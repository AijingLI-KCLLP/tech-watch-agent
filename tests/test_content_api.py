import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import app
from services import article_review_service


class ContentApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    @patch("api.add_pasted_text")
    def test_pasted_text_is_forwarded_to_the_service(self, add_pasted_text) -> None:
        add_pasted_text.return_value = {
            "article": {"id": "article-1", "title": "A note", "url": None},
            "input_asset_id": "asset-1",
            "chunk_count": 2,
            "source_verification_status": "unverified",
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
            "source_verification_status": "verified",
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

    @patch("api.add_article_by_url")
    def test_article_url_is_forwarded_to_the_service(self, add_article_by_url) -> None:
        add_article_by_url.return_value = {
            "article": {"id": "article-3", "title": "A URL article", "url": "https://example.com/article"},
            "input_asset_id": "asset-3",
            "chunk_count": 1,
            "source_verification_status": "verified",
        }

        response = self.client.post(
            "/content/url",
            json={"url": "https://example.com/article", "title": "A URL article"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["article"]["url"], "https://example.com/article")
        add_article_by_url.assert_called_once_with(
            url="https://example.com/article",
            title="A URL article",
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
                "category": "inbox",
                "n_tags": 0,
                "tags": [],
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


class ArticleReviewServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    @patch("services.article_review_service.update_article")
    @patch("adapters.store._chroma")
    @patch("services.article_review_service.save_chunks")
    @patch("services.article_review_service.embed", return_value=[[0.1, 0.2]])
    @patch(
        "services.article_review_service.get_article_detail",
        return_value={"id": "article-4"},
    )
    def test_content_edit_replaces_retrieval_chunks(
        self, get_detail, embed, save_chunks, chroma, update_article
    ) -> None:
        update_article.return_value = {"id": "article-4", "content": "Edited text."}

        result = article_review_service.edit_article(
            "article-4", content="Edited text."
        )

        self.assertEqual(result["content"], "Edited text.")
        chroma.return_value.delete.assert_called_once_with(where={"article_id": "article-4"})
        save_chunks.assert_called_once()
        chunks, embeddings = save_chunks.call_args.args
        self.assertEqual([chunk.text for chunk in chunks], ["Edited text."])
        self.assertEqual(embeddings, [[0.1, 0.2]])
        update_article.assert_called_once_with("article-4", content="Edited text.")
        get_detail.assert_called_once_with("article-4")

    @patch("api.init_db")
    @patch("api.update_article")
    def test_article_patch_accepts_normalized_content(self, update_article, init_db) -> None:
        update_article.return_value = {
            "id": "article-4",
            "title": "Reviewed article",
            "url": None,
            "content": "Edited normalized content.",
            "fetched_at": "2026-01-01T00:00:00+00:00",
            "category": "tech_code",
            "n_tags": 1,
            "summary": None,
            "original_type": "text",
            "source": None,
            "tags": ["reviewed"],
            "input_assets": [],
        }

        response = self.client.patch(
            "/articles/article-4",
            json={
                "title": "Reviewed article",
                "content": "Edited normalized content.",
                "category": "tech_code",
                "tags": ["reviewed"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"], "Edited normalized content.")
        update_article.assert_called_once_with(
            "article-4",
            title="Reviewed article",
            content="Edited normalized content.",
            category="tech_code",
            tags=["reviewed"],
        )
        init_db.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
