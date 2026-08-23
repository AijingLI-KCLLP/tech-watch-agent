import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from adapters import content
from core.models import OriginalType


class ContentAdapterTest(unittest.TestCase):
    def test_normalize_text_preserves_paragraphs(self) -> None:
        normalized = content.normalize_text(" First   paragraph.\r\n\r\n Second\tparagraph. ")

        self.assertEqual(normalized, "First paragraph.\n\nSecond paragraph.")

    def test_text_file_extraction_uses_shared_normalizer(self) -> None:
        original_type, mime_type, text = content.extract_file_content(
            b"First  line.\n\nSecond line.",
            "note.md",
            "text/markdown",
        )

        self.assertEqual(original_type, OriginalType.TEXT)
        self.assertEqual(mime_type, "text/markdown")
        self.assertEqual(text, "First line.\n\nSecond line.")

    def test_persist_upload_reuses_the_hash_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            uploads_dir = Path(temp_dir) / "data" / "uploads"
            uploads_dir.mkdir(parents=True)
            digest = content.sha256_bytes(b"raw file")

            with patch.object(content, "ROOT", Path(temp_dir)), patch.object(
                content, "UPLOADS_DIR", uploads_dir
            ):
                path = content.persist_upload(b"raw file", "note.txt", digest)

            self.assertEqual(path, f"data/uploads/{digest}.txt")
            self.assertEqual((uploads_dir / f"{digest}.txt").read_bytes(), b"raw file")

    def test_vision_mode_reports_that_no_vision_extractor_exists_yet(self) -> None:
        with patch.object(content, "IMAGE_EXTRACTION_MODE", "vision"):
            with self.assertRaisesRegex(
                content.ContentExtractionError, "not implemented yet"
            ):
                content._extract_image(b"not an image")


if __name__ == "__main__":
    unittest.main()
