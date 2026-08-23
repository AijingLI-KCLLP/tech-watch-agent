import unittest
from types import SimpleNamespace
from unittest.mock import patch

from adapters.tagger import tag_article, tag_text
from core.content_ingest_graph import tag_node as tag_content_node
from core.ingest_graph import store_node as watch_store_node
from core.ingest_graph import tag_node as tag_ingest_node
from core.models import Article


class _FakeLlm:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> SimpleNamespace:
        self.prompts.append(prompt)
        return SimpleNamespace(content=self.response)


class TaggerTest(unittest.TestCase):
    @patch(
        "adapters.tagger.get_llm",
        return_value=_FakeLlm('{"tags": ["Python", "developer tools", "Developer Tools", "CI/CD", "ci/cd"]}'),
    )
    def test_generates_normalized_deduplicated_tags(self, get_llm) -> None:
        tags = tag_text("Python release", "New compiler features.")

        self.assertEqual(tags, ["python", "developer tools", "ci/cd"])
        prompt = get_llm.return_value.prompts[0]
        self.assertIn("Python release", prompt)
        self.assertIn("senior developer", prompt)
        self.assertIn("your notes", prompt)
        self.assertIn("Case is irrelevant", prompt)

    @patch("adapters.tagger.get_llm", return_value=_FakeLlm("python, compiler"))
    def test_rejects_malformed_model_output(self, get_llm) -> None:
        self.assertEqual(tag_text("Python", "Compiler"), [])

    @patch("adapters.tagger.get_llm", side_effect=ConnectionError)
    def test_article_tagger_ignores_llm_failure(self, get_llm) -> None:
        self.assertEqual(tag_article(Article(title="Python", content="Compiler")), [])

    @patch("core.ingest_graph.tag_article", return_value=["ai agents"])
    def test_watch_graph_tags_each_article(self, tag) -> None:
        articles = [
            Article(title="Agents", content="Agent orchestration."),
            Article(title="Tools", content="Tool use."),
        ]

        result = tag_ingest_node({"articles": articles})

        self.assertEqual(tag.call_count, 2)
        self.assertEqual(
            result["article_tags"],
            {article.id: ["ai agents"] for article in articles},
        )

    @patch("core.content_ingest_graph.tag_article", return_value=["design systems"])
    def test_content_graph_tags_its_article(self, tag) -> None:
        article = Article(title="Design", content="Design-system notes.")

        result = tag_content_node({"article": article})

        tag.assert_called_once_with(article)
        self.assertEqual(result["tags"], ["design systems"])

    @patch("core.ingest_graph.save_chunks")
    @patch("core.ingest_graph.save_article_tags")
    @patch("core.ingest_graph.save_article", return_value="persisted-1")
    @patch("core.ingest_graph.save_source")
    def test_watch_store_keeps_topic_and_avoids_a_duplicate_generated_tag(
        self, save_source, save_article, save_article_tags, save_chunks
    ) -> None:
        article = Article(title="Agents", content="Agent orchestration.")

        watch_store_node(
            {
                "topic": "AI Agents",
                "sources": [],
                "articles": [article],
                "article_tags": {article.id: ["ai agents", "tool use"]},
                "chunks": [],
                "embeddings": [],
            }
        )

        save_article_tags.assert_called_once_with(
            "persisted-1", ["AI Agents", "tool use"]
        )


if __name__ == "__main__":
    unittest.main()
