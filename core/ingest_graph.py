from typing import TypedDict
from adapters.categorizer import categorize_article
from adapters.embedder import embed
from adapters.search import search
from adapters.store import save_article, save_article_tags, save_chunks, save_source
from config import CHUNK_OVERLAP, CHUNK_SIZE
from core.models import Article, Chunk, Source
from langgraph.graph import END, START, StateGraph

class IngestState(TypedDict):
    topic: str
    sources: list[Source]
    articles: list[Article]
    chunks: list[Chunk]
    embeddings: list[list[float]]

def _split(text: str, size:int, overlap:int) ->list[str]:
    pieces = []
    start = 0
    step = size - overlap
    while start < len(text):
        pieces.append(text[start:start + size])
        start += step
    return pieces

def search_node(state:IngestState) -> dict:
    pairs = search(state["topic"])

    seen:dict[str,Source]={}
    articles: list[Article] = []

    for src, article in pairs:
        if src.id not in seen:
            seen[src.id] = src
        articles.append(article)
    return {"sources":list(seen.values()), "articles":articles}


def categorize_node(state: IngestState) -> dict:
    articles = state["articles"]
    for article in articles:
        article.category = categorize_article(article)
    return {"articles": articles}

def chunk_node(state:IngestState) -> dict:
    chunks: list[Chunk] = []
    for article in state["articles"]:
        for i, text in enumerate(_split(article.content, CHUNK_SIZE, CHUNK_OVERLAP)):
            chunks.append(Chunk(article_id=article.id, text=text,position=i))
    return {"chunks":chunks}

def embed_node(state:IngestState) -> dict:
    vectors = embed([c.text for c in state["chunks"]])
    return {"embeddings":vectors}


def store_node(state: IngestState) -> dict:
    for src in state["sources"]:
        save_source(src)

    article_id_map: dict[str, str] = {}
    for article in state["articles"]:
        persisted_article_id = save_article(article)
        article_id_map[article.id] = persisted_article_id
        save_article_tags(persisted_article_id, [state["topic"]])

    persisted_chunks: list[Chunk] = []
    for chunk in state["chunks"]:
        persisted_chunks.append(
            Chunk(
                id=chunk.id,
                article_id=article_id_map[chunk.article_id],
                text=chunk.text,
                position=chunk.position,
            )
        )

    save_chunks(persisted_chunks, state["embeddings"])
    return {}


def build_ingest_graph():
    g = StateGraph(IngestState)

    g.add_node("search", search_node)
    g.add_node("categorize", categorize_node)
    g.add_node("chunk", chunk_node)
    g.add_node("embed", embed_node)
    g.add_node("store", store_node)

    g.add_edge(START, "search")
    g.add_edge("search", "categorize")
    g.add_edge("categorize", "chunk")
    g.add_edge("chunk", "embed")
    g.add_edge("embed", "store")
    g.add_edge("store",END)

    return g.compile()
