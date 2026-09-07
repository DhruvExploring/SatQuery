"""SatQuery planner for Tools 1-8.

The model selects the tool; trusted arguments are always produced by the backend.
The OpenAI/Claude toggle from the existing project is preserved.
"""
from __future__ import annotations

import functools
import logging
from pathlib import Path
from typing import Any

from backend.config.settings import settings
from backend.orchestrator.registry import (
    TOOL_INDICES,
    TOOL_INSPECT,
    TOOL_MULTI,
    TOOL_OPTICAL,
    TOOL_REGISTRY,
    TOOL_SAR,
    TOOL_SPATIAL,
    TOOL_SPEC,
    TOOL_TEMPORAL,
    TOOL_WEATHER,
    enforce_call_tool_location,
    match_tool_from_query,
    trusted_args_for_tool,
)
from backend.orchestrator.state import Plan, SatQueryState

logger = logging.getLogger(__name__)

_TOOL_LINES = "\n".join(f"  - {n}: {d}" for n, d in TOOL_REGISTRY.items())
_PLANNER_TOOL_NAMES = list(TOOL_REGISTRY.keys())

STATIC_SYSTEM_PROMPT = f"""You are the planner for SatQuery, a remote-sensing AI assistant.

Choose exactly one action: call_tool, clarify, chat, respond_error.
The tool field must be exactly one of these registered names, copied verbatim:
{', '.join(_PLANNER_TOOL_NAMES)}

Never invent names (not Sentinelimagery, SentinelHub_Search, Skill names, or API names).
Do not execute tools and do not invent file paths, coordinates, dates, raster
parameters or credentials. The backend supplies trusted arguments.

Available tools:
{_TOOL_LINES}

Routing hints:
- Sentinel-2 RGB / visual / optical → fetch_optical_imagery
- Sentinel-2 multispectral / bands / vegetation analysis fetch → fetch_multispectral_imagery
- Sentinel-1 / SAR / radar → fetch_sar_imagery
- rainfall / weather / temperature → fetch_weather_environment
- compute_vegetation_indices works on a multispectral GeoTIFF.
- inspect_geotiff_metadata works on any GeoTIFF.
- analyze_temporal_change compares two GeoTIFF rasters.
- analyze_spatial_landcover_terrain analyzes LULC and optionally DEM/change mask.

Return JSON with action, tool, args, reason. Set args to {{}}.
"""

SKILLKIT_SYSTEM_PROMPT = f"""You are the SatQuery planner.
Use Skill/SkillRead only as background. The tool field must still be exactly one
of: {', '.join(_PLANNER_TOOL_NAMES)}.
Never execute a tool, never invent file paths or parameters, and never return
Sentinel Hub / Skill / API identifiers as the tool name.
The backend supplies trusted arguments. Return action, tool, args, reason.
"""

# Aliases the model may copy from older skills or Sentinel Hub docs.
_LLM_TOOL_ALIASES = {
    "fetch_satellite_imagery": TOOL_OPTICAL,
    "fetch_optical": TOOL_OPTICAL,
    "fetch_sar": TOOL_SAR,
    "fetch_multispectral": TOOL_MULTI,
    "fetch_weather": TOOL_WEATHER,
    "compute_indices": TOOL_INDICES,
    "inspect_geotiff": TOOL_INSPECT,
    "analyze_temporal": TOOL_TEMPORAL,
    "analyze_spatial": TOOL_SPATIAL,
    "analyze_landcover": TOOL_SPATIAL,
}


def _normalize_tool_token(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def resolve_llm_tool(tool: Any) -> str | None:
    """Map a model-chosen name onto a canonical planner tool, or None."""
    if tool is None:
        return None
    raw = str(tool).strip()
    if not raw:
        return None
    if raw in TOOL_REGISTRY:
        return raw
    if raw in _LLM_TOOL_ALIASES:
        return _LLM_TOOL_ALIASES[raw]
    token = _normalize_tool_token(raw)
    for name in TOOL_REGISTRY:
        if _normalize_tool_token(name) == token:
            return name
    for alias, canonical in _LLM_TOOL_ALIASES.items():
        if _normalize_tool_token(alias) == token:
            return canonical
    return None

@functools.lru_cache(maxsize=1)
def _build_skillkit() -> Any | None:
    skills_dir = Path(__file__).parent.parent.parent / "skills"
    if not skills_dir.is_dir():
        return None
    try:
        # pyrefly: ignore [missing-import]
        from langchain_skillkit import SkillKit
        return SkillKit(str(skills_dir))
    except Exception as exc:
        logger.warning("SkillKit disabled: %r", exc)
        return None

@functools.lru_cache(maxsize=1)
def _build_base_llm() -> Any:
    if settings.use_openai:
        if settings.use_claude:
            raise ValueError("Enable exactly one of OpenAI or Claude.")
        if not settings.openai_api_key:
            raise ValueError("SATQUERY_USE_OPENAI=true but OPENAI_API_KEY is missing.")
        from langchain_openai import ChatOpenAI
        kwargs: dict[str, Any] = {
            "model": settings.openai_model,
            "api_key": settings.openai_api_key,
            "temperature": 0,
        }
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        return ChatOpenAI(**kwargs)

    if settings.use_claude:
        if not settings.claude_api_key:
            raise ValueError("SATQUERY_USE_CLAUDE=true but ANTHROPIC_API_KEY is missing.")
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=settings.claude_model, api_key=settings.claude_api_key, temperature=0)

    raise ValueError("No LLM provider is enabled.")

