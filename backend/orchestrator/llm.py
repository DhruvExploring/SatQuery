"""Planner: English → structured Plan.

Two paths controlled by settings.use_mock_planner:

  True  → keyword mock (no network, tests always pass)
  False → real LLM via LangChain with_structured_output + SkillKit discovery

When the real LLM path is enabled, exactly ONE provider must be active:

  SATQUERY_USE_OPENAI=true
  SATQUERY_USE_CLAUDE=false

OR

  SATQUERY_USE_OPENAI=false
  SATQUERY_USE_CLAUDE=true

The node that calls make_plan() does not care which path is active.

To add a new tool:
  1. Add its name + description to TOOL_REGISTRY.
  2. Create skills/<tool-name>/SKILL.md.
  Nothing else changes.
"""

from __future__ import annotations

import functools
import logging
from typing import Any

from backend.config.settings import settings
from backend.orchestrator.state import Plan, SatQueryState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool registry — single source of truth
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
# System prompt
# ---------------------------------------------------------------------------
_TOOL_LINES = "\n".join(
    f"  - {name}: {desc}" for name, desc in TOOL_REGISTRY.items()
)


STATIC_SYSTEM_PROMPT = f"""\
You are the planner for SatQuery, a remote-sensing AI assistant.

Your only job is to decide what action to take given a user query and context.

You must NOT:
- execute tools
- fetch data
- invent file paths

Available tools:
{_TOOL_LINES}

Rules:
1. If the user wants satellite imagery and all required inputs are present
   → action=call_tool
2. If the user wants satellite imagery but bbox is missing
   → action=clarify
3. If the query is unrelated to remote sensing
   → action=chat
4. If validation errors exist in the context
   → action=respond_error

Return JSON with exactly these fields:

  action : one of "call_tool" | "clarify" | "chat" | "respond_error"
  tool   : tool name string or null
  args   : dict of tool arguments
  reason : one sentence explaining your decision
"""


SKILLKIT_SYSTEM_PROMPT = """\
You are the planner for SatQuery, a remote-sensing AI assistant.

Your only job is to decide what action to take given a user query and context.

You must NOT:
- execute tools
- fetch data
- invent file paths

You have access to two discovery tools:

  - Skill: list available remote-sensing skills
  - SkillRead: read the full instructions for a specific skill

Workflow:
1. Call Skill() to see what tools are available.
2. If a tool looks relevant, call SkillRead(name).
3. Decide which action to take based on the query and skill instructions.

Rules:
- If a relevant tool is available and all required inputs are present
  → action=call_tool
- If a relevant tool is available but a required input such as bbox is missing
  → action=clarify
- If the query is unrelated to remote sensing
  → action=chat
- If validation errors exist in the context
  → action=respond_error

Return JSON with exactly these fields:

  action : one of "call_tool" | "clarify" | "chat" | "respond_error"
  tool   : executor tool name or null
  args   : dict of tool arguments
  reason : one sentence explaining your decision
"""


# ---------------------------------------------------------------------------
# Keyword mock planner
# ---------------------------------------------------------------------------
FETCH_KEYWORDS = (
    "fetch",
    "imagery",
    "image",
    "sentinel",
    "satellite",
    "geotiff",
    "download",
)

SAR_KEYWORDS = (
    "sar",
    "radar",
    "sentinel-1",
    "sentinel1",
    "backscatter",
)

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
    """Original keyword-matching planner."""

    if state.get("errors"):
        return {
            "action": "respond_error",
            "tool": None,
            "args": {},
            "reason": "Input validation failed; skip tool selection.",
        }

    query = (state.get("query") or "").strip()

    if not query:
        return {
            "action": "respond_error",
            "tool": None,
            "args": {},
            "reason": "Empty query.",
        }

    # SAR check first because SAR queries can also contain "fetch".
    if _wants_sar(query):
        if not _has_bbox(state):
            return {
                "action": "clarify",
                "tool": None,
                "args": {},
                "reason": "SAR fetch requested but bbox is missing.",
            }

        args = {
            "bbox": state["bbox"],
            "start_date": (
                state.get("start_date")
                or settings.default_start_date
            ),
            "end_date": (
                state.get("end_date")
                or settings.default_end_date
            ),
            "width": (
                state.get("width")
                or settings.default_width
            ),
            "height": (
                state.get("height")
                or settings.default_height
            ),
            "crs": settings.default_crs,
        }

        return {
            "action": "call_tool",
            "tool": TOOL_SAR,
            "args": args,
            "reason": "Query looks like a Sentinel-1 SAR request.",
        }

    if _wants_fetch(query):
        if not _has_bbox(state):
            return {
                "action": "clarify",
                "tool": None,
                "args": {},
                "reason": "Fetch requested but bbox is missing.",
            }

        args = {
            "bbox": state["bbox"],
            "start_date": (
                state.get("start_date")
                or settings.default_start_date
            ),
            "end_date": (
                state.get("end_date")
                or settings.default_end_date
            ),
            "modality": (
                state.get("modality")
                or "optical"
            ),
            "bands": None,
            "max_cloud_cover": (
                state.get("max_cloud_cover")
                or settings.default_max_cloud_cover
            ),
            "width": (
                state.get("width")
                or settings.default_width
            ),
            "height": (
                state.get("height")
                or settings.default_height
            ),
            "crs": settings.default_crs,
        }

        return {
            "action": "call_tool",
            "tool": TOOL_FETCH,
            "args": args,
            "reason": "Query looks like a Sentinel-2 fetch request.",
        }

    return {
        "action": "chat",
        "tool": None,
        "args": {},
        "reason": "Query does not match a known remote-sensing tool.",
    }


