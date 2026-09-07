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
    TOOL_REGISTRY,
    TOOL_SPEC,
    enforce_call_tool_location,
    match_tool_from_query,
    trusted_args_for_tool,
)
from backend.orchestrator.state import Plan, SatQueryState

logger = logging.getLogger(__name__)

_TOOL_LINES = "\n".join(f"  - {n}: {d}" for n, d in TOOL_REGISTRY.items())

STATIC_SYSTEM_PROMPT = f"""You are the planner for SatQuery, a remote-sensing AI assistant.

Choose exactly one action: call_tool, clarify, chat, respond_error.
Choose the most relevant registered tool. Do not execute tools and do not invent
file paths, coordinates, dates, raster parameters or credentials. The backend
supplies trusted arguments.

Available tools:
{_TOOL_LINES}

Important:
- compute_vegetation_indices works on a multispectral GeoTIFF.
- inspect_geotiff_metadata works on any GeoTIFF.
- analyze_temporal_change compares two GeoTIFF rasters.
- analyze_spatial_landcover_terrain analyzes LULC and optionally DEM/change mask.
- Prefer analysis tools when the query asks for analysis rather than retrieval.

Return JSON with action, tool, args, reason. Set args to {{}}.
"""

SKILLKIT_SYSTEM_PROMPT = """You are the SatQuery planner.
Use Skill/SkillRead to understand relevant remote-sensing capabilities, then
select one tool. Never execute a tool and never invent file paths or parameters.
The backend supplies trusted arguments. Return action, tool, args, reason.
"""

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
        return ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, temperature=0)

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
        "tool": {"type": ["string", "null"]},
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
    elif tool not in TOOL_SPEC:
        planned = {"action": "respond_error", "tool": None, "args": {}, "reason": f"Unknown tool {tool!r}."}
    else:
        planned = {"action": "call_tool", "tool": tool, "args": trusted_args_for_tool(tool, state), "reason": result.get("reason", "")}

    return enforce_call_tool_location(planned, state)

def make_plan(state: SatQueryState) -> Plan:
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
