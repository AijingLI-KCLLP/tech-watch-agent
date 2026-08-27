"""Local-LLM workflow for turning selected library items into an editable draft."""

from typing import TypedDict

from adapters.llm import get_llm
from adapters.prompts import render_prompt
from config import MAX_DRAFT_ARTICLE_CHARS
from core.models import DraftFormat
from langgraph.graph import END, START, StateGraph


class PublishState(TypedDict):
    articles: list[dict]
    intent: str
    format: DraftFormat
    platform: str
    language: str
    audience: str
    objective: str
    tone: str
    personal_angle: str
    source_summary: str
    writing_direction: str
    content: str


def _text(response: object) -> str:
    return str(getattr(response, "content", response)).strip()


def _source_pack(articles: list[dict]) -> str:
    entries: list[str] = []
    for position, article in enumerate(articles, start=1):
        metadata = [
            f"title: {article['title']}",
            f"source: {article.get('source_name') or 'not recorded'}",
            f"url: {article.get('url') or 'not recorded'}",
            f"category: {article.get('category') or 'inbox'}",
        ]
        if article.get("summary"):
            metadata.append(f"stored summary: {article['summary']}")
        metadata.append(f"content:\n{article['content'][:MAX_DRAFT_ARTICLE_CHARS]}")
        entries.append(f"<source index=\"{position}\">\n" + "\n".join(metadata) + "\n</source>")
    return "\n\n".join(entries)


def summarize_sources_node(state: PublishState) -> dict:
    return {
        "source_summary": _text(
            get_llm().invoke(
                render_prompt(
                    "publish_summarize_sources",
                    intent=state["intent"],
                    language=state["language"],
                    sources=_source_pack(state["articles"]),
                )
            )
        )
    }


def develop_angle_node(state: PublishState) -> dict:
    """Keep the author's intent intact instead of asking the LLM to invent a voice."""
    return {
        "writing_direction": (
            f"Sharing intent: {state['intent']}\n"
            f"Personal angle supplied by the author: {state['personal_angle']}\n"
            f"Audience: {state['audience']}\n"
            f"Objective: {state['objective']}\n"
            f"Tone: {state['tone']}"
        )
    }


def generate_draft_node(state: PublishState) -> dict:
    prompt_name = (
        "publish_generate_note"
        if state["format"] is DraftFormat.NOTE
        else "publish_generate_post"
    )
    return {
        "content": _text(
            get_llm().invoke(
                render_prompt(
                    prompt_name,
                    intent=state["intent"],
                    platform=state["platform"],
                    language=state["language"],
                    audience=state["audience"],
                    objective=state["objective"],
                    tone=state["tone"],
                    source_summary=state["source_summary"],
                    writing_direction=state["writing_direction"],
                )
            )
        )
    }


def build_publish_graph():
    graph = StateGraph(PublishState)
    graph.add_node("summarize_sources", summarize_sources_node)
    graph.add_node("develop_angle", develop_angle_node)
    graph.add_node("generate_draft", generate_draft_node)
    graph.add_edge(START, "summarize_sources")
    graph.add_edge("summarize_sources", "develop_angle")
    graph.add_edge("develop_angle", "generate_draft")
    graph.add_edge("generate_draft", END)
    return graph.compile()
