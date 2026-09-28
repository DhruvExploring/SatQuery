"""Optional narrative synthesis: the orchestrator LLM writes the final answer
instead of the templated format_tool_success() string.

Returns None (never raises) on any failure, so respond() falls back to the
deterministic template exactly as it did before this existed. This is a
reliability safety net for transient synthesis errors — not the automatic
local/API mode switching that the orchestrator and vision tool explicitly do
not do at runtime; the provider is still a static config choice.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.config.settings import settings
from backend.orchestrator.prompts import load_prompt
from backend.orchestrator.state import SatQueryState

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = load_prompt("synthesis_system")


def _extract_text(content: Any) -> str:
    """Some providers (e.g. Anthropic with extended thinking on) return a
    list of content blocks -- a "thinking" block plus a "text" block --
    instead of a plain string. Keep only the text block(s); a bare
    str(content) would otherwise dump the raw thinking block/signature into
    the user-facing answer.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(p for p in parts if p)
    return str(content)


def synthesize_final_answer(
    state: SatQueryState,
    tool_results: list[dict[str, Any]],
) -> str | None:
    if settings.orchestrator_provider == "mock" or not settings.orchestrator_synthesize_answer:
        return None

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        model_choice = state.get("model")
        if model_choice:
            try:
                client = _build_base_llm(model_override=model_choice)
            except TypeError:
                client = _build_base_llm()
        else:
            client = _build_base_llm()
        context = {
            "query": state.get("query"),
            "initial_description": state.get("initial_description"),
            "tool_results": tool_results,
        }
        response = client.invoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=f"Context: {context}"),
            ]
        )
        text = _extract_text(response.content)
        return text.strip() or None
    except Exception as exc:
        logger.warning(
            "Narrative synthesis failed (%r); falling back to templated answer.", exc
        )
        return None
