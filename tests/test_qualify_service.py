import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from adapters import store
from core.models import Source
from services.agent_service import qualify_existing_sources


class QualifyServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_sqlite_path = store.SQLITE_PATH
        store.SQLITE_PATH = Path(self.temp_dir.name) / "test.db"
        store.init_db()

    def tearDown(self) -> None:
        store.SQLITE_PATH = self.previous_sqlite_path
        self.temp_dir.cleanup()

    @patch("services.agent_service.qualify_source")
    def test_backfill_qualifies_once_per_url_and_updates_duplicates(self, qualify) -> None:
        store.save_source(Source(name="Example", url="https://example.com"))
        store.save_source(Source(name="Example duplicate", url="https://example.com"))
        store.save_source(Source(name="Other", url="https://other.example.com"))

        def qualified_source(source: Source) -> Source:
            return source.model_copy(
                update={
                    "credibility_score": 0.75,
                    "credibility_reason": "Established publisher.",
                }
            )

        qualify.side_effect = qualified_source

        result = qualify_existing_sources()

        self.assertEqual(result["processed"], 2)
        self.assertEqual(result["qualified_sources"], 2)
        self.assertEqual(result["updated_rows"], 3)
        self.assertEqual(qualify.call_count, 2)
        with store._db() as conn:
            rows = conn.execute(
                "SELECT credibility_score, credibility_reason FROM sources"
            ).fetchall()
        self.assertEqual(rows, [(0.75, "Established publisher.")] * 3)


if __name__ == "__main__":
    unittest.main()
