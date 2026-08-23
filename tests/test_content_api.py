import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import app


class ContentApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    @patch("api.add_pasted_text")
    def test_pasted_text_is_forwarded_to_the_service(self, add_pasted_text) -> None:
        add_pasted_text.return_value = {
            "article": {"id": "article-1", "title": "A note", "url": None},
            "input_asset_id": "asset-1",
            "chunk_count": 2,
        }

        response = self.client.post(
            "/content/text",
            json={
                "text": "A useful note.",
                "title": "A note",
                "provided_source_url": "https://example.com/note",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["input_asset_id"], "asset-1")
        add_pasted_text.assert_called_once_with(
            text="A useful note.",
            title="A note",
            provided_source_url="https://example.com/note",
        )

    @patch("api.add_uploaded_file")
    def test_file_upload_is_forwarded_to_the_service(self, add_uploaded_file) -> None:
        add_uploaded_file.return_value = {
            "article": {"id": "article-2", "title": "Read me", "url": None},
            "input_asset_id": "asset-2",
            "chunk_count": 1,
        }

        response = self.client.post(
            "/content/file",
            data={"title": "Read me", "provided_source_url": "https://example.com"},
            files={"file": ("readme.txt", b"Some content", "text/plain")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["article"]["id"], "article-2")
        add_uploaded_file.assert_called_once_with(
            content=b"Some content",
            filename="readme.txt",
            mime_type="text/plain",
            title="Read me",
            provided_source_url="https://example.com/",
        )

    @patch("api.init_db")
    @patch("api.count_articles", return_value=21)
    @patch("api.list_articles")
    def test_articles_returns_a_paginated_response(
        self, list_articles, count_articles, init_db
    ) -> None:
        list_articles.return_value = [
            {
                "id": "article-3",
                "title": "Newest article",
                "url": None,
                "fetched_at": "2026-01-01T00:00:00+00:00",
                "category": "unsorted",
                "n_tags": 0,
                "source_name": None,
                "input_asset_id": None,
                "input_asset_original_type": None,
            }
        ]

        response = self.client.get("/articles?limit=20&offset=20")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 21)
        self.assertEqual(response.json()["offset"], 20)
        self.assertEqual(response.json()["items"][0]["title"], "Newest article")
        list_articles.assert_called_once_with(limit=20, offset=20)
        count_articles.assert_called_once_with()
        init_db.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
