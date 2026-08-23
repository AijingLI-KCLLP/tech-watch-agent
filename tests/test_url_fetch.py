import unittest
from unittest.mock import patch

from adapters import url_fetch
from core.models import OriginalType


class _Headers:
    def __init__(self, mime_type: str, charset: str | None = None) -> None:
        self.mime_type = mime_type
        self.charset = charset

    def get_content_type(self) -> str:
        return self.mime_type

    def get_content_charset(self) -> str | None:
        return self.charset


class _Response:
    def __init__(self, content: bytes, final_url: str, mime_type: str) -> None:
        self.content = content
        self.final_url = final_url
        self.headers = _Headers(mime_type)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def read(self, size: int) -> bytes:
        return self.content

    def geturl(self) -> str:
        return self.final_url


class UrlFetchTest(unittest.TestCase):
    @patch("adapters.url_fetch.urlopen")
    def test_html_url_is_normalized_from_its_content_type(self, urlopen) -> None:
        urlopen.return_value = _Response(
            b"<html><head><title>Useful article</title></head><body>First  paragraph.</body></html>",
            "https://example.com/articles/useful",
            "text/html",
        )

        fetched = url_fetch.fetch_url_content("https://example.com/articles/useful")

        self.assertEqual(fetched.original_type, OriginalType.TEXT)
        self.assertEqual(fetched.mime_type, "text/html")
        self.assertEqual(fetched.title, "Useful article")
        self.assertEqual(fetched.text, "First paragraph.")
        self.assertEqual(fetched.filename, "useful.html")

    @patch("adapters.url_fetch.extract_file_content")
    @patch("adapters.url_fetch.urlopen")
    def test_pdf_url_uses_the_file_extractor(self, urlopen, extract_file_content) -> None:
        urlopen.return_value = _Response(
            b"%PDF-raw",
            "https://example.com/report",
            "application/pdf",
        )
        extract_file_content.return_value = (
            OriginalType.PDF,
            "application/pdf",
            "Extracted report text.",
        )

        fetched = url_fetch.fetch_url_content("https://example.com/report")

        self.assertEqual(fetched.original_type, OriginalType.PDF)
        self.assertEqual(fetched.text, "Extracted report text.")
        extract_file_content.assert_called_once_with(
            b"%PDF-raw", "report.pdf", "application/pdf"
        )

    @patch("adapters.url_fetch.extract_file_content")
    @patch("adapters.url_fetch.urlopen")
    def test_image_url_uses_ocr_extraction(self, urlopen, extract_file_content) -> None:
        urlopen.return_value = _Response(
            b"image-bytes",
            "https://example.com/diagram",
            "image/png",
        )
        extract_file_content.return_value = (
            OriginalType.IMAGE,
            "image/png",
            "OCR diagram text.",
        )

        fetched = url_fetch.fetch_url_content("https://example.com/diagram")

        self.assertEqual(fetched.original_type, OriginalType.IMAGE)
        self.assertEqual(fetched.text, "OCR diagram text.")
        extract_file_content.assert_called_once_with(
            b"image-bytes", "diagram.png", "image/png"
        )


if __name__ == "__main__":
    unittest.main()
