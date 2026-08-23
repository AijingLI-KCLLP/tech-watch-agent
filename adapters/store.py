import sqlite3
import chromadb
from contextlib import contextmanager
from typing import Iterator

from config import (
    CHROMA_COLLECTION,
    CHROMA_PATH,
    SQLITE_PATH
)

from core.models import Article, Category, Chunk, InputAsset, Source, Tag

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
             credibility_reason
             TEXT,
             source_summary
             TEXT
         );

         CREATE TABLE IF NOT EXISTS articles
         (
             id
             TEXT
             PRIMARY
             KEY,
             source_id TEXT REFERENCES sources (id),
             url TEXT UNIQUE,
             title TEXT NOT NULL,
             content TEXT NOT NULL,
             fetched_at TEXT NOT NULL,
             category TEXT NOT NULL DEFAULT 'inbox',
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

INPUT_ASSET_SCHEMA = """
    CREATE TABLE IF NOT EXISTS input_assets
    (
        id                              TEXT PRIMARY KEY,
        article_id                      TEXT REFERENCES articles (id) ON DELETE CASCADE,
        original_type                   TEXT NOT NULL,
        mime_type                       TEXT NOT NULL,
        input_filename                  TEXT,
        storage_path                    TEXT,
        sha256                          TEXT NOT NULL,
        raw_text                        TEXT,
        extracted_text                  TEXT,
        provided_source_url             TEXT,
        source_verification_status      TEXT NOT NULL DEFAULT 'unverified'
                                        CHECK (source_verification_status IN (
                                            'verified', 'plausible', 'unverified', 'mismatch'
                                        )),
        source_verification_reason      TEXT,
        source_verification_confidence  REAL
                                        CHECK (
                                            source_verification_confidence IS NULL OR
                                            (source_verification_confidence >= 0 AND
                                             source_verification_confidence <= 1)
                                        ),
        verified_source_id              TEXT REFERENCES sources (id) ON DELETE SET NULL,
        created_at                      TEXT NOT NULL,
        CHECK (verified_source_id IS NULL OR source_verification_status = 'verified')
    );

    CREATE INDEX IF NOT EXISTS idx_input_asset_article ON input_assets(article_id);
    CREATE INDEX IF NOT EXISTS idx_input_asset_sha256 ON input_assets(sha256);
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
        if "credibility_reason" not in source_columns:
            conn.execute(
                "ALTER TABLE sources ADD COLUMN credibility_reason TEXT"
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
        # Old categories described personal intent, not article subject. Do not infer a topic.
        conn.execute(
            """
            UPDATE articles
            SET category = CASE category
                WHEN 'culture' THEN 'culture_society'
                ELSE 'inbox'
            END
            WHERE category IN ('unsorted', 'pro', 'perso', 'metier', 'culture')
            """
        )
        # Rebuild old article tables so both the URL and Source are optional.
        needs_article_rebuild = (
            columns.get("url", (None, None, None, None, 1))[3]
            or columns.get("source_id", (None, None, None, None, 1))[3]
        )
        if needs_article_rebuild:
            conn.commit()
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("ALTER TABLE article_tag RENAME TO article_tag_old")
            conn.execute("ALTER TABLE articles RENAME TO articles_old")
            conn.execute(
                """
                CREATE TABLE articles
                (
                    id            TEXT PRIMARY KEY,
                    source_id     TEXT REFERENCES sources (id),
                    url           TEXT UNIQUE,
                    title         TEXT    NOT NULL,
                    content       TEXT    NOT NULL,
                    fetched_at    TEXT    NOT NULL,
                    category      TEXT    NOT NULL DEFAULT 'inbox',
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

        conn.executescript(INPUT_ASSET_SCHEMA)


def save_source(source: Source) -> None:
    with _db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO sources
                (id, name, url, type, credibility_score, credibility_reason, source_summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source.id,
                source.name,
                str(source.url),
                source.type.value,
                source.credibility_score,
                source.credibility_reason,
                source.source_summary,
            ),
        )


def get_or_create_source(source: Source) -> Source:
    """Reuse one publisher Source per canonical source URL."""
    source_url = str(source.url)
    with _db() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, name, url, type, credibility_score, credibility_reason, source_summary
            FROM sources
            WHERE url = ?
            LIMIT 1
            """,
            (source_url,),
        ).fetchone()
        if row is not None:
            if (
                source.credibility_score is not None
                or source.credibility_reason is not None
            ):
                conn.execute(
                    """
                    UPDATE sources
                    SET credibility_score = COALESCE(?, credibility_score),
                        credibility_reason = COALESCE(?, credibility_reason)
                    WHERE id = ?
                    """,
                    (source.credibility_score, source.credibility_reason, row["id"]),
                )
            return Source(
                id=row["id"],
                name=row["name"],
                url=row["url"],
                type=row["type"],
                credibility_score=(
                    source.credibility_score
                    if source.credibility_score is not None
                    else row["credibility_score"]
                ),
                credibility_reason=(
                    source.credibility_reason
                    if source.credibility_reason is not None
                    else row["credibility_reason"]
                ),
                source_summary=row["source_summary"],
            )

        conn.execute(
            """
            INSERT INTO sources
                (id, name, url, type, credibility_score, credibility_reason, source_summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source.id,
                source.name,
                source_url,
                source.type.value,
                source.credibility_score,
                source.credibility_reason,
                source.source_summary,
            ),
        )
    return source


