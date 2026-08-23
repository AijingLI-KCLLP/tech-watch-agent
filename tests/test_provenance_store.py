import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from adapters import store
from core.models import Article, Category, InputAsset, OriginalType, Source


class ProvenanceStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_sqlite_path = store.SQLITE_PATH
        store.SQLITE_PATH = Path(self.temp_dir.name) / "test.db"
        store.init_db()

    def tearDown(self) -> None:
        store.SQLITE_PATH = self.previous_sqlite_path
        self.temp_dir.cleanup()

    def test_input_asset_can_be_linked_to_an_article_without_a_source(self) -> None:
        article = Article(title="Pasted note", content="Useful source-less content.")
        article_id = store.save_article(article)
        asset = InputAsset(
            article_id=article_id,
            original_type=OriginalType.TEXT,
            mime_type="text/plain",
            sha256="a" * 64,
            raw_text="Useful source-less content.",
            extracted_text="Useful source-less content.",
        )
        store.save_input_asset(asset)

        detail = store.get_article_detail(article_id)

        self.assertIsNotNone(detail)
        self.assertIsNone(detail["source"])
        self.assertEqual(detail["input_assets"][0]["id"], asset.id)
        self.assertEqual(
            detail["input_assets"][0]["source_verification_status"],
            "unverified",
        )

    def test_article_source_column_is_nullable(self) -> None:
        with store._db() as conn:
            columns = {
                row[1]: row for row in conn.execute("PRAGMA table_info(articles)")
            }

        self.assertEqual(columns["source_id"][3], 0)

    def test_article_list_includes_the_latest_uploaded_asset(self) -> None:
        article = Article(title="Architecture diagram", content="A diagram description.")
        article_id = store.save_article(article)
        asset = InputAsset(
            article_id=article_id,
            original_type=OriginalType.IMAGE,
            mime_type="image/png",
            input_filename="diagram.png",
            storage_path="data/uploads/diagram.png",
            sha256="b" * 64,
            extracted_text="Architecture diagram.",
        )
        store.save_input_asset(asset)

        listed = store.list_articles()

        self.assertEqual(listed[0]["input_asset_id"], asset.id)
        self.assertEqual(listed[0]["input_asset_original_type"], "image")

    def test_article_list_supports_limit_and_offset(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for index in range(3):
            store.save_article(
                Article(
                    title=f"Article {index}",
                    content="Content.",
                    fetched_at=start + timedelta(minutes=index),
                )
            )

        listed = store.list_articles(limit=1, offset=1)

        self.assertEqual(store.count_articles(), 3)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["title"], "Article 1")

    def test_categorization_queries_inbox_by_default(self) -> None:
        inbox_id = store.save_article(Article(title="Inbox", content="Content."))
        reviewed_id = store.save_article(
            Article(
                title="Reviewed",
                content="Content.",
                category=Category.TECH_CODE,
            )
        )

        articles = store.list_articles_for_categorization()

        self.assertEqual([article["id"] for article in articles], [inbox_id])
        self.assertTrue(store.update_article_category(inbox_id, Category.LEARNING_LIFE))
        self.assertEqual(
            store.get_article_detail(inbox_id)["category"],
            Category.LEARNING_LIFE.value,
        )
        self.assertEqual(
            store.get_article_detail(reviewed_id)["category"],
            Category.TECH_CODE.value,
        )

    def test_get_or_create_source_reuses_the_canonical_url(self) -> None:
        source = Source(
            name="example.com",
            url="https://example.com",
            credibility_score=0.8,
            credibility_reason="Established publisher.",
        )

        first = store.get_or_create_source(source)
        second = store.get_or_create_source(
            Source(name="Example", url="https://example.com")
        )

        self.assertEqual(first.id, second.id)
        self.assertEqual(second.credibility_score, 0.8)
        self.assertEqual(second.credibility_reason, "Established publisher.")

    def test_legacy_intent_categories_are_migrated_to_inbox(self) -> None:
        article = Article(title="Existing article", content="Existing content.")
        article_id = store.save_article(article)
        with store._db() as conn:
            conn.execute("UPDATE articles SET category = 'pro' WHERE id = ?", (article_id,))

        store.init_db()
        detail = store.get_article_detail(article_id)

        self.assertEqual(detail["category"], "inbox")

    def test_legacy_migration_preserves_articles(self) -> None:
        legacy_schema = store.SCHEMA.replace(
            "source_id TEXT REFERENCES sources (id),",
            "source_id TEXT NOT NULL REFERENCES sources (id),",
        )
        with store._db() as conn:
            conn.executescript(
                """
                DROP TABLE input_assets;
                DROP TABLE article_tag;
                DROP TABLE tags;
                DROP TABLE articles;
                DROP TABLE sources;
                """
            )
            conn.executescript(legacy_schema)

        source = Source(name="example.com", url="https://example.com")
        store.save_source(source)
        article = Article(
            source_id=source.id,
            title="Legacy article",
            content="Existing content must survive the migration.",
        )
        article_id = store.save_article(article)

        store.init_db()
        detail = store.get_article_detail(article_id)

        self.assertIsNotNone(detail)
        self.assertEqual(detail["title"], "Legacy article")
        self.assertEqual(detail["source"]["id"], source.id)


if __name__ == "__main__":
    unittest.main()
