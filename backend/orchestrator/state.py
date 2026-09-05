"""SatQuery LangGraph State — clipboard for one user request."""

from __future__ import annotations

from datetime import datetime, timezone
from operator import add
from typing import Annotated, Any, Literal, NotRequired, TypedDict

PlanAction = Literal["call_tool", "clarify", "chat", "respond_error"]


class Plan(TypedDict):
    action: PlanAction
    tool: str | None
    args: dict[str, Any]
    reason: str


class ToolResult(TypedDict):
    tool: str
    result: dict[str, Any]
    duration_ms: NotRequired[float]
    timestamp: NotRequired[str]


class ExecutionTraceEntry(TypedDict):
    node: str
    timestamp: str
    summary: str


class SatQueryState(TypedDict):
    query: str
    bbox: NotRequired[list[float] | None]
    latitude: NotRequired[float | None]
    longitude: NotRequired[float | None]
    start_date: NotRequired[str | None]
    end_date: NotRequired[str | None]
    bands: NotRequired[list[str] | None]
    max_cloud_cover: NotRequired[float]
    width: NotRequired[int]
    height: NotRequired[int]
    polarization: NotRequired[list[str] | None]
    orbit_direction: NotRequired[str | None]
    scene_selection: NotRequired[str | None]
    plan: NotRequired[Plan | None]
    tool_results: Annotated[list[ToolResult], add]
    errors: Annotated[list[str], add]
    execution_trace: Annotated[list[ExecutionTraceEntry], add]
    final_answer: NotRequired[str | None]
    status: NotRequired[str]


def trace_entry(node: str, summary: str) -> ExecutionTraceEntry:
    """One debug row. Never put secrets (API keys, tokens) in summary."""
    return {
        "node": node,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
    }


def empty_state(query: str, **overrides: Any) -> SatQueryState:
    state: SatQueryState = {
        "query": query,
        "bbox": None,
        "latitude": None,
        "longitude": None,
        "start_date": None,
        "end_date": None,
        "bands": None,
        "max_cloud_cover": 30.0,
        "width": 512,
        "height": 512,
        "polarization": None,
        "orbit_direction": None,
        "scene_selection": None,
        "plan": None,
        "tool_results": [],
        "errors": [],
        "execution_trace": [],
        "final_answer": None,
        "status": "pending",
    }
    state.update(overrides)
    return state
