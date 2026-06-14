import sqlite3
import chromadb
from contextlib import contextmanager
from typing import Iterator

from config import (
    CHROMA_COLLECTION,
    CHROMA_PATH,
    SQLITE_PATH
)

from core.models import Article, Chunk, Source, Tag

# SQLite

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    url               TEXT NOT NULL,
    type              TEXT NOT NULL,
    credibility_score REAL,
    why_interest      TEXT
);

CREATE TABLE IF NOT EXISTS articles (
    id          TEXT PRIMARY KEY,
    source_id   TEXT NOT NULL REFERENCES sources(id),
    url         TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'unsorted',
    summary     TEXT
);

CREATE TABLE IF NOT EXISTS tags (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS article_tag (
    article_id TEXT NOT NULL REFERENCES articles(id),
    tag_id     TEXT NOT NULL REFERENCES tags(id),
    PRIMARY KEY (article_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_article_source ON articles(source_id);
CREATE INDEX IF NOT EXISTS idx_article_tag_tag ON article_tag(tag_id);
"""


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    try :
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _db() as conn:
        conn.executescript(SCHEMA)

def save_source(source: Source) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sources (id, name, url, type, credibility_score, why_interest) VALUES (?, ?, ?, ?, ?, ?)",
            (
                source.id,
                source.name,
                str(source.url),
                source.type.value,
                source.credibility_score,
                source.why_interest,
            ),
        )

def save_article(article: Article) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO articles (id, source_id, url, title, content, fetched_at, category, summary) VALUES(?,?,?,?,?,?,?,?)",
            (
                article.id,
                article.source_id,
                str(article.url),
                article.title,
                article.content,
                article.fetched_at.isoformat(),
                article.category.value,
                article.summary,
            ),
        )

        for tag in article.tags:
            row = conn.execute("SELECT id FROM tags WHERE name = ?", (tag,)).fetchone()
            if row :
                tag_id = row[0]
            else:
                new_tag = Tag(name=tag)
                conn.execute("INSERT INTO tags (id, name, created_at) VALUES(?,?,?)",
                             (new_tag.id,new_tag.name,new_tag.created_at.isoformat()),
                             )
                tag_id = new_tag.id
            conn.execute(
                "INSERT OR IGNORE INTO article_tag (article_id, tag_id) VALUES(?, ?)",(article.id, tag_id))


def get_article(article_id: str) -> dict | None:
    with _db() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, url, title FROM articles WHERE id = ?", (article_id,)
        ).fetchone()
        return dict(row) if row else None


# Chroma
_chroma_client: chromadb.PersistentClient | None = None

def _chroma() -> chromadb.Collection:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return _chroma_client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        metadata={"hnsw:space":"cosine"},
    )

def save_chunks(chunks: list[Chunk], embeddings:list[list[float]]) -> None:
    if not chunks:
        return
    col = _chroma()
    col.add(
        ids=[c.id for c in chunks],
        embeddings=embeddings,
        documents=[c.text for c in chunks],
        metadatas=[
            {
                "article_id":c.article_id,
                "position":c.position
            } for c in chunks
        ],
    )

def query_chunks(query_embedding: list[float], top_k: int) -> list[dict]:
    col = _chroma()
    res = col.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )
    out = []
    for text, meta, dist in zip(
        res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        out.append({
            "text": text,
            "article_id": meta["article_id"],
            "score": 1 - dist,
        })
    return out
