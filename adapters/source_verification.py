import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from adapters.content import ContentExtractionError
from adapters.url_fetch import fetch_url_content
from config import TAVILY_API_KEY
from core.models import Source, SourceType, SourceVerificationStatus

PERSONAL_NOTE_SOURCE_URL = "https://personal-note.invalid/"


@dataclass(frozen=True)
class SourceVerification:
    status: SourceVerificationStatus
    reason: str
    confidence: float | None
    source: Source | None = None
    article_url: str | None = None


def source_for_url(url: str) -> Source:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if parsed.scheme not in {"http", "https"} or hostname is None:
        raise ContentExtractionError("Source URLs must use http or https.")
    return Source(
        name=hostname.removeprefix("www."),
        url=f"{parsed.scheme}://{parsed.netloc}",
        # URL-based type inference is deliberately deferred to source enrichment.
        type=SourceType.OTHER,
    )


def personal_note_source() -> Source:
    """Return the stable local Source used when an upload has no verified origin."""
    return Source(
        name="Personal note",
        # Source.url is currently required; .invalid is reserved and never fetched.
        url=PERSONAL_NOTE_SOURCE_URL,
        type=SourceType.PERSONAL_NOTE,
    )


def _fetch_source_content(url: str) -> tuple[str, str, str]:
    """Fetch a source and return its final URL, title, and readable text."""
    try:
        fetched = fetch_url_content(url)
    except ContentExtractionError:
        raise
    except Exception as exc:
        raise ContentExtractionError(f"Could not fetch the source URL: {exc}") from exc
    return fetched.final_url, fetched.title, fetched.text


def _normalized_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _character_ngrams(text: str, width: int = 4) -> set[str]:
    normalized = _normalized_for_match(text)
    if len(normalized) <= width:
        return {normalized} if normalized else set()
    return {normalized[index : index + width] for index in range(len(normalized) - width + 1)}


def _coverage(input_text: str, candidate_text: str) -> float:
    input_ngrams = _character_ngrams(input_text)
    candidate_ngrams = _character_ngrams(candidate_text)
    if not input_ngrams or not candidate_ngrams:
        return 0.0
    return len(input_ngrams & candidate_ngrams) / len(input_ngrams)


def _compare_source(
    *, input_text: str, input_title: str, candidate_text: str, candidate_title: str
) -> tuple[SourceVerificationStatus, float, str]:
    text_coverage = _coverage(input_text, candidate_text)
    title_coverage = _coverage(input_title, candidate_title) if input_title and candidate_title else 0.0
    confidence = round((0.8 * text_coverage) + (0.2 * title_coverage), 3)

    if text_coverage >= 0.7 or (text_coverage >= 0.5 and title_coverage >= 0.5):
        return (
            SourceVerificationStatus.VERIFIED,
            confidence,
            f"Strong text match ({text_coverage:.0%}) with title match ({title_coverage:.0%}).",
        )
    if text_coverage >= 0.2 or title_coverage >= 0.5:
        return (
            SourceVerificationStatus.PLAUSIBLE,
            confidence,
            f"Partial text match ({text_coverage:.0%}) with title match ({title_coverage:.0%}).",
        )
    return (
        SourceVerificationStatus.MISMATCH,
        confidence,
        f"Weak text match ({text_coverage:.0%}) with title match ({title_coverage:.0%}).",
    )


def _verification_from_candidate(
    *,
    input_text: str,
    input_title: str,
    candidate_url: str,
    candidate_title: str,
    candidate_text: str,
    prefix: str,
) -> SourceVerification:
    status, confidence, reason = _compare_source(
        input_text=input_text,
        input_title=input_title,
        candidate_text=candidate_text,
        candidate_title=candidate_title,
    )
    source = source_for_url(candidate_url) if status is SourceVerificationStatus.VERIFIED else None
    return SourceVerification(
        status=status,
        reason=f"{prefix} {reason}",
        confidence=confidence,
        source=source,
        article_url=candidate_url if source is not None else None,
    )


def verify_provided_source(
    *, input_text: str, input_title: str, source_url: str
) -> SourceVerification:
    """Fetch and compare a user-provided source URL against uploaded content."""
    try:
        final_url, source_title, source_text = _fetch_source_content(source_url)
    except ContentExtractionError as exc:
        return SourceVerification(
            status=SourceVerificationStatus.UNVERIFIED,
            reason=str(exc),
            confidence=None,
        )

    return _verification_from_candidate(
        input_text=input_text,
        input_title=input_title,
        candidate_url=final_url,
        candidate_title=source_title,
        candidate_text=source_text,
        prefix="Provided source URL fetched successfully.",
    )


def _search_candidates(query: str) -> list[dict[str, Any]]:
    if not TAVILY_API_KEY:
        raise ContentExtractionError("TAVILY_API_KEY is not configured, so a source cannot be found.")
    try:
        from tavily import TavilyClient

        response = TavilyClient(api_key=TAVILY_API_KEY).search(
            query=query,
            include_raw_content=True,
            max_results=5,
        )
        return response.get("results", [])
    except Exception as exc:
        raise ContentExtractionError(f"Could not search for a source: {exc}") from exc


def find_source(*, input_text: str, input_title: str) -> SourceVerification:
    """Search for the best source candidate when an uploaded file has no source URL."""
    query = f'"{input_title}" {input_text[:500]}'.strip()
    try:
        candidates = _search_candidates(query)
    except ContentExtractionError as exc:
        return SourceVerification(
            status=SourceVerificationStatus.UNVERIFIED,
            reason=str(exc),
            confidence=None,
        )

    verifications = []
    for candidate in candidates:
        url = candidate.get("url")
        candidate_text = candidate.get("raw_content") or candidate.get("content") or ""
        if not url or not candidate_text:
            continue
        try:
            verifications.append(
                _verification_from_candidate(
                    input_text=input_text,
                    input_title=input_title,
                    candidate_url=url,
                    candidate_title=candidate.get("title") or "",
                    candidate_text=candidate_text,
                    prefix=f"Found candidate {url}.",
                )
            )
        except ContentExtractionError:
            continue

    if not verifications:
        return SourceVerification(
            status=SourceVerificationStatus.UNVERIFIED,
            reason="No searchable source with readable content was found.",
            confidence=None,
        )

    ranking = {
        SourceVerificationStatus.VERIFIED: 3,
        SourceVerificationStatus.PLAUSIBLE: 2,
        SourceVerificationStatus.MISMATCH: 1,
        SourceVerificationStatus.UNVERIFIED: 0,
    }
    return max(
        verifications,
        key=lambda verification: (ranking[verification.status], verification.confidence or 0),
    )
