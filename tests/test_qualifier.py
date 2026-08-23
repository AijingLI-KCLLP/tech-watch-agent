import unittest
from types import SimpleNamespace
from unittest.mock import patch

from adapters.qualifier import qualify_source
from core.ingest_graph import qualify_node
from core.models import Source, SourceType


class _FakeLlm:
    def __init__(self, content: str) -> None:
        self.content = content

    def invoke(self, prompt: str) -> SimpleNamespace:
        return SimpleNamespace(content=self.content)


class QualifierTest(unittest.TestCase):
    @patch(
        "adapters.qualifier.get_llm",
        return_value=_FakeLlm(
            '{"credibility_score": 0.91, "credibility_reason": "Official publisher domain."}'
        ),
    )
    def test_qualifies_source_with_score_and_reason(self, get_llm) -> None:
        qualified = qualify_source(
            Source(name="OpenAI", url="https://openai.com", type=SourceType.ARTICLE)
        )

        self.assertEqual(qualified.credibility_score, 0.91)
        self.assertEqual(qualified.credibility_reason, "Official publisher domain.")

    @patch("adapters.qualifier.get_llm", return_value=_FakeLlm("not JSON"))
    def test_invalid_model_output_leaves_source_unqualified(self, get_llm) -> None:
        source = Source(name="Unknown", url="https://example.com")

        self.assertIsNone(qualify_source(source).credibility_score)

    def test_personal_note_has_an_explanation_without_a_score(self) -> None:
        qualified = qualify_source(
            Source(
                name="Personal note",
                url="https://personal-note.invalid",
                type=SourceType.PERSONAL_NOTE,
            )
        )

        self.assertIsNone(qualified.credibility_score)
        self.assertIn("no external publisher", qualified.credibility_reason)

    @patch("core.ingest_graph.qualify_source")
    def test_watch_graph_qualifies_every_source(self, qualify) -> None:
        source = Source(name="Example", url="https://example.com")
        qualify.return_value = source.model_copy(
            update={"credibility_score": 0.5, "credibility_reason": "Community site."}
        )

        result = qualify_node({"sources": [source]})

        qualify.assert_called_once_with(source)
        self.assertEqual(result["sources"][0].credibility_score, 0.5)


if __name__ == "__main__":
    unittest.main()