# ---------------------------------------------------------------------------
# SkillKit
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=1)
def _build_skillkit() -> Any | None:
    """
    Build a SkillKit instance pointed at the skills/ directory.

    If SkillKit is unavailable, the planner uses the static system prompt.
    """

    from pathlib import Path

    skills_dir = (
        Path(__file__).parent.parent.parent / "skills"
    )

    if not skills_dir.is_dir():
        logger.warning(
            "skills/ directory not found at %s — SkillKit disabled.",
            skills_dir,
        )
        return None

    try:
        from langchain_skillkit import SkillKit

        kit = SkillKit(str(skills_dir))

        logger.info(
            "SkillKit loaded from %s",
            skills_dir,
        )

        return kit

    except ImportError:
        logger.warning(
            "langchain-skillkit not installed — SkillKit disabled."
        )
        return None

    except Exception as exc:
        logger.warning(
            "SkillKit failed to initialise (%r) — disabled.",
            exc,
        )
        return None


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=1)
def _build_base_llm() -> Any:
    """
    Build exactly ONE active LLM provider.

    Provider selection is controlled by:

        SATQUERY_USE_OPENAI
        SATQUERY_USE_CLAUDE

    Exactly one must be true.
    """

    # -----------------------------------------------------------------------
    # OpenAI
    # -----------------------------------------------------------------------
    if settings.use_openai:

        if settings.use_claude:
            raise ValueError(
                "Invalid LLM configuration: both OpenAI and Claude "
                "are enabled. Enable exactly one."
            )

        if not settings.openai_api_key:
            raise ValueError(
                "SATQUERY_USE_OPENAI=true but OPENAI_API_KEY is missing."
            )

        from langchain_openai import ChatOpenAI

        logger.info(
            "Using OpenAI LLM: %s",
            settings.openai_model,
        )

        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
        )

    # -----------------------------------------------------------------------
    # Claude
    # -----------------------------------------------------------------------
    if settings.use_claude:

        if not settings.claude_api_key:
            raise ValueError(
                "SATQUERY_USE_CLAUDE=true but "
                "ANTHROPIC_API_KEY is missing."
            )

        from langchain_anthropic import ChatAnthropic

        logger.info(
            "Using Claude LLM: %s",
            settings.claude_model,
        )

        return ChatAnthropic(
            model=settings.claude_model,
            api_key=settings.claude_api_key,
        )

    # -----------------------------------------------------------------------
    # No provider
    # -----------------------------------------------------------------------
    raise ValueError(
        "No LLM provider is enabled. "
        "Enable exactly one of "
        "SATQUERY_USE_OPENAI or SATQUERY_USE_CLAUDE."
    )


# ---------------------------------------------------------------------------
# JSON schema returned by the LLM
# ---------------------------------------------------------------------------
_PLAN_SCHEMA = {
    "title": "Plan",
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "call_tool",
                "clarify",
                "chat",
                "respond_error",
            ],
        },
        "tool": {
            "type": ["string", "null"],
        },
        "args": {
            "type": "object",
        },
        "reason": {
            "type": "string",
        },
    },
    "required": [
        "action",
        "tool",
        "args",
        "reason",
    ],
}


