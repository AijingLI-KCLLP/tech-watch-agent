"""LLM-backed subject categorization with a closed Category vocabulary."""

import re

from adapters.llm import get_llm
from adapters.prompts import render_prompt
from core.models import Article, Category


MAX_CONTENT_CHARS = 8_000

def _parse_category(response: object) -> Category:
    """Accept only an exact enum value; malformed model output remains in inbox."""
    content = getattr(response, "content", response)
    value = str(content).strip().lower().strip("`").strip()
    try:
        return Category(value)
    except ValueError:
        # Some local models add a short explanation despite the output constraint.
        # Accept one unambiguous category token, but never guess from a mixed response.
        matches = {
            category.value
            for category in Category
            if re.search(rf"\b{re.escape(category.value)}\b", value)
        }
        return Category(matches.pop()) if len(matches) == 1 else Category.INBOX


def categorize_text(title: str, content: str) -> Category:
    """Classify normalized content into one stable subject category."""
    prompt = render_prompt(
        "categorize", title=title[:500], content=content[:MAX_CONTENT_CHARS]
    )
    return _parse_category(get_llm().invoke(prompt))


def categorize_article(article: Article) -> Category:
    """Classify an Article without changing its content or other editorial fields."""
    return categorize_text(article.title, article.content)
