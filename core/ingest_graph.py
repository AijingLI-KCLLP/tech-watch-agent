from typing import TypedDict
from adapters.embedder import embed
from adapters.search import search
from adapters.store import save_article, save_chunks, save_source
from config import CHUNK_OVERLAP, CHUNK_SIZE
from core.models import Article, Chunk, Source

from langgraph.graph import END, START, StateGraph

class IngestState(TypedDict):
    topic: str
    sources: list[Source]
    articles: list[Article]
    chunks: list[Chunk]
    embeddings: list[list[float]]

def _split(text: str, step:int, overlap:int) ->list[str]:
    pieces = []
    start = 0
    step = step - overlap
    while start < len(text):
        pieces.append(text[start:start + step])
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

def chunk_node(state:IngestState) -> dict:
    chunks: list[Chunk] = []
    for article in state["articles"]:
        for i, text in enumerate(_split(article.content, CHUNK_SIZE, CHUNK_OVERLAP)):
            chunks.append(Chunk(article_id=article.id, text=text,position=i))
        return {"chunks":chunks}

def embed_node(state:IngestState) -> dict:
    vectors = embed([c.text for c in state["chunks"]])
    return {"embeddings":vectors}

def store_node(state:IngestState) -> dict:
    for src in state["sources"]:
        save_source(src)
    for article in state["articles"]:
        save_article(article)
    save_chunks(state["chunks"],state["embeddings"])
    return {}

def build_ingest_graph():
    g = StateGraph(IngestState)

    g.add_node("search", search_node)
    g.add_node("chunk", chunk_node)
    g.add_node("embed", embed_node)
    g.add_node("store", store_node)

    g.add_edge(START, "search")
    g.add_edge("search", "chunk")
    g.add_edge("chunk", "embed")
    g.add_edge("embed", "store")
    g.add_edge("store",END)
