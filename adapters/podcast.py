"""Resolve public podcast transcripts or audio from episode and platform URLs."""

import html
import json
import re
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from adapters.content import ContentExtractionError, normalize_text
from config import MAX_PODCAST_AUDIO_BYTES, TAVILY_API_KEY, WHISPER_COMPUTE_TYPE, WHISPER_MODEL


_USER_AGENT = "TechWatchAgent/0.1"
# Long-running shows often retain thousands of episodes in one RSS document.
_MAX_METADATA_BYTES = 25 * 1024 * 1024
_AUDIO_TYPES = ("audio/", "video/")


@dataclass(frozen=True)
class ResolvedPodcastEpisode:
    episode_url: str
    title: str | None
    publisher_name: str | None
    publisher_url: str | None
    transcript_url: str | None = None
    audio_url: str | None = None
    language: str | None = None


@dataclass(frozen=True)
class _Document:
    url: str
    content_type: str
    content: bytes


class _EpisodePageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self._in_title = False
        self._in_json_ld = False
        self.json_ld_parts: list[str] = []
        self.feed_urls: list[str] = []
        self.audio_urls: list[str] = []
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        if tag == "title":
            self._in_title = True
        if tag == "link" and "alternate" in values.get("rel", "").casefold():
            if "rss" in values.get("type", "").casefold() or "atom" in values.get("type", "").casefold():
                self.feed_urls.append(values.get("href", ""))
        if tag in {"audio", "source"} and values.get("src"):
            self.audio_urls.append(values["src"])
        if tag == "meta":
            name = (values.get("property") or values.get("name") or "").casefold()
            content = values.get("content", "")
            if name and content:
                self.meta[name] = content
                if name in {"og:audio", "og:audio:url", "twitter:player:stream"}:
                    self.audio_urls.append(content)
        if tag == "script" and values.get("type", "").casefold() == "application/ld+json":
            self._in_json_ld = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag == "script":
            self._in_json_ld = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._in_json_ld:
            self.json_ld_parts.append(data)


def _fetch_document(url: str, *, max_bytes: int = _MAX_METADATA_BYTES) -> _Document:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ContentExtractionError("Podcast URLs must use http or https.")
    request = Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(request, timeout=20) as response:
            content_type = response.headers.get_content_type().lower()
            if content_type.startswith(_AUDIO_TYPES):
                return _Document(
                    url=response.geturl(), content_type=content_type, content=b""
                )
            content = response.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise ContentExtractionError("Podcast metadata response exceeds the size limit.")
            return _Document(
                url=response.geturl(),
                content_type=content_type,
                content=content,
            )
    except ContentExtractionError:
        raise
    except Exception as exc:
        raise ContentExtractionError(f"Could not fetch podcast metadata: {exc}") from exc


def _is_feed(document: _Document) -> bool:
    if "rss" in document.content_type or "xml" in document.content_type:
        return True
    return document.content.lstrip().startswith((b"<?xml", b"<rss", b"<feed"))


def _element_text(element: ET.Element | None) -> str | None:
    if element is None or not element.text or not element.text.strip():
        return None
    return " ".join(element.text.split())


def _find_child(element: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in element if child.tag.rsplit("}", 1)[-1] == name), None)


def _feed_episode(document: _Document, episode_url: str, title_hint: str | None = None) -> ResolvedPodcastEpisode:
    try:
        root = ET.fromstring(document.content)
    except ET.ParseError as exc:
        raise ContentExtractionError("The discovered podcast feed is not valid XML.") from exc

    channel = next((node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "channel"), root)
    publisher_name = _element_text(_find_child(channel, "title"))
    publisher_url = _element_text(_find_child(channel, "link")) or document.url
    language = _element_text(_find_child(channel, "language"))
    items = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] in {"item", "entry"}]
    if not items:
        raise ContentExtractionError("The discovered feed contains no podcast episodes.")

    def score(item: ET.Element) -> int:
        values = [
            _element_text(_find_child(item, name)) or ""
            for name in ("guid", "link", "title")
        ]
        values.extend(child.attrib.get("href", "") for child in item)
        episode_key = episode_url.casefold()
        if any(episode_key == value.casefold() for value in values if value):
            return 3
        if title_hint and any(title_hint.casefold() in value.casefold() for value in values if value):
            return 2
        return 0

    item = max(items, key=score)
    if score(item) == 0 and title_hint:
        raise ContentExtractionError("The discovered feed does not contain the requested episode.")
    title = _element_text(_find_child(item, "title")) or title_hint
    transcript_url = next(
        (
            child.attrib.get("url")
            for child in item
            if child.tag.rsplit("}", 1)[-1] == "transcript" and child.attrib.get("url")
        ),
        None,
    )
    enclosure = _find_child(item, "enclosure")
    audio_url = enclosure.attrib.get("url") if enclosure is not None else None
    if not audio_url:
        audio_url = next(
            (
                child.attrib.get("href")
                for child in item
                if child.tag.rsplit("}", 1)[-1] == "link"
                and "enclosure" in child.attrib.get("rel", "").casefold()
                and child.attrib.get("href")
            ),
            None,
        )
    return ResolvedPodcastEpisode(
        episode_url=episode_url,
        title=title,
        publisher_name=publisher_name,
        publisher_url=publisher_url,
        transcript_url=urljoin(document.url, transcript_url) if transcript_url else None,
        audio_url=urljoin(document.url, audio_url) if audio_url else None,
        language=language,
    )


