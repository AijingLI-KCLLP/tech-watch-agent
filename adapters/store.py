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
         CREATE TABLE IF NOT EXISTS sources
         (
             id
             TEXT
             PRIMARY
             KEY,
             name
             TEXT
             NOT
             NULL,
             url
             TEXT
             NOT
             NULL,
             type
             TEXT
             NOT
             NULL,
             credibility_score
             REAL,
             source_summary
             TEXT
         );

         CREATE TABLE IF NOT EXISTS articles
         (
             id
             TEXT
             PRIMARY
             KEY,
             source_id
             TEXT
             NOT
             NULL
             REFERENCES
             sources
         (
             id
         ),
             url TEXT UNIQUE,
             title TEXT NOT NULL,
             content TEXT NOT NULL,
             fetched_at TEXT NOT NULL,
             category TEXT NOT NULL DEFAULT 'unsorted',
             n_tags INTEGER NOT NULL DEFAULT 0,
             summary TEXT,
             original_type TEXT
             );

         CREATE TABLE IF NOT EXISTS tags
         (
             id
             TEXT
             PRIMARY
             KEY,
             name
             TEXT
             NOT
             NULL
             UNIQUE,
             created_at
             TEXT
             NOT
             NULL
         );

         CREATE TABLE IF NOT EXISTS article_tag
         (
             article_id
             TEXT
             NOT
             NULL
             REFERENCES
             articles
         (
             id
         ),
             tag_id TEXT NOT NULL REFERENCES tags
         (
             id
         ),
             PRIMARY KEY
         (
             article_id,
             tag_id
         )
             );

         CREATE INDEX IF NOT EXISTS idx_article_source ON articles(source_id);
         CREATE INDEX IF NOT EXISTS idx_article_tag_tag ON article_tag(tag_id); \
         """


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _db() as conn:
        conn.executescript(SCHEMA)
        source_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(sources)").fetchall()
        }
        if "source_summary" not in source_columns:
            conn.execute(
                "ALTER TABLE sources ADD COLUMN source_summary TEXT"
            )
        if "why_interest" in source_columns:
            conn.execute(
                """
                UPDATE sources
                SET source_summary = COALESCE(source_summary, why_interest)
                WHERE why_interest IS NOT NULL
                """
            )
        columns = {
            row[1]: row for row in conn.execute("PRAGMA table_info(articles)").fetchall()
        }
        if "n_tags" not in columns:
            conn.execute(
                "ALTER TABLE articles ADD COLUMN n_tags INTEGER NOT NULL DEFAULT 0"
            )
        if "original_type" not in columns:
            conn.execute(
                "ALTER TABLE articles ADD COLUMN original_type TEXT"
            )
        # Rebuild the table if url is still NOT NULL so Article.url can be optional.
        if columns.get("url", (None, None, None, None, 1))[3]:
            conn.commit()
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("ALTER TABLE article_tag RENAME TO article_tag_old")
            conn.execute("ALTER TABLE articles RENAME TO articles_old")
            conn.execute(
                """
                CREATE TABLE articles
                (
                    id            TEXT PRIMARY KEY,
                    source_id     TEXT    NOT NULL REFERENCES sources (id),
                    url           TEXT UNIQUE,
                    title         TEXT    NOT NULL,
                    content       TEXT    NOT NULL,
                    fetched_at    TEXT    NOT NULL,
                    category      TEXT    NOT NULL DEFAULT 'unsorted',
                    n_tags        INTEGER NOT NULL DEFAULT 0,
                    summary       TEXT,
                    original_type TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE article_tag
                (
                    article_id TEXT NOT NULL REFERENCES articles (id),
                    tag_id     TEXT NOT NULL REFERENCES tags (id),
                    PRIMARY KEY (article_id, tag_id)
                )
                """
            )
            conn.execute(
                """
                INSERT INTO articles (id, source_id, url, title, content, fetched_at, category, n_tags, summary,
                                      original_type)
                SELECT id,
                       source_id,
                       url,
                       title,
                       content,
                       fetched_at,
                       category,
                       COALESCE(n_tags, 0),
                       summary,
                       original_type
                FROM articles_old
                """
            )
            conn.execute(
                """
                INSERT INTO article_tag (article_id, tag_id)
                SELECT article_id, tag_id
                FROM article_tag_old
                """
            )
            conn.execute("DROP TABLE article_tag_old")
            conn.execute("DROP TABLE articles_old")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_article_source ON articles(source_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_article_tag_tag ON article_tag(tag_id)"
            )
            conn.commit()
            conn.execute("PRAGMA foreign_keys = ON")


def save_source(source: Source) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sources (id, name, url, type, credibility_score, source_summary) VALUES (?, ?, ?, ?, ?, ?)",
            (
                source.id,
                source.name,
                str(source.url),
                source.type.value,
                source.credibility_score,
                source.source_summary,
            ),
        )


def save_article(article: Article) -> str:
    article_url = str(article.url) if article.url is not None else None

    with _db() as conn:
        if article_url is not None:
            row = conn.execute(
                "SELECT id FROM articles WHERE url = ?",
                (article_url,),
            ).fetchone()
            if row:
                return row[0]

        conn.execute(
            """
            INSERT INTO articles (id,
                                  source_id,
                                  url,
                                  title,
                                  content,
                                  fetched_at,
                                  category,
                                  n_tags,
                                  summary,
                                  original_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                article.id,
                article.source_id,
                article_url,
                article.title,
                article.content,
                article.fetched_at.isoformat(),
                article.category.value,
                article.n_tags,
                article.summary,
                article.original_type.value if article.original_type is not None else None,
            ),
        )

        return article.id


