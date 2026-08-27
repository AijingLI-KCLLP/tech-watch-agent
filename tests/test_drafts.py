import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from adapters import store
from api import app
from core.models import Article, Draft, DraftFormat
from services import publish_service


class DraftStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_sqlite_path = store.SQLITE_PATH
        store.SQLITE_PATH = Path(self.temp_dir.name) / "test.db"
        store.init_db()
        self.article_ids = [
            store.save_article(Article(title="One", content="First source.")),
            store.save_article(Article(title="Two", content="Second source.")),
        ]

    def tearDown(self) -> None:
        store.SQLITE_PATH = self.previous_sqlite_path
        self.temp_dir.cleanup()

    def test_draft_keeps_ordered_source_links_and_manual_edits(self) -> None:
        draft = Draft(
            title="A local draft",
            intent="Share a practical view.",
            format=DraftFormat.POST,
            platform="LinkedIn",
            language="French",
            audience="Clients",
            objective="Explain a decision",
            tone="Clear and pragmatic",
            personal_angle="The trade-off matters.",
            source_summary="Brief.",
            generated_content="Generated.",
            content="Generated.",
        )
        store.save_draft(draft, [self.article_ids[1], self.article_ids[0]])

        listed = store.list_drafts()
        detail = store.get_draft_detail(draft.id)
        updated = store.update_draft(draft.id, content="Manually edited.")

        self.assertEqual(store.count_drafts(), 1)
        self.assertEqual(listed[0]["article_count"], 2)
        self.assertEqual([article["id"] for article in detail["articles"]], [self.article_ids[1], self.article_ids[0]])
        self.assertEqual(updated["content"], "Manually edited.")
        self.assertEqual(updated["generated_content"], "Generated.")


class PublishServiceTest(unittest.TestCase):
    @patch("services.publish_service.watch_topic")
    @patch("services.publish_service.query_chunks")
    @patch("services.publish_service.embed")
    @patch("services.publish_service.get_articles_for_draft")
    def test_intent_combines_local_retrieval_and_web_enrichment(
        self, get_articles, embed, query_chunks, watch_topic
    ) -> None:
        embed.return_value = [[0.1, 0.2]]
        query_chunks.return_value = [{"article_id": "local-1", "score": 0.9}]
        watch_topic.return_value = {
            "topic": "AI agent adoption", "article_count": 1, "chunk_count": 1,
            "articles": [{"id": "web-1", "title": "Recent source", "url": "https://example.com"}],
        }
        get_articles.return_value = [
            {"id": "local-1", "title": "Local", "content": "Saved source."},
            {"id": "web-1", "title": "Web", "content": "New source."},
        ]

        articles = publish_service._articles_for_intent("AI agent adoption", enrich_with_web=True)

        self.assertEqual([article["id"] for article in articles], ["local-1", "web-1"])
        watch_topic.assert_called_once_with("AI agent adoption")

    @patch("services.publish_service.get_draft_detail")
    @patch("services.publish_service.save_draft")
    @patch("services.publish_service.build_publish_graph")
    @patch("services.publish_service.query_chunks")
    @patch("services.publish_service.embed")
    @patch("services.publish_service.get_articles_for_draft")
    def test_create_draft_runs_the_three_step_workflow_and_persists(
        self, get_articles, embed, query_chunks, build_graph, save_draft, get_detail
    ) -> None:
        get_articles.return_value = [{"id": "a1", "title": "Source", "content": "Text"}]
        embed.return_value = [[0.1, 0.2]]
        query_chunks.return_value = [{"article_id": "a1", "score": 0.9}]
        graph = Mock()
        graph.invoke.return_value = {"source_summary": "Brief", "content": "Draft body"}
        build_graph.return_value = graph
        get_detail.return_value = {"id": "draft-1"}

        result = publish_service.create_draft(
            intent="Share a practical view.", format=DraftFormat.POST, platform="LinkedIn", language="French",
            audience="Clients", objective="Explain", tone="Direct",
            personal_angle="A practical observation.", enrich_with_web=False,
        )

        self.assertEqual(result, {"id": "draft-1"})
        self.assertEqual(graph.invoke.call_args.args[0]["articles"][0]["id"], "a1")
        self.assertEqual(graph.invoke.call_args.args[0]["intent"], "Share a practical view.")
        saved_draft, saved_ids = save_draft.call_args.args
        self.assertEqual(saved_ids, ["a1"])
        self.assertEqual(saved_draft.content, "Draft body")
        self.assertEqual(saved_draft.intent, "Share a practical view.")
        self.assertEqual(saved_draft.source_summary, "Brief")


class DraftApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    @patch("api.init_db")
    @patch("api.create_draft")
    def test_create_draft_forwards_editorial_brief(self, create_draft, init_db) -> None:
        create_draft.return_value = {
            "id": "draft-1", "title": "Draft", "intent": "Share a practical view.", "format": "post", "platform": "LinkedIn", "language": "French",
            "audience": "Clients", "objective": "Explain", "tone": "Direct",
            "personal_angle": "My take", "source_summary": "Brief", "generated_content": "Generated",
            "content": "Edited", "status": "draft", "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00", "articles": [],
        }
        payload = {"intent": "Share a practical view.", "format": "post", "platform": "LinkedIn", "language": "French", "audience": "Clients", "objective": "Explain", "tone": "Direct", "personal_angle": "My take", "enrich_with_web": False}

        response = self.client.post("/drafts", json=payload)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["id"], "draft-1")
        create_draft.assert_called_once_with(**payload)
        init_db.assert_called_once_with()

    @patch("api.init_db")
    @patch("api.update_draft")
    def test_patch_draft_persists_manual_content(self, update_draft, init_db) -> None:
        update_draft.return_value = {
            "id": "draft-1", "title": "Draft", "intent": "Share an update.", "format": "note", "platform": "none", "language": "English",
            "audience": "Peers", "objective": "Share", "tone": "Clear", "personal_angle": "My take",
            "source_summary": "Brief", "generated_content": "Generated", "content": "Manual text",
            "status": "reviewed", "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-02T00:00:00+00:00", "articles": [],
        }

        response = self.client.patch("/drafts/draft-1", json={"content": "Manual text", "status": "reviewed"})

        self.assertEqual(response.status_code, 200)
        update_draft.assert_called_once_with("draft-1", content="Manual text", status="reviewed")
        init_db.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
