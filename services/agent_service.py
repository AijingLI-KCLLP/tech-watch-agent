from typing import TypedDict

from adapters.content import (
    ContentExtractionError,
    extract_file_content,
    normalize_text,
    persist_upload,
    sha256_bytes,
)
from adapters.media import fetch_youtube_transcript, podcast_source, youtube_source
from adapters.podcast import (
    fetch_podcast_transcript,
    resolve_podcast_episode,
    transcribe_podcast_audio,
)
from adapters.categorizer import categorize_text
from adapters.qualifier import qualify_source
from adapters.tagger import tag_text
from adapters.url_fetch import fetch_url_content
from adapters.source_verification import (
    SourceVerification,
    find_source,
    personal_note_source,
    source_for_url,
    verify_provided_source,
)
from adapters.store import (
    get_or_create_source,
    init_db,
    list_articles_for_categorization,
    list_articles_for_tagging,
    list_sources_for_qualification,
    save_article_tags,
    save_input_asset,
    update_article_category,
    update_source_qualification,
)
from core.content_ingest_graph import build_content_ingest_graph
from core.ingest_graph import build_ingest_graph
from core.models import (
    Article,
    Category,
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


class CategorizeResults(TypedDict):
    processed: int
    updated: int
    would_update: int
    kept_inbox: int
    failed: list[dict[str, str]]


class QualifyResults(TypedDict):
    processed: int
    qualified_sources: int
    updated_rows: int
    unqualified_sources: int


class TagResults(TypedDict):
    processed: int
    generated_tags: int
    added_tag_links: int
    failed: list[dict[str, str]]


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
        source = get_or_create_source(qualify_source(verification.source))
        input_asset.verified_source_id = source.id
    elif fallback_source is not None:
        source = get_or_create_source(qualify_source(fallback_source))
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


def add_youtube_video(
    url: str,
    title: str | None = None,
) -> AddContentResult:
    """Turn a YouTube video's public captions into searchable library text."""
    transcript = fetch_youtube_transcript(url)
    verification = SourceVerification(
        status=SourceVerificationStatus.VERIFIED,
        reason="Public YouTube captions were retrieved for this video.",
        confidence=1.0,
        source=youtube_source(transcript),
        article_url=transcript.video_url,
    )
    raw_bytes = transcript.text.encode("utf-8")
    input_asset = InputAsset(
        original_type=OriginalType.TEXT,
        mime_type="text/plain",
        input_filename=f"youtube-{transcript.video_url.rsplit('=', maxsplit=1)[-1]}.transcript.txt",
        sha256=sha256_bytes(raw_bytes),
        raw_text=transcript.text,
        extracted_text=transcript.text,
        provided_source_url=transcript.video_url,
        source_verification_status=verification.status,
        source_verification_reason=verification.reason,
        source_verification_confidence=verification.confidence,
    )
    return _ingest_normalized_content(
        normalized_text=transcript.text,
        input_asset=input_asset,
        title=title or transcript.title,
        verification=verification,
    )


def add_podcast_episode(
    *,
    url: str,
    transcript: str | None = None,
    transcript_url: str | None = None,
    title: str | None = None,
) -> AddContentResult:
    """Ingest pasted, publisher-provided, or locally transcribed podcast text."""
    if transcript and transcript.strip() and transcript_url:
        raise ContentExtractionError(
            "Provide transcript text or transcript_url, not both."
        )

    transcript_title = None
    if transcript_url:
        fetched = fetch_url_content(transcript_url)
        normalized_text = fetched.text
        transcript_title = fetched.title or None
        provenance_reason = f"Transcript retrieved from {fetched.final_url}."
        input_filename = fetched.filename
        mime_type = fetched.mime_type
        raw_text = None
        source_url = url
        source = podcast_source(url)
    elif transcript and transcript.strip():
        normalized_text = normalize_text(transcript or "")
        provenance_reason = "Transcript supplied with the podcast episode URL."
        input_filename = "podcast.transcript.txt"
        mime_type = "text/plain"
        raw_text = transcript
        source_url = url
        source = podcast_source(url)
    else:
        resolved = resolve_podcast_episode(url)
        source_url = url
        source = Source(
            name=resolved.publisher_name or podcast_source(url).name,
            url=resolved.publisher_url or str(podcast_source(url).url),
            type=podcast_source(url).type,
        )
        transcript_title = resolved.title
        if resolved.transcript_url:
            normalized_text = fetch_podcast_transcript(resolved.transcript_url)
            provenance_reason = f"Transcript retrieved from the publisher feed: {resolved.transcript_url}."
            input_filename = "podcast.publisher-transcript.txt"
        elif resolved.audio_url:
            normalized_text = transcribe_podcast_audio(
                resolved.audio_url, language=resolved.language
            )
            provenance_reason = f"Transcript generated locally from the public episode audio: {resolved.audio_url}."
            input_filename = "podcast.local-transcript.txt"
        else:
            raise ContentExtractionError(
                "The podcast feed does not provide a transcript or public audio enclosure."
            )
        mime_type = "text/plain"
        raw_text = normalized_text

    verification = SourceVerification(
        status=SourceVerificationStatus.VERIFIED,
        reason=provenance_reason,
        confidence=1.0,
        source=source,
        article_url=source_url,
    )
    raw_bytes = normalized_text.encode("utf-8")
    input_asset = InputAsset(
        original_type=OriginalType.TEXT,
        mime_type=mime_type,
        input_filename=input_filename,
        sha256=sha256_bytes(raw_bytes),
        raw_text=raw_text,
        extracted_text=normalized_text,
        provided_source_url=url,
        source_verification_status=verification.status,
        source_verification_reason=verification.reason,
        source_verification_confidence=verification.confidence,
    )
    return _ingest_normalized_content(
        normalized_text=normalized_text,
        input_asset=input_asset,
        title=title or transcript_title,
        verification=verification,
    )


def categorize_existing_articles(
    *, only_inbox: bool = True, dry_run: bool = False
) -> CategorizeResults:
    """Categorize saved articles while preserving reviewed categories by default."""
    init_db()
    articles = list_articles_for_categorization(only_inbox=only_inbox)
    updated = 0
    would_update = 0
    kept_inbox = 0
    failed: list[dict[str, str]] = []

    for article in articles:
        try:
            category = categorize_text(article["title"], article["content"])
        except Exception as exc:
            failed.append({"id": article["id"], "error": str(exc)})
            continue

        if category is Category.INBOX:
            kept_inbox += 1
        if category.value != article["category"]:
            would_update += 1
            if not dry_run and update_article_category(article["id"], category):
                updated += 1

    return {
        "processed": len(articles),
        "updated": updated,
        "would_update": would_update,
        "kept_inbox": kept_inbox,
        "failed": failed,
    }


def tag_existing_articles(
    *, dry_run: bool = False, replace: bool = False
) -> TagResults:
    """Generate tags for saved articles, optionally replacing prior tag links."""
    init_db()
    articles = list_articles_for_tagging()
    generated_tags = 0
    added_tag_links = 0
    failed: list[dict[str, str]] = []

    for article in articles:
        try:
            tags = tag_text(article["title"], article["content"])
        except Exception as exc:
            failed.append({"id": article["id"], "error": str(exc)})
            continue

        generated_tags += len(tags)
        if not dry_run and tags:
            added_tag_links += save_article_tags(
                article["id"], tags, replace=replace
            )

    return {
        "processed": len(articles),
        "generated_tags": generated_tags,
        "added_tag_links": added_tag_links,
        "failed": failed,
    }


def qualify_existing_sources(*, dry_run: bool = False) -> QualifyResults:
    """Backfill missing source-legitimacy fields once per canonical URL."""
    init_db()
    sources = list_sources_for_qualification()
    qualified_sources = 0
    updated_rows = 0
    unqualified_sources = 0

    for source in sources:
        qualified = qualify_source(source)
        if (
            qualified.credibility_score is None
            or qualified.credibility_reason is None
        ):
            unqualified_sources += 1
            continue

        qualified_sources += 1
        if not dry_run:
            updated_rows += update_source_qualification(qualified)

    return {
        "processed": len(sources),
        "qualified_sources": qualified_sources,
        "updated_rows": updated_rows,
        "unqualified_sources": unqualified_sources,
    }

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

    if final.get("needs_web_search", False):
        watch_topic(question)
        final = graph.invoke({"question": question})

    answer = final["answer"]
    if final.get("needs_web_search", False):
        answer = (
            "I searched for and ingested material related to this question, but "
            "could not find enough relevant context to answer it reliably."
        )

    return {
        "question": question,
        "answer": answer,
    }
