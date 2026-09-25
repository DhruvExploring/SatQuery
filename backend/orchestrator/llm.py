"""SatQuery planner for Tools 1-11.

The model selects the tool; trusted arguments are always produced by the backend
from state (bbox, dates, file paths, credentials -- never from the model's own
`args`). The one deliberate, narrow exception: `place_name`/`landmark_names`
(_PLAN_SCHEMA below), the model's own extraction of what to search for from the
user's raw question -- there's no other deterministic source for "what place
name did they mean," and tools (Tool 10 in particular) must never try to parse
that out of a raw sentence themselves. See _llm_plan's enrichment step and
registry.py::trusted_args_for_tool's TOOL_GEOCODE_FORWARD/TOOL_SCENE_IDENTITY
branches.
The OpenAI/Claude toggle from the existing project is preserved.
"""
from __future__ import annotations

import functools
import logging
from pathlib import Path
from typing import Any

from backend.config.settings import settings
from backend.orchestrator.registry import (
    TOOL_GEOCODE_FORWARD,
    TOOL_INDICES,
    TOOL_INSPECT,
    TOOL_MULTI,
    TOOL_OPTICAL,
    TOOL_REGISTRY,
    TOOL_SAR,
    TOOL_SCENE_IDENTITY,
    TOOL_SPATIAL,
    TOOL_SPEC,
    TOOL_TEMPORAL,
    TOOL_WEATHER,
    enforce_call_tool_location,
    match_tool_from_query,
    trusted_args_for_tool,
)
from backend.orchestrator.prompts import load_prompt
from backend.orchestrator.state import Plan, SatQueryState

logger = logging.getLogger(__name__)

_TOOL_LINES = "\n".join(f"  - {n}: {d}" for n, d in TOOL_REGISTRY.items())
_PLANNER_TOOL_NAMES = list(TOOL_REGISTRY.keys())

# The entire planner prompt -- identity, rules, tool list, routing hints, and
# where the continuation note plugs in -- lives in one editable file,
# backend/orchestrator/prompts/planner_system.md, so it can be edited without
# touching this code. Used whether or not SkillKit is active: it already
# tells the model how to treat Skill/SkillRead tools if they're bound (see
# _build_skillkit below), so there's no separate skillkit-only prompt file to
# keep in sync.
#
# {{CONTINUATION_NOTE}} is only filled in when tool_results_so_far is
# non-empty, i.e. this is a continuation call after at least one tool has
# already run for this same request -- see plan_single_tool. On a fresh
# request (no prior results), `chat` means "this needs no remote-sensing tool
# at all." On a continuation it means something different (see
# continuation_suffix.md), so it's spelled out explicitly only then rather
# than left ambiguous on every hop.
_CONTINUATION_NOTE = load_prompt("continuation_suffix")

SYSTEM_PROMPT = load_prompt(
    "planner_system",
    TOOL_NAMES=", ".join(_PLANNER_TOOL_NAMES),
    TOOL_LINES=_TOOL_LINES,
    CONTINUATION_NOTE="",
)

SYSTEM_PROMPT_WITH_CONTINUATION = load_prompt(
    "planner_system",
    TOOL_NAMES=", ".join(_PLANNER_TOOL_NAMES),
    TOOL_LINES=_TOOL_LINES,
    CONTINUATION_NOTE=_CONTINUATION_NOTE,
)

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
    if settings.orchestrator_provider == "openai":
        if not settings.orchestrator_api_key:
            raise ValueError(
                "SATQUERY_ORCHESTRATOR_PROVIDER=openai but no API key is set "
                "(SATQUERY_ORCHESTRATOR_API_KEY or OPENAI_API_KEY)."
            )
        from langchain_openai import ChatOpenAI
        kwargs: dict[str, Any] = {
            "model": settings.orchestrator_model,
            "api_key": settings.orchestrator_api_key,
            "temperature": 0,
            "max_tokens": 1500,
        }
        if settings.orchestrator_base_url:
            kwargs["base_url"] = settings.orchestrator_base_url
        return ChatOpenAI(**kwargs)

    if settings.orchestrator_provider == "anthropic":
        if not settings.orchestrator_api_key:
            raise ValueError(
                "SATQUERY_ORCHESTRATOR_PROVIDER=anthropic but no API key is set "
                "(SATQUERY_ORCHESTRATOR_API_KEY or ANTHROPIC_API_KEY)."
            )
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=settings.orchestrator_model,
            api_key=settings.orchestrator_api_key,
        )

    raise ValueError("No LLM provider is enabled (SATQUERY_ORCHESTRATOR_PROVIDER=mock).")

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
        # Tools never parse the user's natural-language query themselves --
        # any semantic extraction from raw text happens here, once, by the
        # model that actually read the question. The backend still builds
        # every other trusted argument (bbox, dates, paths) from state, not
        # from `args` -- these two fields are the sole, narrow exception,
        # because "what place name/landmark(s) to search for" has no other
        # deterministic source. See registry.py::trusted_args_for_tool's
        # TOOL_GEOCODE_FORWARD/TOOL_SCENE_IDENTITY branches.
        "place_name": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": (
                "Only when tool is geocode_place_to_coordinates: the clean "
                "place/feature name to search for (e.g. 'Yamuna River'), "
                "extracted from the user's question -- never the full "
                "question text or conversational wording around it. Null "
                "for every other tool."
            ),
        },
        "landmark_names": {
            "anyOf": [
                {"type": "array", "items": {"type": "string"}},
                {"type": "null"},
            ],
            "description": (
                "Only when tool is resolve_scene_identity and the question "
                "names specific landmark(s) to check against the scene: "
                "their clean name(s) (e.g. ['Red Fort', 'India Gate']), one "
                "per landmark mentioned. Null when no specific landmark is "
                "named."
            ),
        },
    },
    "required": ["action", "tool", "args", "reason", "place_name", "landmark_names"],
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

    # Unlike the real LLM planner, this keyword matcher has no notion of
    # "what have I already gathered/tried" -- it would otherwise re-select
    # the same tool on every continuation hop (the query text never
    # changes) and spin until MAX_TOOL_HOPS, whether that tool succeeded
    # (nothing left to do) or failed (retrying identically can't help).
    # Attempt each keyword-matched tool at most once.
    already_attempted = {r.get("tool") for r in (state.get("tool_results") or [])}
    if tool in already_attempted:
        # Keep `tool`/`args` on the stop signal (unlike the "no tool ever
        # needed" case below) so callers/API consumers can still see which
        # tool actually ran and what it was called with, instead of it
        # reading back None/{}.
        return {
            "action": "chat",
            "tool": tool,
            "args": trusted_args_for_tool(tool, state),
            "reason": f"{tool} already attempted.",
        }

    planned: Plan = {"action": "call_tool", "tool": tool, "args": trusted_args_for_tool(tool, state), "reason": reason}
    return enforce_call_tool_location(planned, state)