def list_sources_for_qualification() -> list[Source]:
    """Return one representative per source URL missing qualification data."""
    with _db() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, name, url, type, credibility_score, credibility_reason, source_summary
            FROM sources
            WHERE credibility_score IS NULL OR credibility_reason IS NULL
            GROUP BY url
            ORDER BY url ASC
            """
        ).fetchall()
        return [
            Source(
                id=row["id"],
                name=row["name"],
                url=row["url"],
                type=row["type"],
                credibility_score=row["credibility_score"],
                credibility_reason=row["credibility_reason"],
                source_summary=row["source_summary"],
            )
            for row in rows
        ]


def update_source_qualification(source: Source) -> int:
    """Apply one qualification to every duplicated row for the canonical URL."""
    if source.credibility_score is None or source.credibility_reason is None:
        return 0
    with _db() as conn:
        cursor = conn.execute(
            """
            UPDATE sources
            SET credibility_score = ?, credibility_reason = ?
            WHERE url = ?
            """,
            (source.credibility_score, source.credibility_reason, str(source.url)),
        )
        return cursor.rowcount


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


def save_input_asset(asset: InputAsset) -> None:
    """Persist raw-input provenance before or after it is linked to an Article."""
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO input_assets (
                id,
                article_id,
                original_type,
                mime_type,
                input_filename,
                storage_path,
                sha256,
                raw_text,
                extracted_text,
                provided_source_url,
                source_verification_status,
                source_verification_reason,
                source_verification_confidence,
                verified_source_id,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset.id,
                asset.article_id,
                asset.original_type.value,
                asset.mime_type,
                asset.input_filename,
                asset.storage_path,
                asset.sha256,
                asset.raw_text,
                asset.extracted_text,
                str(asset.provided_source_url)
                if asset.provided_source_url is not None
                else None,
                asset.source_verification_status.value,
                asset.source_verification_reason,
                asset.source_verification_confidence,
                asset.verified_source_id,
                asset.created_at.isoformat(),
            ),
        )


def link_input_asset_to_article(asset_id: str, article_id: str) -> None:
    """Attach previously persisted raw-input provenance to its normalized Article."""
    with _db() as conn:
        cursor = conn.execute(
            "UPDATE input_assets SET article_id = ? WHERE id = ?",
            (article_id, asset_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"Input asset not found: {asset_id}")


def list_input_assets(article_id: str) -> list[dict]:
    """Return raw-input provenance for an Article review screen."""
    with _db() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id,
                   article_id,
                   original_type,
                   mime_type,
                   input_filename,
                   storage_path,
                   sha256,
                   raw_text,
                   extracted_text,
                   provided_source_url,
                   source_verification_status,
                   source_verification_reason,
                   source_verification_confidence,
                   verified_source_id,
                   created_at
            FROM input_assets
            WHERE article_id = ?
            ORDER BY created_at ASC
            """,
            (article_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def save_article_tags(
    article_id: str, tags: list[str], *, replace: bool = False
) -> int:
    """Add tags without replacing existing links and return the number added."""
    unique_tags = _normalized_tags(tags)
    added_links = 0
    with _db() as conn:
        if replace:
            conn.execute("DELETE FROM article_tag WHERE article_id = ?", (article_id,))
        for tag in unique_tags:
            row = conn.execute(
                "SELECT id FROM tags WHERE name = ? COLLATE NOCASE", (tag,)
            ).fetchone()
            if row:
                tag_id = row[0]
            else:
                new_tag = Tag(name=tag)
                conn.execute(
                    "INSERT INTO tags (id, name, created_at) VALUES(?,?,?)",
                    (new_tag.id, new_tag.name, new_tag.created_at.isoformat()),
                )
                tag_id = new_tag.id
            cursor = conn.execute(
                "INSERT OR IGNORE INTO article_tag (article_id, tag_id) VALUES(?, ?)",
                (article_id, tag_id),
            )
            added_links += cursor.rowcount
        conn.execute(
            """
            UPDATE articles
            SET n_tags = (
                SELECT COUNT(*) FROM article_tag WHERE article_id = ?
            )
            WHERE id = ?
            """,
            (article_id, article_id),
        )
    return added_links


def get_article(article_id: str) -> dict | None:
    with _db() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, url, title, n_tags FROM articles WHERE id = ?", (article_id,)
        ).fetchone()
        return dict(row) if row else None


