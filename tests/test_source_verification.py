import unittest
from unittest.mock import patch

from adapters import source_verification
from core.models import SourceVerificationStatus


class SourceVerificationTest(unittest.TestCase):
    input_text = "Continuous integration automatically builds tests and deploys software changes."
    input_title = "What CI/CD means"

    @patch("adapters.source_verification._fetch_source_content")
    def test_provided_source_is_verified_for_a_strong_text_match(self, fetch) -> None:
        fetch.return_value = (
            "https://example.com/ci-cd",
            self.input_title,
            self.input_text,
        )

        result = source_verification.verify_provided_source(
            input_text=self.input_text,
            input_title=self.input_title,
            source_url="https://example.com/ci-cd",
        )

        self.assertEqual(result.status, SourceVerificationStatus.VERIFIED)
        self.assertIsNotNone(result.source)
        self.assertEqual(result.article_url, "https://example.com/ci-cd")

    @patch("adapters.source_verification._fetch_source_content")
    def test_provided_source_is_plausible_for_a_title_only_match(self, fetch) -> None:
        fetch.return_value = (
            "https://example.com/ci-cd",
            self.input_title,
            "A different page with no overlapping content.",
        )

        result = source_verification.verify_provided_source(
            input_text=self.input_text,
            input_title=self.input_title,
            source_url="https://example.com/ci-cd",
        )

        self.assertEqual(result.status, SourceVerificationStatus.PLAUSIBLE)
        self.assertIsNone(result.source)

    @patch("adapters.source_verification._fetch_source_content")
    def test_provided_source_is_a_mismatch_for_unrelated_content(self, fetch) -> None:
        fetch.return_value = (
            "https://example.com/food",
            "Pasta recipes",
            "A recipe for tomato pasta and fresh basil.",
        )

        result = source_verification.verify_provided_source(
            input_text=self.input_text,
            input_title=self.input_title,
            source_url="https://example.com/food",
        )

        self.assertEqual(result.status, SourceVerificationStatus.MISMATCH)
        self.assertIsNone(result.source)

    @patch("adapters.source_verification._fetch_source_content")
    def test_provided_source_is_unverified_when_it_cannot_be_fetched(self, fetch) -> None:
        fetch.side_effect = source_verification.ContentExtractionError("Connection refused")

        result = source_verification.verify_provided_source(
            input_text=self.input_text,
            input_title=self.input_title,
            source_url="https://example.com/unavailable",
        )

        self.assertEqual(result.status, SourceVerificationStatus.UNVERIFIED)
        self.assertIsNone(result.confidence)

    @patch("adapters.source_verification._search_candidates")
    def test_source_search_returns_a_verified_match(self, search_candidates) -> None:
        search_candidates.return_value = [
            {
                "url": "https://example.com/ci-cd",
                "title": self.input_title,
                "raw_content": self.input_text,
            }
        ]

        result = source_verification.find_source(
            input_text=self.input_text,
            input_title=self.input_title,
        )

        self.assertEqual(result.status, SourceVerificationStatus.VERIFIED)
        self.assertEqual(result.article_url, "https://example.com/ci-cd")


if __name__ == "__main__":
    unittest.main()