def _llm_plan(state: SatQueryState) -> Plan:
    from langchain_core.messages import HumanMessage, SystemMessage

    tool_results = state.get("tool_results") or []
    system_prompt = SYSTEM_PROMPT_WITH_CONTINUATION if tool_results else SYSTEM_PROMPT
    context = {
        "query": state.get("query", ""),
        "bbox": state.get("bbox"),
        "region_bbox": state.get("region_bbox"),
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
    if tool_results:
        context["tool_results_so_far"] = [
            {"tool": r.get("tool"), "result": r.get("result")} for r in tool_results
        ]

    client = _build_llm_client()
    memory_tools = _build_memory_tools(state.get("user_id"))
    if memory_tools:
        client = client.bind_tools(memory_tools)

    result: dict[str, Any] = client.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Context: {context}"),
    ])

    if result.get("action") not in {"call_tool", "clarify", "chat", "respond_error"}:
        # Some models occasionally put the tool name where `action` belongs
        # (e.g. action="get_place_name_from_coordinates" instead of
        # action="call_tool", tool="get_place_name_from_coordinates") --
        # the two-field split isn't enum-enforced by every provider. Recover
        # by treating a resolvable tool name in `action` as the intended
        # call_tool, instead of discarding an otherwise-clear model choice
        # and raising.
        recovered_tool = resolve_llm_tool(result.get("action"))
        if recovered_tool is None:
            raise ValueError(f"LLM returned unknown action: {result.get('action')!r}")
        logger.info(
            "LLM put tool name %r in the action field; recovered as call_tool.",
            result.get("action"),
        )
        result = {**result, "action": "call_tool", "tool": recovered_tool}

    action = result["action"]
    tool = result.get("tool")
    if action != "call_tool":
        if tool_results and action == "chat":
            # A continuation call returning "chat" means "I have enough to
            # answer now," not "no tool was ever needed" -- relabel so
            # `respond()` falls through to its ordinary tool_results
            # synthesis path instead of its canned chat-only reply. Keep
            # `tool`/`args` pointing at the last tool that actually ran (not
            # None/{}) so callers can still see what produced the answer.
            last_tool = tool_results[-1].get("tool")
            return {
                "action": "finish",
                "tool": last_tool,
                "args": trusted_args_for_tool(last_tool, state) if last_tool else {},
                "reason": result.get("reason", ""),
            }
        planned: Plan = {"action": action, "tool": None, "args": {}, "reason": result.get("reason", "")}
        return enforce_call_tool_location(planned, state)

    resolved = resolve_llm_tool(tool)
    if resolved is None or resolved not in TOOL_SPEC:
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

    # The LLM already read the user's actual question -- for the two tools
    # whose correct argument is inherently a piece of extracted natural-
    # language meaning (what place to search for; which landmarks were
    # named), use its own extraction instead of handing the tool a raw
    # sentence to parse itself. Injected onto a per-hop state copy (never
    # the real graph state) so trusted_args_for_tool and
    # enforce_call_tool_location -- which rebuilds args from state too, see
    # registry.py -- both see it consistently, and it can never leak into a
    # later, unrelated hop.
    enriched_state = state
    if resolved == TOOL_GEOCODE_FORWARD and result.get("place_name"):
        enriched_state = {**state, "place_name": result["place_name"]}
    elif resolved == TOOL_SCENE_IDENTITY and result.get("landmark_names"):
        enriched_state = {**state, "landmark_names": result["landmark_names"]}

    planned = {
        "action": "call_tool",
        "tool": resolved,
        "args": trusted_args_for_tool(resolved, enriched_state),
        "reason": result.get("reason", ""),
    }
    return enforce_call_tool_location(planned, enriched_state)

def plan_single_tool(state: SatQueryState) -> Plan:
    """Keyword or LLM planner for single-tool / chat only. Missions never call this."""
    if settings.orchestrator_provider == "mock":
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
    """Thin single-hop convenience wrapper around plan_single_tool -- the
    tool-loop subgraph (tool_loop_graph.py) is what actually drives
    multi-hop planning at query time."""
    return plan_single_tool(state)
