"""LLM-backed, bounded tag generation for saved articles."""

import json
import re

from adapters.llm import get_llm
from adapters.prompts import render_prompt
from core.models import Article


MAX_CONTENT_CHARS = 8_000
MAX_TAGS = 5
MAX_TAG_CHARS = 60


def _parse_tags(response: object) -> list[str]:
    """Return only a small, clean tag list from the model's JSON response."""
    content = str(getattr(response, "content", response)).strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if match is None:
        return []

    try:
        payload = json.loads(match.group())
        values = payload["tags"]
    except (KeyError, TypeError, json.JSONDecodeError):
        return []

    if not isinstance(values, list):
        return []

    tags: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        tag = re.sub(r"\s+", " ", value).strip().lower()
        if not tag or len(tag) > MAX_TAG_CHARS or tag in tags:
            continue
        tags.append(tag)
        if len(tags) == MAX_TAGS:
            break
    return tags


def tag_text(title: str, content: str) -> list[str]:
    """Classify an article with a few broad, distinct library tags."""
    prompt = render_prompt(
        "tag",
        max_tags=MAX_TAGS,
        title=title[:500],
        content=content[:MAX_CONTENT_CHARS],
    )
    return _parse_tags(get_llm().invoke(prompt))


def tag_article(article: Article) -> list[str]:
    """Generate advisory tags without allowing an LLM failure to block ingest."""
    try:
        return tag_text(article.title, article.content)
    except Exception:
        return []