def _json_values(value: object, keys: set[str]) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key.casefold() in keys and isinstance(item, str):
                found.append(item)
            found.extend(_json_values(item, keys))
    elif isinstance(value, list):
        for item in value:
            found.extend(_json_values(item, keys))
    return found


def _page_metadata(document: _Document) -> tuple[str | None, str | None, str | None, list[str], list[str]]:
    parser = _EpisodePageParser()
    parser.feed(document.content.decode("utf-8", errors="replace"))
    parser.close()
    title = parser.meta.get("og:title") or " ".join(parser.title_parts).strip() or None
    publisher = parser.meta.get("og:site_name")
    publisher_url = parser.meta.get("og:url")
    for raw_json in parser.json_ld_parts:
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
        if not title:
            values = _json_values(payload, {"name", "headline"})
            title = values[0] if values else None
        parser.audio_urls.extend(_json_values(payload, {"contenturl", "encodingurl"}))
        parser.feed_urls.extend(_json_values(payload, {"feedurl", "rssurl"}))
    return title, publisher, publisher_url, parser.feed_urls, parser.audio_urls


def _spotify_metadata(url: str) -> tuple[str | None, str | None, str | None]:
    endpoint = "https://open.spotify.com/oembed?" + urlencode({"url": url, "format": "json"})
    try:
        document = _fetch_document(endpoint)
        payload = json.loads(document.content)
        return payload.get("title"), payload.get("author_name"), payload.get("author_url")
    except (ContentExtractionError, json.JSONDecodeError):
        return None, None, None


def _rss_urls_from_page(document: _Document) -> list[str]:
    _, _, _, feed_urls, _ = _page_metadata(document)
    text = document.content.decode("utf-8", errors="replace")
    feed_urls.extend(
        re.findall(
            r"https?://[^\s\"'<>]*(?:feeds?\.|/feed(?:/|$)|\.rss(?:[?#]|$)|\.xml(?:[?#]|$))[^\s\"'<>]*",
            text,
            flags=re.IGNORECASE,
        )
    )
    unique_urls: list[str] = []
    for candidate in feed_urls:
        absolute = urljoin(document.url, candidate.replace("\\/", "/"))
        if absolute not in unique_urls:
            unique_urls.append(absolute)
    return unique_urls


def _discovered_feeds(title: str, publisher: str | None) -> list[str]:
    if not TAVILY_API_KEY:
        return []
    candidates: list[str] = []
    try:
        from tavily import TavilyClient

        query = f'"{title}" {"\"" + publisher + "\" " if publisher else ""}podcast RSS feed'
        results = TavilyClient(api_key=TAVILY_API_KEY).search(query=query, max_results=5)
    except Exception:
        return None
    for result in results.get("results", []):
        candidate = result.get("url")
        if not candidate:
            continue
        try:
            document = _fetch_document(candidate)
            if _is_feed(document):
                candidates.append(document.url)
            else:
                candidates.extend(_rss_urls_from_page(document))
        except ContentExtractionError:
            continue
    return list(dict.fromkeys(candidates))


