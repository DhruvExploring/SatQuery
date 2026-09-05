"""Planner: English → structured Plan.

Two paths controlled by settings.use_mock_planner:

  True  → keyword mock (no network, tests always pass)
  False → real LLM via LangChain with_structured_output + SkillKit discovery

The node that calls make_plan() must not care which path is active.

To add a new tool:
  1. Add its name + description to TOOL_REGISTRY (used by keyword planner + executor)
  2. Create skills/<tool-name>/SKILL.md (used by LLM planner via SkillKit)
  Nothing else changes.
"""

from __future__ import annotations

import functools
import logging
import warnings
from typing import Any

from backend.config.settings import settings
from backend.orchestrator.state import Plan, SatQueryState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool registry — single source of truth the prompt is built from.
# When you add fetch_sar, fetch_lulc, etc., add them here only.
# ---------------------------------------------------------------------------
TOOL_REGISTRY: dict[str, str] = {
    "fetch_satellite_imagery": (
        "Download a Sentinel-2 optical GeoTIFF for a bounding box and date range. "
        "Requires: bbox ([min_lon, min_lat, max_lon, max_lat]), start_date, end_date."
    ),
    "fetch_sar": (
        "Download Sentinel-1 SAR (Synthetic Aperture Radar) imagery for a bounding "
        "box and date range. Use when the user requests radar, SAR, or Sentinel-1 data. "
        "Requires: bbox ([min_lon, min_lat, max_lon, max_lat]), start_date, end_date."
    ),
}

# ---------------------------------------------------------------------------
# System prompt — used by the LLM path.
# Tool descriptions are NOT hardcoded here; the LLM discovers them via
# SkillKit (Skill / SkillRead tools) when use_mock_planner=False.
# The fallback static prompt (STATIC_SYSTEM_PROMPT) is used if SkillKit
# is unavailable (import error, missing skills/ dir, etc.).
# ---------------------------------------------------------------------------
_TOOL_LINES = "\n".join(
    f"  - {name}: {desc}" for name, desc in TOOL_REGISTRY.items()
)

# Static fallback — same as Week 1 behaviour if SkillKit is not available.
STATIC_SYSTEM_PROMPT = f"""\
You are the planner for SatQuery, a remote-sensing AI assistant.
Your only job is to decide what action to take given a user query and context.
You must NOT execute tools, fetch data, or invent file paths.

Available tools:
{_TOOL_LINES}

Rules:
1. If the user wants satellite imagery and all required inputs are present → action=call_tool
2. If the user wants satellite imagery but bbox is missing → action=clarify
3. If the query is unrelated to remote sensing → action=chat
4. If validation errors exist in the context → action=respond_error

Return JSON with exactly these fields:
  action  : one of "call_tool" | "clarify" | "chat" | "respond_error"
  tool    : tool name string or null
  args    : dict of tool arguments (empty dict if no tool)
  reason  : one sentence explaining your decision
"""

# SkillKit system prompt — tool descriptions come from SKILL.md files at runtime.
SKILLKIT_SYSTEM_PROMPT = """\
You are the planner for SatQuery, a remote-sensing AI assistant.
Your only job is to decide what action to take given a user query and context.
You must NOT execute tools, fetch data, or invent file paths.

You have access to two discovery tools:
  - Skill: list available remote-sensing skills (name + short description)
  - SkillRead: read the full instructions for a specific skill

Workflow:
1. Call Skill() to see what tools are available.
2. If a tool looks relevant, call SkillRead(name) to read its full instructions.
3. Decide which action to take based on the query and skill instructions.

Rules:
- If a relevant tool is available and all required inputs are present → action=call_tool
- If a relevant tool is available but a required input (e.g. bbox) is missing → action=clarify
- If the query is unrelated to remote sensing → action=chat
- If validation errors exist in the context → action=respond_error

Return JSON with exactly these fields:
  action  : one of "call_tool" | "clarify" | "chat" | "respond_error"
  tool    : the executor tool name (e.g. "fetch_satellite_imagery") or null
  args    : dict of tool arguments (empty dict if no tool)
  reason  : one sentence explaining your decision
"""

# ---------------------------------------------------------------------------
# Keyword mock (Week-1 baseline — preserved for testing and fallback)
# ---------------------------------------------------------------------------
FETCH_KEYWORDS = ("fetch", "imagery", "image", "sentinel", "satellite", "geotiff", "download")
SAR_KEYWORDS = ("sar", "radar", "sentinel-1", "sentinel1", "backscatter")
TOOL_FETCH = "fetch_satellite_imagery"
TOOL_SAR = "fetch_sar"


def _wants_sar(query: str) -> bool:
    lowered = query.lower()
    return any(kw in lowered for kw in SAR_KEYWORDS)


def _wants_fetch(query: str) -> bool:
    lowered = query.lower()
    return any(kw in lowered for kw in FETCH_KEYWORDS)


