"""Persisted RAG conversations for the Ask interface."""

from adapters.store import (
    get_conversation_detail,
    save_conversation,
    save_conversation_message,
    update_conversation_title,
)
from core.models import ChatRole, Conversation, ConversationMessage
from services.agent_service import ask_question


def create_conversation() -> dict:
    conversation = Conversation()
    save_conversation(conversation)
    return get_conversation_detail(conversation.id) or {}


def _discussion_context(messages: list[dict]) -> str:
    """Keep enough prior turns for follow-up questions without bloating retrieval."""
    recent = messages[-6:]
    lines = [
        f"{message['role'].capitalize()}: {message['content']}"
        for message in recent
    ]
    return "\n".join(lines)[-6_000:]


def ask_in_conversation(conversation_id: str, question: str) -> dict | None:
    conversation = get_conversation_detail(conversation_id)
    if conversation is None:
        return None
    prior_messages = conversation["messages"]
    save_conversation_message(
        ConversationMessage(
            conversation_id=conversation_id,
            role=ChatRole.USER,
            content=question,
        )
    )
    result = ask_question(question, discussion_context=_discussion_context(prior_messages))
    save_conversation_message(
        ConversationMessage(
            conversation_id=conversation_id,
            role=ChatRole.ASSISTANT,
            content=result["answer"],
        )
    )
    if not prior_messages:
        update_conversation_title(conversation_id, question.strip()[:120])
    return get_conversation_detail(conversation_id)
