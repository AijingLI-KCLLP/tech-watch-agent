"""Transcript acquisition and metadata helpers for media-backed content."""

import json
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from adapters.content import ContentExtractionError, normalize_text
from core.models import Source, SourceType


@dataclass(frozen=True)
class YouTubeTranscript:
    video_url: str
    title: str | None
    channel_name: str | None
    channel_url: str | None
    text: str


def _youtube_video_id(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
    elif host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        else:
            match = re.match(r"^/(?:embed|shorts|live)/([^/?]+)", parsed.path)
            video_id = match.group(1) if match else ""
    else:
        raise ContentExtractionError("The URL is not a supported YouTube video URL.")

    if not re.fullmatch(r"[A-Za-z0-9_-]{6,}", video_id):
        raise ContentExtractionError("Could not find a YouTube video id in this URL.")
    return video_id


def _youtube_oembed(video_url: str) -> tuple[str | None, str | None, str | None]:
    """Best-effort title and channel lookup; captions remain the source of truth."""
    endpoint = "https://www.youtube.com/oembed?" + urlencode(
        {"url": video_url, "format": "json"}
    )
    try:
        request = Request(endpoint, headers={"User-Agent": "TechWatchAgent/0.1"})
        with urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data.get("title"), data.get("author_name"), data.get("author_url")
    except Exception:
        return None, None, None


def _caption_text(video_id: str) -> str:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise ContentExtractionError(
            "YouTube transcript support is not installed. Run: pip install youtube-transcript-api"
        ) from exc

    try:
        transcript = YouTubeTranscriptApi().fetch(video_id)
        snippets = getattr(transcript, "snippets", transcript)
        parts = [
            str(snippet.get("text", ""))
            if isinstance(snippet, dict)
            else str(getattr(snippet, "text", ""))
            for snippet in snippets
        ]
    except Exception as exc:
        raise ContentExtractionError(
            f"Could not retrieve a transcript for this YouTube video: {exc}"
        ) from exc

    return normalize_text("\n\n".join(part for part in parts if part.strip()))


def fetch_youtube_transcript(url: str) -> YouTubeTranscript:
    """Retrieve a public caption transcript without downloading the video itself."""
    video_id = _youtube_video_id(url)
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    title, channel_name, channel_url = _youtube_oembed(video_url)
    return YouTubeTranscript(
        video_url=video_url,
        title=title,
        channel_name=channel_name,
        channel_url=channel_url,
        text=_caption_text(video_id),
    )


def youtube_source(transcript: YouTubeTranscript) -> Source:
    """Use the channel as the publisher and the video URL as the content URL."""
    return Source(
        name=transcript.channel_name or "YouTube",
        url=transcript.channel_url or "https://www.youtube.com",
        type=SourceType.VIDEO,
    )


def podcast_source(episode_url: str) -> Source:
    """A podcast source is the episode host until feed metadata is available."""
    parsed = urlparse(episode_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ContentExtractionError("Podcast URLs must use http or https.")
    return Source(
        name=parsed.hostname.removeprefix("www."),
        url=f"{parsed.scheme}://{parsed.netloc}",
        type=SourceType.PODCAST,
    )
