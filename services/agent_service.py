from typing import TypedDict

from adapters.content import (
    extract_file_content,
    normalize_text,
    persist_upload,
    sha256_bytes,
)
from adapters.url_fetch import fetch_url_content
from adapters.source_verification import (
    SourceVerification,
    find_source,
    personal_note_source,
    source_for_url,
    verify_provided_source,
)
from adapters.store import get_or_create_source, init_db, save_input_asset
from core.content_ingest_graph import build_content_ingest_graph
from core.ingest_graph import build_ingest_graph
from core.models import (
    Article,
    InputAsset,
    OriginalType,
    Source,
    SourceVerificationStatus,
)
from core.retrieve_graph import build_retrieve_graph

class WatchResults(TypedDict):
    topic: str
    article_count: int
    chunk_count: int
    articles: list[dict[str, str | None]]

class AskResults(TypedDict):
    question:str
    answer:str


class AddContentResult(TypedDict):
    article: dict[str, str | None]
    input_asset_id: str
    chunk_count: int
    source_verification_status: str


def _title_from_text(text: str, fallback: str) -> str:
    first_line = next((line for line in text.splitlines() if line.strip()), fallback)
    return first_line.strip()[:500]


def _article_title(text: str, title: str | None) -> str:
    return title.strip()[:500] if title and title.strip() else _title_from_text(
        text,
        "Untitled content",
    )


def _ingest_normalized_content(
    *,
    normalized_text: str,
    input_asset: InputAsset,
    title: str | None,
    verification: SourceVerification | None = None,
    fallback_source: Source | None = None,
) -> AddContentResult:
    init_db()
    source: Source | None = None
    if verification is not None:
        input_asset.source_verification_status = verification.status
        input_asset.source_verification_reason = verification.reason
        input_asset.source_verification_confidence = verification.confidence
    has_verified_source = (
        verification is not None
        and verification.status is SourceVerificationStatus.VERIFIED
        and verification.source is not None
    )
    if has_verified_source:
        source = get_or_create_source(verification.source)
        input_asset.verified_source_id = source.id
    elif fallback_source is not None:
        source = get_or_create_source(fallback_source)
    save_input_asset(input_asset)

    article = Article(
        title=_article_title(normalized_text, title),
        content=normalized_text,
        original_type=input_asset.original_type,
        source_id=source.id if source is not None else None,
        url=verification.article_url if has_verified_source else None,
    )
    graph = build_content_ingest_graph()
    final = graph.invoke({"article": article, "input_asset": input_asset})

    return {
        "article": {
            "id": final["persisted_article_id"],
            "title": article.title,
            "url": str(article.url) if article.url is not None else None,
        },
        "input_asset_id": input_asset.id,
        "chunk_count": len(final["chunks"]),
        "source_verification_status": input_asset.source_verification_status.value,
    }


def add_pasted_text(
    text: str,
    title: str | None = None,
    provided_source_url: str | None = None,
) -> AddContentResult:
    raw_bytes = text.encode("utf-8")
    input_asset = InputAsset(
        original_type=OriginalType.TEXT,
        mime_type="text/plain",
        sha256=sha256_bytes(raw_bytes),
        raw_text=text,
        extracted_text=normalize_text(text),
        provided_source_url=provided_source_url,
    )
    return _ingest_normalized_content(
        normalized_text=input_asset.extracted_text,
        input_asset=input_asset,
        title=title,
    )


def add_uploaded_file(
    content: bytes,
    filename: str,
    mime_type: str | None,
    title: str | None = None,
    provided_source_url: str | None = None,
) -> AddContentResult:
    original_type, normalized_mime_type, extracted_text = extract_file_content(
        content,
        filename,
        mime_type,
    )
    article_title = _article_title(extracted_text, title)
    verification = (
        verify_provided_source(
            input_text=extracted_text,
            input_title=article_title,
            source_url=provided_source_url,
        )
        if provided_source_url
        else find_source(input_text=extracted_text, input_title=article_title)
    )
    fallback_source = (
        personal_note_source()
        if provided_source_url is None
        and verification.status is not SourceVerificationStatus.VERIFIED
        else None
    )
    digest = sha256_bytes(content)
    input_asset = InputAsset(
        original_type=original_type,
        mime_type=normalized_mime_type,
        input_filename=filename,
        storage_path=persist_upload(content, filename, digest),
        sha256=digest,
        extracted_text=extracted_text,
        provided_source_url=provided_source_url,
        source_verification_status=verification.status,
        source_verification_reason=verification.reason,
        source_verification_confidence=verification.confidence,
    )
    return _ingest_normalized_content(
        normalized_text=extracted_text,
        input_asset=input_asset,
        title=title,
        verification=verification,
        fallback_source=fallback_source,
    )


def add_article_by_url(
    url: str,
    title: str | None = None,
) -> AddContentResult:
    fetched = fetch_url_content(url)
    verification = SourceVerification(
        status=SourceVerificationStatus.VERIFIED,
        reason=f"Fetched directly from {fetched.final_url}.",
        confidence=1.0,
        source=source_for_url(fetched.final_url),
        article_url=fetched.final_url,
    )
    digest = sha256_bytes(fetched.content)
    input_asset = InputAsset(
        original_type=fetched.original_type,
        mime_type=fetched.mime_type,
        input_filename=fetched.filename,
        storage_path=persist_upload(fetched.content, fetched.filename, digest),
        sha256=digest,
        extracted_text=fetched.text,
        provided_source_url=url,
        source_verification_status=verification.status,
        source_verification_reason=verification.reason,
        source_verification_confidence=verification.confidence,
    )
    return _ingest_normalized_content(
        normalized_text=fetched.text,
        input_asset=input_asset,
        title=title or fetched.title or None,
        verification=verification,
    )

def watch_topic(topic: str) -> WatchResults:
    init_db()
    graph = build_ingest_graph()
    final = graph.invoke({"topic": topic})

    return {
        "topic": topic,
        "article_count": len(final["articles"]),
        "chunk_count": len(final["chunks"]),
        "articles": [
            {
                "id": article.id,
                "title": article.title,
                "url": str(article.url) if article.url is not None else None,
            }
            for article in final["articles"]
        ],
    }

def ask_question(question: str) -> AskResults:
    init_db()
    graph = build_retrieve_graph()
    final = graph.invoke({"question": question})

    return {
        "question": question,
        "answer": final["answer"],
    }