def resolve_podcast_episode(url: str) -> ResolvedPodcastEpisode:
    """Resolve a platform URL to a public transcript or audio enclosure."""
    document = _fetch_document(url)
    if _is_feed(document):
        return _feed_episode(document, document.url)
    if document.content_type.startswith(_AUDIO_TYPES):
        host = urlparse(document.url).hostname or "Podcast"
        return ResolvedPodcastEpisode(document.url, None, host, document.url, audio_url=document.url)

    title, publisher, publisher_url, feed_urls, audio_urls = _page_metadata(document)
    host = (urlparse(document.url).hostname or "").lower().removeprefix("www.")
    if host in {"open.spotify.com", "spotify.com"}:
        spotify_title, spotify_publisher, spotify_publisher_url = _spotify_metadata(document.url)
        raw_page_title = re.search(
            r"<title[^>]*>(.*?)</title>",
            document.content.decode("utf-8", errors="replace"),
            flags=re.IGNORECASE | re.DOTALL,
        )
        page_title = html.unescape(raw_page_title.group(1)).strip() if raw_page_title else title or ""
        show_match = re.match(r"^(.+?)\s+-\s+(.+?)\s+\|\s+Podcast on Spotify$", page_title)
        title = spotify_title or (show_match.group(1) if show_match else title)
        publisher = (
            show_match.group(2)
            if show_match
            else spotify_publisher or publisher
        )
        publisher_url = None if show_match else spotify_publisher_url or publisher_url
        # Spotify's page exposes a preview clip as og:audio. It is not the
        # episode enclosure and must never be mistaken for one.
        audio_urls = []

    for feed_url in feed_urls:
        try:
            return _feed_episode(_fetch_document(urljoin(document.url, feed_url)), document.url, title)
        except ContentExtractionError:
            continue
    if audio_urls:
        return ResolvedPodcastEpisode(
            document.url, title, publisher, publisher_url or document.url, audio_url=urljoin(document.url, audio_urls[0])
        )
    if title:
        for discovered in _discovered_feeds(title, publisher):
            try:
                return _feed_episode(_fetch_document(discovered), document.url, title)
            except ContentExtractionError:
                continue
    raise ContentExtractionError(
        "Could not find a public podcast transcript or audio enclosure for this URL. "
        "Spotify-exclusive, subscriber-only, and protected episodes cannot be transcribed."
    )


def _clean_caption_text(text: str) -> str:
    text = re.sub(r"^WEBVTT[^\n]*\n", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\d+\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(
        r"\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3}\s*-->\s*\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3}[^\n]*",
        "",
        text,
    )
    return normalize_text(html.unescape(re.sub(r"<[^>]+>", "", text)))


def fetch_podcast_transcript(url: str) -> str:
    document = _fetch_document(url)
    if document.content_type in {"application/json", "text/json"}:
        try:
            payload = json.loads(document.content)
            pieces = _json_values(payload, {"text", "content", "transcript"})
            return normalize_text("\n\n".join(pieces))
        except (json.JSONDecodeError, ContentExtractionError) as exc:
            raise ContentExtractionError("Could not extract text from the podcast transcript file.") from exc
    return _clean_caption_text(document.content.decode("utf-8", errors="replace"))


def transcribe_podcast_audio(url: str, language: str | None = None) -> str:
    """Download a public enclosure temporarily and transcribe it locally."""
    if (urlparse(url).hostname or "").casefold() == "p.scdn.co":
        raise ContentExtractionError(
            "Spotify preview clips are not full podcast episodes and cannot be transcribed."
        )
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ContentExtractionError(
            "Podcast transcription support is not installed. Run: pip install faster-whisper"
        ) from exc

    suffix = Path(urlparse(url).path).suffix or ".audio"
    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="tech-watch-podcast-", suffix=suffix, delete=False) as output:
            path = Path(output.name)
            request = Request(url, headers={"User-Agent": _USER_AGENT})
            with urlopen(request, timeout=60) as response:
                content_type = response.headers.get_content_type().lower()
                if not content_type.startswith(_AUDIO_TYPES):
                    raise ContentExtractionError("The resolved podcast enclosure is not an audio file.")
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_PODCAST_AUDIO_BYTES:
                        raise ContentExtractionError("Podcast audio exceeds the configured download limit.")
                    output.write(chunk)
        model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type=WHISPER_COMPUTE_TYPE)
        segments, _ = model.transcribe(str(path), language=language, vad_filter=True)
        return normalize_text("\n\n".join(segment.text.strip() for segment in segments if segment.text.strip()))
    except ContentExtractionError:
        raise
    except Exception as exc:
        raise ContentExtractionError(f"Could not transcribe the podcast audio: {exc}") from exc
    finally:
        if path is not None:
            path.unlink(missing_ok=True)