# ---------------------------------------------------------------------------
# LangMem tools
# ---------------------------------------------------------------------------
def _build_memory_tools(
    user_id: str | None,
) -> list[Any]:
    """
    Build LangMem manage + search tools scoped to a user namespace.
    """

    if settings.memory_backend == "none":
        return []

    try:
        from langmem import (
            create_manage_memory_tool,
            create_search_memory_tool,
        )

        uid = user_id or "anonymous"

        namespace = (
            "satquery",
            "memories",
            uid,
        )

        return [
            create_manage_memory_tool(
                namespace=namespace
            ),
            create_search_memory_tool(
                namespace=namespace
            ),
        ]

    except ImportError:
        logger.warning(
            "langmem not installed — memory tools disabled."
        )
        return []

    except Exception as exc:
        logger.warning(
            "Failed to build memory tools (%r) — memory disabled.",
            exc,
        )
        return []


# ---------------------------------------------------------------------------
# Structured LLM client
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=1)
def _build_llm_client() -> Any:
    """
    Return a structured-output LLM client.

    The base LLM is created exactly once.
    """

    base = _build_base_llm()

    kit = _build_skillkit()

    if kit is not None:
        llm_with_tools = base.bind_tools(
            kit.tools
        )

        return llm_with_tools.with_structured_output(
            _PLAN_SCHEMA
        )

    return base.with_structured_output(
        _PLAN_SCHEMA
    )


# ---------------------------------------------------------------------------
# Real LLM planner
# ---------------------------------------------------------------------------
def _llm_plan(state: SatQueryState) -> Plan:
    """
    Call the selected real LLM to produce a Plan.

    IMPORTANT:
    LLM failures are NOT silently converted into the keyword planner.
    """

    from langchain_core.messages import (
        HumanMessage,
        SystemMessage,
    )

    # Use SkillKit prompt when available.
    system_prompt = (
        SKILLKIT_SYSTEM_PROMPT
        if _build_skillkit() is not None
        else STATIC_SYSTEM_PROMPT
    )

    # Keep the LLM input concise.
    bbox_str = (
        str(state.get("bbox"))
        if state.get("bbox")
        else "not provided"
    )

    user_msg = (
        f"Query: {state.get('query', '')}\n"
        f"Bounding box: {bbox_str}\n"
        f"Start date: "
        f"{state.get('start_date') or 'not provided'}\n"
        f"End date: "
        f"{state.get('end_date') or 'not provided'}\n"
        f"Validation errors: "
        f"{state.get('errors') or 'none'}"
    )

    client = _build_llm_client()

    # Inject user-specific memory tools if enabled.
    memory_tools = _build_memory_tools(
        state.get("user_id")
    )

    if memory_tools:
        client = client.bind_tools(
            memory_tools
        )

    try:
        result: dict[str, Any] = client.invoke(
            [
                SystemMessage(
                    content=system_prompt
                ),
                HumanMessage(
                    content=user_msg
                ),
            ]
        )

        # Validate LLM action.
        valid_actions = {
            "call_tool",
            "clarify",
            "chat",
            "respond_error",
        }

        if result.get("action") not in valid_actions:
            raise ValueError(
                "LLM returned unknown action: "
                f"{result.get('action')!r}"
            )

        # Fill missing tool arguments from state.
        if (
            result["action"] == "call_tool"
            and not result.get("args")
        ):
            result["args"] = {
                "bbox": state.get("bbox"),
                "start_date": (
                    state.get("start_date")
                    or settings.default_start_date
                ),
                "end_date": (
                    state.get("end_date")
                    or settings.default_end_date
                ),
                "modality": (
                    state.get("modality")
                    or "optical"
                ),
                "bands": None,
                "max_cloud_cover": (
                    state.get("max_cloud_cover")
                    or settings.default_max_cloud_cover
                ),
                "width": (
                    state.get("width")
                    or settings.default_width
                ),
                "height": (
                    state.get("height")
                    or settings.default_height
                ),
                "crs": settings.default_crs,
            }

        return Plan(
            action=result["action"],
            tool=result.get("tool"),
            args=result.get("args") or {},
            reason=result.get("reason", ""),
        )

    except Exception:
        logger.exception(
            "LLM planner failed."
        )

        # IMPORTANT:
        # Do NOT silently fall back to keyword planning.
        raise


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def make_plan(state: SatQueryState) -> Plan:
    """
    Return a Plan.

    SATQUERY_MOCK_PLANNER=true
        → keyword planner, no LLM

    SATQUERY_MOCK_PLANNER=false
        → selected OpenAI OR Claude planner

    Exactly one real LLM provider must be enabled.
    """

    if settings.use_mock_planner:
        return _keyword_plan(state)

    return _llm_plan(state)