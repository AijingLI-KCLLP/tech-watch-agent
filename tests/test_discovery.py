import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from adapters.discovery import discover_topics
from adapters.discovery import _load_source_config
from api import app
from core.models import Category


class DiscoveryAdapterTest(unittest.TestCase):
    def test_checked_in_tech_code_allowlist_uses_engineering_publishers(self) -> None:
        config = _load_source_config()

        self.assertEqual(
            config["tech_code"]["domains"],
            [
                "blog.cloudflare.com",
                "netflixtechblog.com",
                "shopify.engineering",
                "slack.engineering",
                "engineering.linkedin.com",
                "stripe.dev",
                "cncf.io",
                "infoq.com",
                "spectrum.ieee.org",
                "cacm.acm.org",
                "martinfowler.com",
            ],
        )

    @patch("adapters.discovery.TavilyClient")
    @patch(
        "adapters.discovery._load_source_config",
        return_value={
            "ai_automation": {"query": "AI agents", "domains": ["openai.com"]},
            "tech_code": {"query": "developer tools", "domains": ["github.blog"]},
        },
    )
    def test_discovers_recent_topics_for_each_selected_category(
        self, source_config, tavily_client
    ) -> None:
        tavily_client.return_value.search.side_effect = [
            {
                "results": [
                    {
                        "title": "New AI agent framework launches",
                        "content": "A concise description of the launch.",
                        "url": "https://example.com/ai",
                    }
                ]
            },
            {
                "results": [
                    {
                        "title": "Developer tooling changes this week",
                        "content": "A concise development summary.",
                        "url": "https://example.com/code",
                    }
                ]
            },
        ]

        topics = discover_topics([Category.AI_AUTOMATION, Category.TECH_CODE])

        self.assertEqual([topic["category"] for topic in topics], ["ai_automation", "tech_code"])
        self.assertEqual(topics[0]["topic"], "New AI agent framework launches")
        self.assertEqual(tavily_client.return_value.search.call_count, 2)
        self.assertEqual(
            tavily_client.return_value.search.call_args_list[0].kwargs["time_range"],
            "week",
        )
        self.assertEqual(
            tavily_client.return_value.search.call_args_list[0].kwargs["topic"], "news"
        )
        self.assertEqual(
            tavily_client.return_value.search.call_args_list[0].kwargs["include_domains"],
            ["openai.com"],
        )


class DiscoveryApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    @patch("api.discover_topics")
    def test_endpoint_forwards_selected_categories(self, discover) -> None:
        discover.return_value = [
            {
                "category": "tech_code",
                "topic": "Developer tooling changes this week",
                "description": "A concise development summary.",
                "source_url": "https://example.com/code",
            }
        ]

        response = self.client.get(
            "/discover/topics?categories=tech_code&categories=ai_automation"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["category"], "tech_code")
        discover.assert_called_once_with(
            [Category.TECH_CODE, Category.AI_AUTOMATION]
        )

    @patch("api.discover_topics", return_value=[])
    def test_endpoint_uses_tech_and_ai_categories_by_default(self, discover) -> None:
        response = self.client.get("/discover/topics")

        self.assertEqual(response.status_code, 200)
        discover.assert_called_once_with(
            [Category.TECH_CODE, Category.AI_AUTOMATION]
        )


if __name__ == "__main__":
    unittest.main()
