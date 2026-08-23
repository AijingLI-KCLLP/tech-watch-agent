from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from adapters.content import ContentExtractionError, extract_file_content, normalize_text
from core.models import OriginalType

MAX_URL_FETCH_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class FetchedUrlContent:
    requested_url: str
    final_url: str
    filename: str
    mime_type: str
    original_type: OriginalType
    title: str
    text: str
    content: bytes


class _HtmlExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_title = False
        self._ignored_depth = 0
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if not self._ignored_depth and not self._in_title:
            self.text_parts.append(data)


def _extract_html(content: bytes, charset: str | None) -> tuple[str, str]:
    parser = _HtmlExtractor()
    parser.feed(content.decode(charset or "utf-8", errors="replace"))
    parser.close()
    raw_title = " ".join(parser.title_parts).strip()
    title = normalize_text(raw_title) if raw_title else ""
    return title, normalize_text("\n\n".join(parser.text_parts))


def _filename_for_url(url: str, mime_type: str) -> str:
    filename = unquote(Path(urlparse(url).path).name)
    if filename and Path(filename).suffix:
        return filename
    stem = filename or "article"
    if mime_type == "application/pdf":
        return f"{stem}.pdf"
    if mime_type.startswith("image/"):
        return f"{stem}.{mime_type.split('/', maxsplit=1)[1]}"
    if mime_type in {"text/html", "application/xhtml+xml"}:
        return f"{stem}.html"
    return f"{stem}.txt"


def fetch_url_content(url: str) -> FetchedUrlContent:
    """Download and extract supported article content based on the response Content-Type."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ContentExtractionError("Article URLs must use http or https.")

    request = Request(url, headers={"User-Agent": "TechWatchAgent/0.1"})
    try:
        with urlopen(request, timeout=10) as response:
            content = response.read(MAX_URL_FETCH_BYTES + 1)
            if len(content) > MAX_URL_FETCH_BYTES:
                raise ContentExtractionError("The URL response exceeds the 5 MB limit.")
            final_url = response.geturl()
            mime_type = response.headers.get_content_type().lower()
            charset = response.headers.get_content_charset()
    except ContentExtractionError:
        raise
    except Exception as exc:
        raise ContentExtractionError(f"Could not fetch the article URL: {exc}") from exc

    filename = _filename_for_url(final_url, mime_type)
    try:
        if mime_type in {"text/html", "application/xhtml+xml"}:
            title, text = _extract_html(content, charset)
            original_type = OriginalType.TEXT
        elif mime_type == "application/pdf" or mime_type.startswith("image/") or mime_type.startswith("text/"):
            original_type, mime_type, text = extract_file_content(content, filename, mime_type)
            title = ""
        else:
            raise ContentExtractionError(
                f"Unsupported URL Content-Type: {mime_type}. "
                "Only HTML, text, PDF, and image URLs are supported."
            )
    except ContentExtractionError:
        raise
    except Exception as exc:
        raise ContentExtractionError(f"Could not extract article content: {exc}") from exc

    return FetchedUrlContent(
        requested_url=url,
        final_url=final_url,
        filename=filename,
        mime_type=mime_type,
        original_type=original_type,
        title=title,
        text=text,
        content=content,
    )