def _has_bbox(state: SatQueryState) -> bool:
    bbox = state.get("bbox")
    return isinstance(bbox, list) and len(bbox) == 4


def _keyword_plan(state: SatQueryState) -> Plan:
    """Original keyword-matching planner. Unchanged from Week 1."""
    if state.get("errors"):
        return {"action": "respond_error", "tool": None, "args": {},
                "reason": "Input validation failed; skip tool selection."}

    query = (state.get("query") or "").strip()
    if not query:
        return {"action": "respond_error", "tool": None, "args": {},
                "reason": "Empty query."}

    # SAR check first — "fetch SAR imagery" matches both SAR and fetch keywords;
    # SAR is more specific and should win.
    if _wants_sar(query):
        if not _has_bbox(state):
            return {"action": "clarify", "tool": None, "args": {},
                    "reason": "SAR fetch requested but bbox is missing."}
        args = {
            "bbox": state["bbox"],
            "start_date": state.get("start_date") or settings.default_start_date,
            "end_date": state.get("end_date") or settings.default_end_date,
            "width": state.get("width") or settings.default_width,
            "height": state.get("height") or settings.default_height,
            "crs": settings.default_crs,
        }
        return {"action": "call_tool", "tool": TOOL_SAR, "args": args,
                "reason": "Query looks like a Sentinel-1 SAR request."}

    if _wants_fetch(query):
        if not _has_bbox(state):
            return {"action": "clarify", "tool": None, "args": {},
                    "reason": "Fetch requested but bbox is missing."}
        args = {
            "bbox": state["bbox"],
            "start_date": state.get("start_date") or settings.default_start_date,
            "end_date": state.get("end_date") or settings.default_end_date,
            "modality": state.get("modality") or "optical",
            "bands": None,
            "max_cloud_cover": state.get("max_cloud_cover") or settings.default_max_cloud_cover,
            "width": state.get("width") or settings.default_width,
            "height": state.get("height") or settings.default_height,
            "crs": settings.default_crs,
        }
        return {"action": "call_tool", "tool": TOOL_FETCH, "args": args,
                "reason": "Query looks like a Sentinel-2 fetch request."}

    return {"action": "chat", "tool": None, "args": {},
            "reason": "Query does not match a known remote-sensing tool."}


# ---------------------------------------------------------------------------
# SkillKit — lazy-loaded, gracefully degrades if unavailable
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=1)
def _build_skillkit() -> Any | None:
    """
    Build a SkillKit instance pointed at the skills/ directory.
    Returns None if langchain-skillkit is not installed or the directory
    does not exist — the LLM path will fall back to the static prompt.
    """
    import os
    from pathlib import Path

    skills_dir = Path(__file__).parent.parent.parent / "skills"
    if not skills_dir.is_dir():
        logger.warning("skills/ directory not found at %s — SkillKit disabled.", skills_dir)
        return None

    try:
        from langchain_skillkit import SkillKit
        kit = SkillKit(str(skills_dir))
        logger.info("SkillKit loaded from %s", skills_dir)
        return kit
    except ImportError:
        logger.warning("langchain-skillkit not installed — SkillKit disabled.")
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("SkillKit failed to initialise (%r) — disabled.", exc)
        return None


# ---------------------------------------------------------------------------
# LLM client — built once and cached
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=1)
def _build_base_llm() -> Any:
    """
    Construct a LangChain chat model (no structured output yet).
    Cached so we don't rebuild on every request.
    Supports: openai, ollama, anthropic.
    """
    provider = settings.llm_provider.lower()

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        kwargs: dict[str, Any] = {"model": settings.llm_model, "temperature": 0}
        if settings.llm_api_key:
            kwargs["api_key"] = settings.llm_api_key
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        return ChatOpenAI(**kwargs)

    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        kwargs = {"model": settings.llm_model, "temperature": 0}
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        return ChatOllama(**kwargs)

    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        kwargs = {"model": settings.llm_model, "temperature": 0}
        if settings.llm_api_key:
            kwargs["api_key"] = settings.llm_api_key
        return ChatAnthropic(**kwargs)

    else:
        raise ValueError(
            f"Unknown SATQUERY_LLM_PROVIDER='{provider}'. "
            "Choose: openai | ollama | anthropic"
        )


# JSON schema the LLM must always return — shared by both client paths.
_PLAN_SCHEMA = {
    "title": "Plan",
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["call_tool", "clarify", "chat", "respond_error"],
        },
        "tool": {"type": ["string", "null"]},
        "args": {"type": "object"},
        "reason": {"type": "string"},
    },
    "required": ["action", "tool", "args", "reason"],
}


