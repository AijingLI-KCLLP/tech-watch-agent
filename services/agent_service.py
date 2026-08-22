from typing import TypedDict

from adapters.store import init_db
from core.ingest_graph import build_ingest_graph
from core.retrieve_graph import build_retrieve_graph

class WatchResults(TypedDict):
    topic: str
    article_count: int
    chunk_count: int
    articles: list[dict[str, str | None]]

class AskResults(TypedDict):
    question:str
    answer:str

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