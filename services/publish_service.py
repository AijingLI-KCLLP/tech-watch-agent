"""Service boundary for draft creation, regeneration, and manual persistence."""

from core.models import Draft, DraftFormat, DraftStatus
from core.publish_graph import build_publish_graph
from adapters.embedder import embed
from adapters.store import (
    get_articles_for_draft,
    get_draft_detail,
    query_chunks,
    save_draft,
    update_draft,
)
from config import MAX_DRAFT_ARTICLES, RETRIEVAL_MIN_SCORE, TOP_K
from services.agent_service import watch_topic


def _selected_articles(article_ids: list[str]) -> list[dict]:
    unique_ids = list(dict.fromkeys(article_ids))
    if not unique_ids:
        raise ValueError("Select at least one article.")
    if len(unique_ids) > MAX_DRAFT_ARTICLES:
        raise ValueError(f"Select at most {MAX_DRAFT_ARTICLES} articles for one draft.")
    articles = get_articles_for_draft(unique_ids)
    found_ids = {article["id"] for article in articles}
    missing_ids = [article_id for article_id in unique_ids if article_id not in found_ids]
    if missing_ids:
        raise ValueError("One or more selected articles no longer exist.")
    return articles


def _local_article_ids(intent: str) -> list[str]:
    """Select distinct, relevant library articles from semantic retrieval."""
    hits = query_chunks(embed([intent])[0], max(TOP_K * 3, MAX_DRAFT_ARTICLES))
    return list(
        dict.fromkeys(
            hit["article_id"]
            for hit in hits
            if hit["score"] >= RETRIEVAL_MIN_SCORE
        )
    )


def _articles_for_intent(intent: str, *, enrich_with_web: bool) -> list[dict]:
    article_ids = _local_article_ids(intent)
    if enrich_with_web:
        try:
            enrichment = watch_topic(intent)
            article_ids.extend(article["id"] for article in enrichment["articles"])
        except Exception:
            # Web enrichment is additive. Existing relevant library content can
            # still support a draft when an upstream web/LLM operation is down.
            if not article_ids:
                raise
    return _selected_articles(list(dict.fromkeys(article_ids))[:MAX_DRAFT_ARTICLES])


def _run_workflow(
    *,
    articles: list[dict],
    intent: str,
    format: DraftFormat,
    platform: str,
    language: str,
    audience: str,
    objective: str,
    tone: str,
    personal_angle: str,
) -> dict:
    return build_publish_graph().invoke(
        {
            "articles": articles,
            "intent": intent,
            "format": format,
            "platform": platform,
            "language": language,
            "audience": audience,
            "objective": objective,
            "tone": tone,
            "personal_angle": personal_angle,
        }
    )


def create_draft(
    *,
    intent: str,
    format: DraftFormat,
    platform: str,
    language: str,
    audience: str,
    objective: str,
    tone: str,
    personal_angle: str,
    enrich_with_web: bool = True,
) -> dict:
    articles = _articles_for_intent(intent, enrich_with_web=enrich_with_web)
    result = _run_workflow(
        articles=articles,
        intent=intent,
        format=format,
        platform=platform,
        language=language,
        audience=audience,
        objective=objective,
        tone=tone,
        personal_angle=personal_angle,
    )
    draft = Draft(
        title=(intent[:120].strip() + " — draft"),
        intent=intent,
        format=format,
        platform=platform,
        language=language,
        audience=audience,
        objective=objective,
        tone=tone,
        personal_angle=personal_angle,
        source_summary=result["source_summary"],
        generated_content=result["content"],
        content=result["content"],
    )
    save_draft(draft, [article["id"] for article in articles])
    return get_draft_detail(draft.id) or {}


def regenerate_draft(draft_id: str) -> dict | None:
    draft = get_draft_detail(draft_id)
    if draft is None:
        return None
    article_ids = [article["id"] for article in draft["articles"]]
    articles = _selected_articles(article_ids)
    result = _run_workflow(
        articles=articles,
        intent=draft["intent"],
        format=DraftFormat(draft["format"]),
        platform=draft["platform"],
        language=draft["language"],
        audience=draft["audience"],
        objective=draft["objective"],
        tone=draft["tone"],
        personal_angle=draft["personal_angle"],
    )
    return update_draft(
        draft_id,
        source_summary=result["source_summary"],
        generated_content=result["content"],
        content=result["content"],
        status=DraftStatus.DRAFT.value,
    )
