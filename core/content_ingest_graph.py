from typing import TypedDict

from adapters.categorizer import categorize_article
from adapters.embedder import embed
from adapters.store import link_input_asset_to_article, save_article, save_chunks
from config import CHUNK_OVERLAP, CHUNK_SIZE
from core.models import Article, Chunk, InputAsset
from langgraph.graph import END, START, StateGraph


class ContentIngestState(TypedDict):
    article: Article
    input_asset: InputAsset
    chunks: list[Chunk]
    embeddings: list[list[float]]
    persisted_article_id: str


def _split(text: str, size: int, overlap: int) -> list[str]:
    pieces = []
    start = 0
    step = size - overlap
    while start < len(text):
        pieces.append(text[start : start + size])
        start += step
    return pieces


def categorize_node(state: ContentIngestState) -> dict:
    article = state["article"]
    article.category = categorize_article(article)
    return {"article": article}


def chunk_node(state: ContentIngestState) -> dict:
    article = state["article"]
    chunks = [
        Chunk(article_id=article.id, text=text, position=position)
        for position, text in enumerate(
            _split(article.content, CHUNK_SIZE, CHUNK_OVERLAP)
        )
    ]
    return {"chunks": chunks}


def embed_node(state: ContentIngestState) -> dict:
    return {"embeddings": embed([chunk.text for chunk in state["chunks"]])}


def store_node(state: ContentIngestState) -> dict:
    article = state["article"]
    persisted_article_id = save_article(article)

    link_input_asset_to_article(state["input_asset"].id, persisted_article_id)

    chunks = [
        Chunk(
            id=chunk.id,
            article_id=persisted_article_id,
            text=chunk.text,
            position=chunk.position,
        )
        for chunk in state["chunks"]
    ]
    save_chunks(chunks, state["embeddings"])
    return {"persisted_article_id": persisted_article_id}


def build_content_ingest_graph():
    graph = StateGraph(ContentIngestState)
    graph.add_node("categorize", categorize_node)
    graph.add_node("chunk", chunk_node)
    graph.add_node("embed", embed_node)
    graph.add_node("store", store_node)
    graph.add_edge(START, "categorize")
    graph.add_edge("categorize", "chunk")
    graph.add_edge("chunk", "embed")
    graph.add_edge("embed", "store")
    return graph.compile()
