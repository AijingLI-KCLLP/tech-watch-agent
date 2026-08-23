"""Source-legitimacy enrichment that never blocks ingestion."""

import json
import re

from adapters.llm import get_llm
from core.models import Source, SourceType


MAX_REASON_CHARS = 500


def _parse_qualification(response: object) -> tuple[float, str] | None:
    content = str(getattr(response, "content", response)).strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if match is None:
        return None

    try:
        payload = json.loads(match.group())
        score = float(payload["credibility_score"])
        reason = str(payload["credibility_reason"]).strip()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None

    if not 0 <= score <= 1 or not reason:
        return None
    return round(score, 2), reason[:MAX_REASON_CHARS]


def qualify_source(source: Source) -> Source:
    """Estimate source legitimacy from available source metadata.

    The result is advisory: a failed or malformed LLM response leaves the source
    unchanged, so qualification cannot reject or interrupt ingestion.
    """
    if source.type is SourceType.PERSONAL_NOTE:
        return source.model_copy(
            update={
                "credibility_reason": (
                    "Personal note: no external publisher can be independently assessed."
                )
            }
        )

    prompt = f"""Assess the legitimacy of this information source for a personal
knowledge library. Use only the metadata below; do not claim to have browsed or
verified the source. Return JSON only, with this exact shape:

{{"credibility_score": 0.0, "credibility_reason": "one concise reason"}}

Score guide: 0.9-1.0 for primary official or academic publishers, 0.7-0.89 for
established editorial or professional publishers, 0.4-0.69 for community or
unverified specialist sites, and 0.0-0.39 for anonymous or low-accountability
sources. Explain the score from the source name, URL, and declared type only.

<source>
name: {source.name}
url: {source.url}
type: {source.type.value}
</source>"""
    try:
        decision = _parse_qualification(get_llm().invoke(prompt))
    except Exception:
        return source

    if decision is None:
        return source
    score, reason = decision
    return source.model_copy(
        update={"credibility_score": score, "credibility_reason": reason}
    )
