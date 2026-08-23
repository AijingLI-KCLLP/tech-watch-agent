import unittest
from types import SimpleNamespace
from unittest.mock import patch

from adapters.categorizer import categorize_text
from core.content_ingest_graph import categorize_node as categorize_content_node
from core.ingest_graph import categorize_node as categorize_ingest_node
from core.models import Article, Category


class _FakeLlm:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> SimpleNamespace:
        self.prompts.append(prompt)
        return SimpleNamespace(content=self.response)


class CategorizerTest(unittest.TestCase):
    @patch("adapters.categorizer.get_llm", return_value=_FakeLlm("tech_code"))
    def test_categorizes_to_a_valid_category(self, get_llm) -> None:
        category = categorize_text("Python release", "New Python compiler features.")

        self.assertEqual(category, Category.TECH_CODE)
        prompt = get_llm.return_value.prompts[0]
        self.assertIn("Python release", prompt)
        self.assertIn("Ansible", prompt)
        self.assertIn("primary subject and reader intent", prompt)
        self.assertIn("Output exactly one", prompt)

    @patch("adapters.categorizer.get_llm", return_value=_FakeLlm("technology"))
    def test_invalid_model_output_stays_in_inbox(self, get_llm) -> None:
        self.assertEqual(
            categorize_text("Unknown", "Unclear content."),
            Category.INBOX,
        )

    @patch(
        "adapters.categorizer.get_llm",
        return_value=_FakeLlm("The primary category is: `product_business`."),
    )
    def test_unambiguous_verbose_model_output_is_accepted(self, get_llm) -> None:
        self.assertEqual(
            categorize_text("Market update", "Startup funding news."),
            Category.PRODUCT_BUSINESS,
        )

    @patch("core.ingest_graph.categorize_article", return_value=Category.AI_AUTOMATION)
    def test_watch_graph_node_categorizes_every_article(self, categorize) -> None:
        articles = [
            Article(title="Agents", content="Agent orchestration."),
            Article(title="Tools", content="Tool use."),
        ]

        result = categorize_ingest_node({"articles": articles})

        self.assertEqual(categorize.call_count, 2)
        self.assertEqual(
            [article.category for article in result["articles"]],
            [Category.AI_AUTOMATION, Category.AI_AUTOMATION],
        )

    @patch(
        "core.content_ingest_graph.categorize_article",
        return_value=Category.DESIGN_CREATIVITY,
    )
    def test_content_graph_node_categorizes_its_article(self, categorize) -> None:
        article = Article(title="Design", content="Design-system notes.")

        result = categorize_content_node({"article": article})

        categorize.assert_called_once_with(article)
        self.assertEqual(result["article"].category, Category.DESIGN_CREATIVITY)


if __name__ == "__main__":
    unittest.main()
