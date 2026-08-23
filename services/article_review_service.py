"""Review-time Article edits, including retrieval-index refreshes."""

from adapters.embedder import embed
from adapters.store import get_article_detail, save_chunks, update_article
from config import CHUNK_OVERLAP, CHUNK_SIZE
from core.ingest_graph import _split
from core.models import Chunk


def _replace_article_chunks(article_id: str, content: str) -> None:
    """Replace retrieval chunks after a reviewer changes normalized content."""
    chunks = [
        Chunk(article_id=article_id, text=text, position=position)
        for position, text in enumerate(_split(content, CHUNK_SIZE, CHUNK_OVERLAP))
    ]
    embeddings = embed([chunk.text for chunk in chunks])
    from adapters import store

    collection = store._chroma()
    collection.delete(where={"article_id": article_id})
    save_chunks(chunks, embeddings)


def edit_article(article_id: str, **updates: object) -> dict | None:
    """Save reviewer changes and keep retrieval aligned with normalized content."""
    content = updates.get("content")
    if content is not None:
        if get_article_detail(article_id) is None:
            return None
        _replace_article_chunks(article_id, str(content))

    return update_article(article_id, **updates)