_PLAN_SCHEMA = {
    "title": "Plan",
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["call_tool", "clarify", "chat", "respond_error"]},
        "tool": {
            "anyOf": [
                {"type": "string", "enum": _PLANNER_TOOL_NAMES},
                {"type": "null"},
            ]
        },
        "args": {"type": "object"},
        "reason": {"type": "string"},
    },
    "required": ["action", "tool", "args", "reason"],
}

@functools.lru_cache(maxsize=1)
def _build_llm_client() -> Any:
    base = _build_base_llm()
    kit = _build_skillkit()
    if kit is not None:
        base = base.bind_tools(kit.tools)
    return base.with_structured_output(_PLAN_SCHEMA)

def _build_memory_tools(user_id: str | None) -> list[Any]:
    if settings.memory_backend == "none":
        return []
    try:
        # pyrefly: ignore [missing-import]
        from langmem import create_manage_memory_tool, create_search_memory_tool
        namespace = ("satquery", "memories", user_id or "anonymous")
        return [create_manage_memory_tool(namespace=namespace), create_search_memory_tool(namespace=namespace)]
    except Exception:
        return []

def _keyword_plan(state: SatQueryState) -> Plan:
    if state.get("errors"):
        return {"action": "respond_error", "tool": None, "args": {}, "reason": "Input validation failed; skip tool selection."}
    query = (state.get("query") or "").strip()
    if not query:
        return {"action": "respond_error", "tool": None, "args": {}, "reason": "Empty query."}

    tool, reason = match_tool_from_query(query)
    if not tool:
        return {"action": "chat", "tool": None, "args": {}, "reason": "Query does not match a registered remote-sensing tool."}

    planned: Plan = {"action": "call_tool", "tool": tool, "args": trusted_args_for_tool(tool, state), "reason": reason}
    return enforce_call_tool_location(planned, state)

def _llm_plan(state: SatQueryState) -> Plan:
    from langchain_core.messages import HumanMessage, SystemMessage

    system_prompt = SKILLKIT_SYSTEM_PROMPT if _build_skillkit() is not None else STATIC_SYSTEM_PROMPT
    context = {
        "query": state.get("query", ""),
        "bbox": state.get("bbox"),
        "latitude": state.get("latitude"),
        "longitude": state.get("longitude"),
        "start_date": state.get("start_date"),
        "end_date": state.get("end_date"),
        "post_start_date": state.get("post_start_date"),
        "post_end_date": state.get("post_end_date"),
        "input_file": state.get("input_file"),
        "raster_before_path": state.get("raster_before_path"),
        "raster_after_path": state.get("raster_after_path"),
        "lulc_raster_path": state.get("lulc_raster_path"),
        "dem_raster_path": state.get("dem_raster_path"),
        "zone_mask_path": state.get("zone_mask_path"),
        "validation_errors": state.get("errors") or [],
    }

    client = _build_llm_client()
    memory_tools = _build_memory_tools(state.get("user_id"))
    if memory_tools:
        client = client.bind_tools(memory_tools)

    result: dict[str, Any] = client.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Context: {context}"),
    ])

    if result.get("action") not in {"call_tool", "clarify", "chat", "respond_error"}:
        raise ValueError(f"LLM returned unknown action: {result.get('action')!r}")

    action = result["action"]
    tool = result.get("tool")
    if action != "call_tool":
        planned: Plan = {"action": action, "tool": None, "args": {}, "reason": result.get("reason", "")}
        return enforce_call_tool_location(planned, state)

    resolved = resolve_llm_tool(tool)
    if resolved is None or resolved not in TOOL_SPEC or resolved.startswith("workflow_"):
        logger.warning(
            "LLM selected unknown tool %r; falling back to keyword planner.",
            tool,
        )
        fallback = _keyword_plan(state)
        if fallback.get("action") == "call_tool":
            fallback["reason"] = (
                f"{fallback.get('reason', '')} "
                f"LLM returned unknown tool {tool!r}; used keyword fallback."
            ).strip()
        return fallback

    planned = {
        "action": "call_tool",
        "tool": resolved,
        "args": trusted_args_for_tool(resolved, state),
        "reason": result.get("reason", ""),
    }
    return enforce_call_tool_location(planned, state)

def plan_single_tool(state: SatQueryState) -> Plan:
    """Keyword or LLM planner for single-tool / chat only. Missions never call this."""
    if settings.use_mock_planner:
        return _keyword_plan(state)
    try:
        return _llm_plan(state)
    except Exception as exc:
        logger.warning(
            "LLM planning failed with error: %r. Falling back to keyword planner.",
            exc,
        )
        return _keyword_plan(state)


def make_plan(state: SatQueryState) -> Plan:
    from backend.orchestrator.handshake import build_plan_update

    return build_plan_update(state, plan_single_tool)["plan"]
