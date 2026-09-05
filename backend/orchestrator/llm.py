"""Planner: English → structured Plan for Tools 1–4.

The LLM (or keyword matcher) chooses WHICH tool. Args always come from
HTTP/state via trusted_args_for_tool — never from model JSON.

SATQUERY_MOCK_PLANNER=true  → keyword planner (offline tests)
SATQUERY_MOCK_PLANNER=false → LLM (Groq / OpenAI-compatible)
"""

from __future__ import annotations

import functools
import logging
import warnings
from typing import Any

from backend.config.settings import settings
from backend.orchestrator.registry import (
    TOOL_REGISTRY,
    TOOL_SPEC,
    enforce_call_tool_location,
    match_tool_from_query,
    trusted_args_for_tool,
)
from backend.orchestrator.state import Plan, SatQueryState

logger = logging.getLogger(__name__)

_TOOL_LINES = "\n".join(f"  - {n}: {d}" for n, d in TOOL_REGISTRY.items())

SYSTEM_PROMPT = f"""\
You are the planner for SatQuery. Decide one action and which tool (if any).
Do not execute tools. Do not invent coordinates, dates, CRS, credentials,
polarization, orbit, bands, or any other tool parameters — the backend fills
args from the HTTP request.

Available tools:
{_TOOL_LINES}

Rules:
1. call_tool when a tool matches and required inputs are present
2. Priority when ambiguous: SAR/flood/radar > weather/environment > \
vegetation/NDVI/crop health/multispectral > optical RGB
3. clarify if location is missing (bbox for imagery; bbox or lat/lon for weather)
4. chat if unrelated; respond_error if validation errors exist

Return JSON: action, tool, args, reason
Set args to {{}} — the backend overwrites them.
"""


def _keyword_plan(state: SatQueryState) -> Plan:
    if state.get("errors"):
        return {"action": "respond_error", "tool": None, "args": {},
                "reason": "Input validation failed; skip tool selection."}
    query = (state.get("query") or "").strip()
    if not query:
        return {"action": "respond_error", "tool": None, "args": {}, "reason": "Empty query."}

    tool, reason = match_tool_from_query(query)
    if not tool:
        return {"action": "chat", "tool": None, "args": {},
                "reason": "Query does not match a known remote-sensing tool."}

    planned: Plan = {
        "action": "call_tool",
        "tool": tool,
        "args": trusted_args_for_tool(tool, state),
        "reason": reason,
    }
    return enforce_call_tool_location(planned, state)


_PLAN_SCHEMA = {
    "title": "Plan",
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["call_tool", "clarify", "chat", "respond_error"]},
        "tool": {"type": ["string", "null"]},
        "args": {"type": "object"},
        "reason": {"type": "string"},
    },
    "required": ["action", "tool", "args", "reason"],
}


@functools.lru_cache(maxsize=1)
def _build_llm_client() -> Any:
    provider = settings.llm_provider.lower()
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        kwargs: dict[str, Any] = {"model": settings.llm_model, "temperature": 0}
        if settings.llm_api_key:
            kwargs["api_key"] = settings.llm_api_key
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        base = ChatOpenAI(**kwargs)
    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        kwargs = {"model": settings.llm_model, "temperature": 0}
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        base = ChatOllama(**kwargs)
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        kwargs = {"model": settings.llm_model, "temperature": 0}
        if settings.llm_api_key:
            kwargs["api_key"] = settings.llm_api_key
        base = ChatAnthropic(**kwargs)
    else:
        raise ValueError(f"Unknown SATQUERY_LLM_PROVIDER='{provider}'")
    return base.with_structured_output(_PLAN_SCHEMA)


def _llm_plan(state: SatQueryState) -> Plan:
    from langchain_core.messages import HumanMessage, SystemMessage

    user_msg = (
        f"Query: {state.get('query', '')}\n"
        f"Bounding box: {state.get('bbox') if state.get('bbox') else 'not provided'}\n"
        f"Latitude: {state.get('latitude') if state.get('latitude') is not None else 'not provided'}\n"
        f"Longitude: {state.get('longitude') if state.get('longitude') is not None else 'not provided'}\n"
        f"Start date: {state.get('start_date') or 'not provided'}\n"
        f"End date: {state.get('end_date') or 'not provided'}\n"
        f"Validation errors: {state.get('errors') or 'none'}"
    )
    try:
        result: dict[str, Any] = _build_llm_client().invoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_msg)]
        )
        if result.get("action") not in {"call_tool", "clarify", "chat", "respond_error"}:
            raise ValueError(f"Unknown action: {result.get('action')!r}")
        action = result["action"]
        tool = result.get("tool")
        if action == "call_tool":
            if tool not in TOOL_SPEC:
                planned = Plan(
                    action="respond_error",
                    tool=None,
                    args={},
                    reason=f"Unknown tool {tool!r}.",
                )
            else:
                planned = Plan(
                    action="call_tool",
                    tool=tool,
                    args=trusted_args_for_tool(tool, state),
                    reason=result.get("reason", ""),
                )
        else:
            planned = Plan(
                action=action,
                tool=None,
                args={},
                reason=result.get("reason", ""),
            )
        return enforce_call_tool_location(planned, state)
    except Exception as exc:  # noqa: BLE001
        warnings.warn(f"LLM planner failed ({exc!r}); keyword fallback.", RuntimeWarning, stacklevel=2)
        logger.warning("LLM planner error — keyword fallback", exc_info=True)
        return _keyword_plan(state)


def make_plan(state: SatQueryState) -> Plan:
    if settings.use_mock_planner:
        return _keyword_plan(state)
    return _llm_plan(state)
