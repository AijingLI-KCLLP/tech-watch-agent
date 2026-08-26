"""Load and render the editable LLM prompt templates."""

import json
from functools import lru_cache
from pathlib import Path


_PROMPTS_PATH = Path(__file__).parent.parent / "prompts.json"


class PromptConfigurationError(RuntimeError):
    """Raised when the prompt configuration cannot safely be used."""


@lru_cache(maxsize=1)
def _templates() -> dict[str, str]:
    try:
        payload = json.loads(_PROMPTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromptConfigurationError("Could not read prompts.json.") from exc
    if not isinstance(payload, dict) or not all(
        isinstance(name, str) and isinstance(template, str)
        for name, template in payload.items()
    ):
        raise PromptConfigurationError("prompts.json must map prompt names to strings.")
    return payload


def render_prompt(name: str, /, **values: object) -> str:
    """Render one named template while reporting missing fields clearly."""
    template = _templates().get(name)
    if template is None:
        raise PromptConfigurationError(f"Prompt {name!r} is not configured.")
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError) as exc:
        raise PromptConfigurationError(
            f"Prompt {name!r} has an invalid placeholder: {exc}"
        ) from exc