def count_articles() -> int:
    with _db() as conn:
        return conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]


def list_articles(limit: int = 50, offset: int = 0) -> list[dict]:
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
                   s.name AS source_name,
                   ia.id AS input_asset_id,
                   ia.original_type AS input_asset_original_type
            FROM articles AS a
            LEFT JOIN sources AS s ON s.id = a.source_id
            LEFT JOIN input_assets AS ia ON ia.id = (
                SELECT id
                FROM input_assets
                WHERE article_id = a.id AND storage_path IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 1
            )
            ORDER BY a.fetched_at DESC, a.id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        articles = [dict(row) for row in rows]
        for article in articles:
            tags = conn.execute(
                """
                SELECT t.name
                FROM tags AS t
                JOIN article_tag AS at ON at.tag_id = t.id
                WHERE at.article_id = ?
                ORDER BY t.name COLLATE NOCASE ASC
                """,
                (article["id"],),
            ).fetchall()
            unique_tags: list[str] = []
            seen_tags: set[str] = set()
            for tag in tags:
                name = tag[0]
                if name.casefold() in seen_tags:
                    continue
                unique_tags.append(name)
                seen_tags.add(name.casefold())
            article["tags"] = unique_tags
            article["n_tags"] = len(unique_tags)
        return articles


def list_articles_for_categorization(*, only_inbox: bool = True) -> list[dict]:
    """Return the content required for an LLM categorization pass."""
    where_clause = "WHERE category = 'inbox'" if only_inbox else ""
    with _db() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT id, title, content, category
            FROM articles
            {where_clause}
            ORDER BY fetched_at ASC, id ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def list_articles_for_tagging() -> list[dict]:
    """Return article text for an LLM tag backfill."""
    with _db() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, title, content
            FROM articles
            ORDER BY fetched_at ASC, id ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def update_article_category(article_id: str, category: Category) -> bool:
    """Persist an automated category decision without altering manual metadata."""
    with _db() as conn:
        cursor = conn.execute(
            "UPDATE articles SET category = ? WHERE id = ?",
            (category.value, article_id),
        )
        return cursor.rowcount == 1


def get_input_asset_file(asset_id: str) -> dict | None:
    """Return the stored-file metadata for an InputAsset without exposing it publicly."""
    with _db() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT storage_path, mime_type, input_filename
            FROM input_assets
            WHERE id = ? AND storage_path IS NOT NULL
            """,
            (asset_id,),
        ).fetchone()
        return dict(row) if row else None


_UNSET = object()


def _normalized_tags(tags: list[str]) -> list[str]:
    """Trim, remove empty values, and preserve the first occurrence of each tag."""
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        value = tag.strip()
        key = value.casefold()
        if not value or key in seen:
            continue
        normalized.append(value)
        seen.add(key)
    return normalized


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
                   s.credibility_reason,
                   s.source_summary
            FROM articles AS a
            LEFT JOIN sources AS s ON s.id = a.source_id
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

        source = None
        if row["source_id"] is not None:
            source = {
                "id": row["source_id"],
                "name": row["source_name"],
                "url": row["source_url"],
                "type": row["source_type"],
                "credibility_score": row["credibility_score"],
                "credibility_reason": row["credibility_reason"],
                "source_summary": row["source_summary"],
            }

        unique_tags: list[str] = []
        seen_tags: set[str] = set()
        for tag in tags:
            name = tag["name"]
            if name.casefold() in seen_tags:
                continue
            unique_tags.append(name)
            seen_tags.add(name.casefold())

        return {
            "id": row["id"],
            "title": row["title"],
            "url": row["url"],
            "content": row["content"],
            "fetched_at": row["fetched_at"],
            "category": row["category"],
            "n_tags": len(unique_tags),
            "summary": row["summary"],
            "original_type": row["original_type"],
            "source": source,
            "tags": unique_tags,
            "input_assets": list_input_assets(article_id),
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
                    "SELECT id FROM tags WHERE name = ? COLLATE NOCASE", (tag_name,)
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