def save_article_tags(article_id: str, tags: list[str]) -> None:
    unique_tags = list(dict.fromkeys(tags))
    with _db() as conn:
        for tag in unique_tags:
            row = conn.execute("SELECT id FROM tags WHERE name = ?", (tag,)).fetchone()
            if row:
                tag_id = row[0]
            else:
                new_tag = Tag(name=tag)
                conn.execute(
                    "INSERT INTO tags (id, name, created_at) VALUES(?,?,?)",
                    (new_tag.id, new_tag.name, new_tag.created_at.isoformat()),
                )
                tag_id = new_tag.id
            conn.execute(
                "INSERT OR IGNORE INTO article_tag (article_id, tag_id) VALUES(?, ?)",
                (article_id, tag_id),
            )
        conn.execute(
            "UPDATE articles SET n_tags = ? WHERE id = ?",
            (len(unique_tags), article_id),
        )


def get_article(article_id: str) -> dict | None:
    with _db() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, url, title, n_tags FROM articles WHERE id = ?", (article_id,)
        ).fetchone()
        return dict(row) if row else None


def list_articles(limit: int = 50) -> list[dict]:
    """Return the newest articles with the fields needed by the web list."""
    with _db() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT a.id,
                   a.title,
                   a.url,
                   a.fetched_at,
                   a.category,
                   a.n_tags,
                   s.name AS source_name
            FROM articles AS a
            LEFT JOIN sources AS s ON s.id = a.source_id
            ORDER BY a.fetched_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


_UNSET = object()


def _normalized_tags(tags: list[str]) -> list[str]:
    """Trim, remove empty values, and preserve the first occurrence of each tag."""
    return list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))


