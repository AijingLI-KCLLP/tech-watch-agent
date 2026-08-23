import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from adapters import store
from core.models import Article, Category
from services.agent_service import categorize_existing_articles


class CategorizeServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_sqlite_path = store.SQLITE_PATH
        store.SQLITE_PATH = Path(self.temp_dir.name) / "test.db"
        store.init_db()

    def tearDown(self) -> None:
        store.SQLITE_PATH = self.previous_sqlite_path
        self.temp_dir.cleanup()

    @patch("services.agent_service.categorize_text", return_value=Category.TECH_CODE)
    def test_backfill_only_changes_inbox_articles(self, categorize_text) -> None:
        inbox_id = store.save_article(Article(title="Inbox", content="Python code."))
        reviewed_id = store.save_article(
            Article(
                title="Reviewed",
                content="Creative writing.",
                category=Category.DESIGN_CREATIVITY,
            )
        )

        result = categorize_existing_articles()

        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(categorize_text.call_count, 1)
        self.assertEqual(
            store.get_article_detail(inbox_id)["category"],
            Category.TECH_CODE.value,
        )
        self.assertEqual(
            store.get_article_detail(reviewed_id)["category"],
            Category.DESIGN_CREATIVITY.value,
        )


if __name__ == "__main__":
    unittest.main()
