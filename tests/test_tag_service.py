import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from adapters import store
from core.models import Article
from services.agent_service import tag_existing_articles


class TagServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_sqlite_path = store.SQLITE_PATH
        store.SQLITE_PATH = Path(self.temp_dir.name) / "test.db"
        store.init_db()

    def tearDown(self) -> None:
        store.SQLITE_PATH = self.previous_sqlite_path
        self.temp_dir.cleanup()

    @patch("services.agent_service.tag_text", return_value=["python", "compilers"])
    def test_backfill_adds_tags_without_replacing_existing_ones(self, tag_text) -> None:
        article_id = store.save_article(Article(title="Python", content="Compiler news."))
        store.save_article_tags(article_id, ["topic"])

        result = tag_existing_articles()

        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["generated_tags"], 2)
        self.assertEqual(result["added_tag_links"], 2)
        self.assertEqual(
            store.get_article_detail(article_id)["tags"],
            ["compilers", "python", "topic"],
        )
        tag_text.assert_called_once_with("Python", "Compiler news.")

    @patch("services.agent_service.tag_text", return_value=["python"])
    def test_dry_run_does_not_write_tags(self, tag_text) -> None:
        article_id = store.save_article(Article(title="Python", content="Compiler news."))

        result = tag_existing_articles(dry_run=True)

        self.assertEqual(result["generated_tags"], 1)
        self.assertEqual(result["added_tag_links"], 0)
        self.assertEqual(store.get_article_detail(article_id)["tags"], [])

    @patch("services.agent_service.tag_text", return_value=["software delivery"])
    def test_replace_removes_existing_tags(self, tag_text) -> None:
        article_id = store.save_article(Article(title="CI/CD", content="Pipeline notes."))
        store.save_article_tags(article_id, ["CI/CD", "ci/cd", "devops automation"])

        result = tag_existing_articles(replace=True)

        self.assertEqual(result["added_tag_links"], 1)
        self.assertEqual(store.get_article_detail(article_id)["tags"], ["software delivery"])

    def test_tag_names_are_case_insensitive(self) -> None:
        article_id = store.save_article(Article(title="CI/CD", content="Pipeline notes."))

        store.save_article_tags(article_id, ["CI/CD", "ci/cd", "Ci/Cd"])

        detail = store.get_article_detail(article_id)
        self.assertEqual(detail["n_tags"], 1)
        self.assertEqual(detail["tags"], ["CI/CD"])


if __name__ == "__main__":
    unittest.main()
