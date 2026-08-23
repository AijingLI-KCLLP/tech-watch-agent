import unittest
from unittest.mock import patch

from core.retrieve_graph import _is_insufficient_context
from services.agent_service import ask_question


class _FakeRetrieveGraph:
    def __init__(self, results: list[dict]) -> None:
        self.results = results
        self.requests: list[dict] = []

    def invoke(self, state: dict) -> dict:
        self.requests.append(state)
        return self.results.pop(0)


class AskQuestionTest(unittest.TestCase):
    def test_recognizes_the_context_sentinel_with_harmless_formatting(self) -> None:
        self.assertTrue(_is_insufficient_context("`INSUFFICIENT_CONTEXT`."))
        self.assertFalse(_is_insufficient_context("The context is insufficient."))

    @patch("services.agent_service.init_db")
    @patch("services.agent_service.watch_topic")
    def test_ingests_question_topic_then_retries_when_context_is_missing(
        self, watch_topic, init_db
    ) -> None:
        graph = _FakeRetrieveGraph(
            [
                {"answer": "", "needs_web_search": True},
                {
                    "answer": "An NFT is a unique blockchain token [source: nft].",
                    "needs_web_search": False,
                },
            ]
        )
        with patch("services.agent_service.build_retrieve_graph", return_value=graph):
            result = ask_question("What is an NFT?")

        watch_topic.assert_called_once_with("What is an NFT?")
        self.assertEqual(graph.requests, [{"question": "What is an NFT?"}] * 2)
        self.assertEqual(
            result["answer"], "An NFT is a unique blockchain token [source: nft]."
        )

    @patch("services.agent_service.init_db")
    @patch("services.agent_service.watch_topic")
    def test_does_not_search_when_existing_context_is_sufficient(
        self, watch_topic, init_db
    ) -> None:
        graph = _FakeRetrieveGraph(
            [{"answer": "Stored answer [source: stored].", "needs_web_search": False}]
        )
        with patch("services.agent_service.build_retrieve_graph", return_value=graph):
            result = ask_question("What is already stored?")

        watch_topic.assert_not_called()
        self.assertEqual(result["answer"], "Stored answer [source: stored].")


if __name__ == "__main__":
    unittest.main()
