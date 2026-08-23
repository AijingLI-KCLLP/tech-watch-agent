import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from adapters import store
from adapters.source_verification import SourceVerification, personal_note_source
from adapters.url_fetch import FetchedUrlContent
from core.models import InputAsset, OriginalType, Source, SourceType, SourceVerificationStatus
from services import agent_service


class _FakeContentGraph:
    def invoke(self, state: dict) -> dict:
        article_id = store.save_article(state["article"])
        store.link_input_asset_to_article(state["input_asset"].id, article_id)
        return {"persisted_article_id": article_id, "chunks": []}


class SourceServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_sqlite_path = store.SQLITE_PATH
        store.SQLITE_PATH = Path(self.temp_dir.name) / "test.db"

    def tearDown(self) -> None:
        store.SQLITE_PATH = self.previous_sqlite_path
        self.temp_dir.cleanup()

    def _asset(self) -> InputAsset:
        return InputAsset(
            original_type=OriginalType.PDF,
            mime_type="application/pdf",
            input_filename="report.pdf",
            storage_path="data/uploads/report.pdf",
            sha256="c" * 64,
            extracted_text="A report about release automation.",
        )

    @patch("services.agent_service.build_content_ingest_graph", return_value=_FakeContentGraph())
    def test_verified_source_is_created_and_linked(self, build_graph) -> None:
        source = Source(name="example.com", url="https://example.com")
        result = agent_service._ingest_normalized_content(
            normalized_text="A report about release automation.",
            input_asset=self._asset(),
            title="Release automation",
            verification=SourceVerification(
                status=SourceVerificationStatus.VERIFIED,
                reason="Strong match.",
                confidence=0.9,
                source=source,
                article_url="https://example.com/report",
            ),
        )

        detail = store.get_article_detail(result["article"]["id"])

        self.assertEqual(result["source_verification_status"], "verified")
        self.assertEqual(detail["source"]["url"], "https://example.com/")
        self.assertEqual(detail["url"], "https://example.com/report")
        self.assertEqual(detail["input_assets"][0]["verified_source_id"], source.id)

    @patch("services.agent_service.build_content_ingest_graph", return_value=_FakeContentGraph())
    def test_plausible_source_does_not_create_or_link_a_source(self, build_graph) -> None:
        asset = self._asset()
        asset.source_verification_status = SourceVerificationStatus.PLAUSIBLE
        asset.source_verification_reason = "Partial match."
        asset.source_verification_confidence = 0.3
        result = agent_service._ingest_normalized_content(
            normalized_text="A report about release automation.",
            input_asset=asset,
            title="Release automation",
            verification=SourceVerification(
                status=SourceVerificationStatus.PLAUSIBLE,
                reason="Partial match.",
                confidence=0.3,
            ),
        )

        detail = store.get_article_detail(result["article"]["id"])

        self.assertIsNone(detail["source"])
        self.assertIsNone(detail["input_assets"][0]["verified_source_id"])

    @patch("services.agent_service.build_content_ingest_graph", return_value=_FakeContentGraph())
    def test_unverified_upload_without_a_url_uses_personal_note(self, build_graph) -> None:
        result = agent_service._ingest_normalized_content(
            normalized_text="A report about release automation.",
            input_asset=self._asset(),
            title="Release automation",
            verification=SourceVerification(
                status=SourceVerificationStatus.UNVERIFIED,
                reason="No source found.",
                confidence=None,
            ),
            fallback_source=personal_note_source(),
        )

        detail = store.get_article_detail(result["article"]["id"])

        self.assertEqual(detail["source"]["name"], "Personal note")
        self.assertEqual(detail["source"]["type"], SourceType.PERSONAL_NOTE.value)
        self.assertIsNone(detail["input_assets"][0]["verified_source_id"])

    @patch("services.agent_service.persist_upload", return_value="data/uploads/article.html")
    @patch("services.agent_service.fetch_url_content")
    @patch("services.agent_service.build_content_ingest_graph", return_value=_FakeContentGraph())
    def test_direct_url_creates_a_verified_source_and_raw_asset(
        self, build_graph, fetch_url_content, persist_upload
    ) -> None:
        fetch_url_content.return_value = FetchedUrlContent(
            requested_url="https://example.com/article",
            final_url="https://example.com/article",
            filename="article.html",
            mime_type="text/html",
            original_type=OriginalType.TEXT,
            title="An article",
            text="An extracted article.",
            content=b"<html>An extracted article.</html>",
        )

        result = agent_service.add_article_by_url("https://example.com/article")

        detail = store.get_article_detail(result["article"]["id"])

        self.assertEqual(result["source_verification_status"], "verified")
        self.assertEqual(detail["url"], "https://example.com/article")
        self.assertEqual(detail["source"]["name"], "example.com")
        self.assertEqual(detail["input_assets"][0]["mime_type"], "text/html")
        self.assertEqual(detail["input_assets"][0]["provided_source_url"], "https://example.com/article")


if __name__ == "__main__":
    unittest.main()
