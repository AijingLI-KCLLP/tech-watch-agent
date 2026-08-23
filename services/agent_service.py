from typing import TypedDict

from adapters.content import (
    extract_file_content,
    normalize_text,
    persist_upload,
    sha256_bytes,
)
from adapters.store import init_db, save_input_asset
from core.content_ingest_graph import build_content_ingest_graph
from core.ingest_graph import build_ingest_graph
from core.models import Article, InputAsset, OriginalType
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


def _title_from_text(text: str, fallback: str) -> str:
    first_line = next((line for line in text.splitlines() if line.strip()), fallback)
    return first_line.strip()[:500]


def _ingest_normalized_content(
    *,
    normalized_text: str,
    input_asset: InputAsset,
    title: str | None,
) -> AddContentResult:
    init_db()
    save_input_asset(input_asset)

    article = Article(
        title=title.strip()[:500] if title and title.strip() else _title_from_text(
            normalized_text,
            "Untitled content",
        ),
        content=normalized_text,
        original_type=input_asset.original_type,
    )
    graph = build_content_ingest_graph()
    final = graph.invoke({"article": article, "input_asset": input_asset})

    return {
        "article": {
            "id": final["persisted_article_id"],
            "title": article.title,
            "url": None,
        },
        "input_asset_id": input_asset.id,
        "chunk_count": len(final["chunks"]),
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
    digest = sha256_bytes(content)
    input_asset = InputAsset(
        original_type=original_type,
        mime_type=normalized_mime_type,
        input_filename=filename,
        storage_path=persist_upload(content, filename, digest),
        sha256=digest,
        extracted_text=extracted_text,
        provided_source_url=provided_source_url,
    )
    return _ingest_normalized_content(
        normalized_text=extracted_text,
        input_asset=input_asset,
        title=title,
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