def _build_memory_tools(user_id: str | None) -> list[Any]:
    """
    Build LangMem manage + search tools scoped to a user namespace.
    Returns an empty list if langmem is not installed or memory_backend=none.

    These are NOT cached — each call gets tools bound to the current user_id.
    The cost is negligible: tool construction is cheap; the store is already cached.
    """
    if settings.memory_backend == "none":
        return []

    try:
        from langmem import create_manage_memory_tool, create_search_memory_tool

        # Namespace: ("satquery", "memories", <user_id or "anonymous">)
        # This keeps SatQuery memories isolated from other apps sharing the same store.
        uid = user_id or "anonymous"
        namespace = ("satquery", "memories", uid)

        return [
            create_manage_memory_tool(namespace=namespace),
            create_search_memory_tool(namespace=namespace),
        ]
    except ImportError:
        logger.warning("langmem not installed — memory tools disabled.")
        return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to build memory tools (%r) — memory disabled.", exc)
        return []


@functools.lru_cache(maxsize=1)
def _build_llm_client() -> Any:
    """
    Return a structured-output LLM client with SkillKit tools bound.
    Memory tools are NOT bound here — they are user-scoped and injected
    per-request in _llm_plan() via a separate bind_tools call.

    If SkillKit is available, binds SkillKit tools so the LLM can call
    Skill() / SkillRead() before committing to a Plan.
    Falls back to a plain structured-output client if SkillKit is absent.
    """
    base = _build_base_llm()
    kit = _build_skillkit()

    if kit is not None:
        llm_with_tools = base.bind_tools(kit.tools)
        return llm_with_tools.with_structured_output(_PLAN_SCHEMA)

    return base.with_structured_output(_PLAN_SCHEMA)


# ---------------------------------------------------------------------------
# LLM planner path
# ---------------------------------------------------------------------------
def _llm_plan(state: SatQueryState) -> Plan:
    """Call the real LLM to produce a Plan. Falls back to keyword planner on error."""
    from langchain_core.messages import HumanMessage, SystemMessage

    # Choose system prompt: SkillKit version if discovery tools are available,
    # static version otherwise.
    system_prompt = (
        SKILLKIT_SYSTEM_PROMPT if _build_skillkit() is not None
        else STATIC_SYSTEM_PROMPT
    )

    # Build a concise user message from state — no Sentinel Hub details here.
    bbox_str = str(state.get("bbox")) if state.get("bbox") else "not provided"
    user_msg = (
        f"Query: {state.get('query', '')}\n"
        f"Bounding box: {bbox_str}\n"
        f"Start date: {state.get('start_date') or 'not provided'}\n"
        f"End date: {state.get('end_date') or 'not provided'}\n"
        f"Validation errors: {state.get('errors') or 'none'}"
    )

    try:
        client = _build_llm_client()

        # Inject per-user memory tools if LangMem is active.
        # We re-bind on each call because user_id varies per request.
        memory_tools = _build_memory_tools(state.get("user_id"))
        if memory_tools:
            client = client.bind_tools(memory_tools)

        result: dict[str, Any] = client.invoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_msg)]
        )

        # Validate the action field to catch a hallucinated value early.
        valid_actions = {"call_tool", "clarify", "chat", "respond_error"}
        if result.get("action") not in valid_actions:
            raise ValueError(f"LLM returned unknown action: {result.get('action')!r}")

        # If LLM says call_tool but gave no args, merge in defaults from state.
        if result["action"] == "call_tool" and not result.get("args"):
            result["args"] = {
                "bbox": state.get("bbox"),
                "start_date": state.get("start_date") or settings.default_start_date,
                "end_date": state.get("end_date") or settings.default_end_date,
                "modality": state.get("modality") or "optical",
                "bands": None,
                "max_cloud_cover": state.get("max_cloud_cover") or settings.default_max_cloud_cover,
                "width": state.get("width") or settings.default_width,
                "height": state.get("height") or settings.default_height,
                "crs": settings.default_crs,
            }

        return Plan(
            action=result["action"],
            tool=result.get("tool"),
            args=result.get("args") or {},
            reason=result.get("reason", ""),
        )

    except Exception as exc:  # noqa: BLE001
        warnings.warn(
            f"LLM planner failed ({exc!r}); falling back to keyword planner.",
            RuntimeWarning,
            stacklevel=2,
        )
        logger.warning("LLM planner error — using keyword fallback", exc_info=True)
        return _keyword_plan(state)


# ---------------------------------------------------------------------------
# Public entry point — the ONLY symbol nodes.py imports
# ---------------------------------------------------------------------------
def make_plan(state: SatQueryState) -> Plan:
    """Return a Plan. Never downloads imagery. Never talks to Sentinel Hub.

    Routing:
      SATQUERY_MOCK_PLANNER=true  (default) → keyword planner (no LLM)
      SATQUERY_MOCK_PLANNER=false           → LLM planner with keyword fallback
    """
    if settings.use_mock_planner:
        return _keyword_plan(state)
    return _llm_plan(state)
