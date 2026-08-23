"""Recent technical-watch topic discovery backed by Tavily News search."""

import json
from pathlib import Path
from typing import TypedDict

from tavily import TavilyClient

from config import TAVILY_API_KEY
from core.models import Category


class DiscoveredTopic(TypedDict):
    category: str
    topic: str
    description: str
    source_url: str


_SOURCES_CONFIG_PATH = Path(__file__).parent.parent / "discovery_sources.json"


def _load_source_config() -> dict[str, dict[str, str | list[str]]]:
    """Load the versioned allowlist of trusted discovery publishers."""
    try:
        config = json.loads(_SOURCES_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Could not read discovery_sources.json.") from exc
    if not isinstance(config, dict):
        raise RuntimeError("discovery_sources.json must contain a category object.")
    return config


def discover_topics(
    categories: list[Category], *, per_category: int = 4
) -> list[DiscoveredTopic]:
    """Return recent news headlines that make useful follow-up watch queries."""
    client = TavilyClient(api_key=TAVILY_API_KEY)
    source_config = _load_source_config()
    discovered: list[DiscoveredTopic] = []
    seen: set[str] = set()

    for category in categories:
        rules = source_config.get(category.value)
        if rules is None:
            continue
        query = rules.get("query")
        domains = rules.get("domains")
        if (
            not isinstance(query, str)
            or not isinstance(domains, list)
            or not domains
            or not all(isinstance(domain, str) and domain for domain in domains)
        ):
            raise RuntimeError(
                f"Discovery source configuration for {category.value} is invalid."
            )
        response = client.search(
            query=f"latest developments {query}",
            topic="news",
            time_range="week",
            search_depth="basic",
            max_results=per_category,
            include_domains=domains,
        )
        for result in response.get("results", []):
            title = (result.get("title") or "").strip()
            url = result.get("url") or ""
            key = title.casefold()
            if not title or not url or key in seen:
                continue
            seen.add(key)
            description = " ".join((result.get("content") or "").split())
            discovered.append(
                {
                    "category": category.value,
                    "topic": title,
                    "description": description[:280],
                    "source_url": url,
                }
            )

    return discovered