def get_article_detail(article_id: str) -> dict | None:
    """Return an article with its source metadata and tags for review screens."""
    with _db() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT a.id,
                   a.title,
                   a.url,
                   a.content,
                   a.fetched_at,
                   a.category,
                   a.n_tags,
                   a.summary,
                   a.original_type,
                   s.id AS source_id,
                   s.name AS source_name,
                   s.url AS source_url,
                   s.type AS source_type,
                   s.credibility_score,
                   s.source_summary
            FROM articles AS a
            JOIN sources AS s ON s.id = a.source_id
            WHERE a.id = ?
            """,
            (article_id,),
        ).fetchone()
        if row is None:
            return None

        tags = conn.execute(
            """
            SELECT t.name
            FROM tags AS t
            JOIN article_tag AS at ON at.tag_id = t.id
            WHERE at.article_id = ?
            ORDER BY t.name COLLATE NOCASE
            """,
            (article_id,),
        ).fetchall()

        return {
            "id": row["id"],
            "title": row["title"],
            "url": row["url"],
            "content": row["content"],
            "fetched_at": row["fetched_at"],
            "category": row["category"],
            "n_tags": row["n_tags"],
            "summary": row["summary"],
            "original_type": row["original_type"],
            "source": {
                "id": row["source_id"],
                "name": row["source_name"],
                "url": row["source_url"],
                "type": row["source_type"],
                "credibility_score": row["credibility_score"],
                "source_summary": row["source_summary"],
            },
            "tags": [tag["name"] for tag in tags],
        }


def update_article(
    article_id: str,
    *,
    title: str | object = _UNSET,
    summary: str | None | object = _UNSET,
    category: str | object = _UNSET,
    tags: list[str] | None | object = _UNSET,
) -> dict | None:
    """Apply a review edit and return the resulting article detail."""
    with _db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM articles WHERE id = ?", (article_id,)
        ).fetchone()
        if exists is None:
            return None

        columns: list[str] = []
        values: list[str | None] = []
        for column, value in (("title", title), ("summary", summary), ("category", category)):
            if value is not _UNSET:
                columns.append(f"{column} = ?")
                values.append(value)

        if columns:
            conn.execute(
                f"UPDATE articles SET {', '.join(columns)} WHERE id = ?",
                (*values, article_id),
            )

        if tags is not _UNSET:
            replacement_tags = _normalized_tags([] if tags is None else tags)
            conn.execute("DELETE FROM article_tag WHERE article_id = ?", (article_id,))
            for tag_name in replacement_tags:
                tag_row = conn.execute(
                    "SELECT id FROM tags WHERE name = ?", (tag_name,)
                ).fetchone()
                if tag_row:
                    tag_id = tag_row[0]
                else:
                    tag = Tag(name=tag_name)
                    conn.execute(
                        "INSERT INTO tags (id, name, created_at) VALUES (?, ?, ?)",
                        (tag.id, tag.name, tag.created_at.isoformat()),
                    )
                    tag_id = tag.id
                conn.execute(
                    "INSERT INTO article_tag (article_id, tag_id) VALUES (?, ?)",
                    (article_id, tag_id),
                )
            conn.execute(
                "UPDATE articles SET n_tags = ? WHERE id = ?",
                (len(replacement_tags), article_id),
            )

    return get_article_detail(article_id)


def delete_article(article_id: str) -> bool:
    """Remove an article's retrieval vectors, metadata, and tag relationships."""
    with _db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM articles WHERE id = ?", (article_id,)
        ).fetchone()
    if exists is None:
        return False

    # Remove vectors first so a successful delete cannot leave retrievable content behind.
    _chroma().delete(where={"article_id": article_id})

    with _db() as conn:
        conn.execute("DELETE FROM article_tag WHERE article_id = ?", (article_id,))
        conn.execute("DELETE FROM articles WHERE id = ?", (article_id,))
        conn.execute(
            """
            DELETE FROM tags
            WHERE NOT EXISTS (
                SELECT 1 FROM article_tag WHERE article_tag.tag_id = tags.id
            )
            """
        )
    return True


# Chroma
_chroma_client: chromadb.PersistentClient | None = None


def _chroma() -> chromadb.Collection:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return _chroma_client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


def save_chunks(chunks: list[Chunk], embeddings: list[list[float]]) -> None:
    if not chunks:
        return
    col = _chroma()
    col.add(
        ids=[c.id for c in chunks],
        embeddings=embeddings,
        documents=[c.text for c in chunks],
        metadatas=[
            {
                "article_id": c.article_id,
                "position": c.position
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
