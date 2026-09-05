"""SatQuery LangGraph State — the clipboard for one user request.

Every node reads this dict and returns only the fields it wants to change.
LangGraph merges those updates back into State.

Why a TypedDict instead of a random dict:
- Nodes agree on field names (no silent typos)
- Optional fields are explicit
- tool_results / errors use reducers so values APPEND instead of overwrite
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Any, Literal, NotRequired, TypedDict


PlanAction = Literal["call_tool", "clarify", "chat", "respond_error"]


class Plan(TypedDict):
    """Planner output. The router reads this; tools never see it."""

    action: PlanAction
    tool: str | None
    args: dict[str, Any]
    reason: str


class ToolResult(TypedDict):
    """One MCP-shaped JSON blob stored after a tool runs."""

    tool: str
    result: dict[str, Any]


class SatQueryState(TypedDict):
    """Shared state for one `graph.invoke()` call."""

    query: str

    # Identity — used by LangMem to scope memories per user.
    # Optional: if absent, memories are stored in a shared anonymous namespace.
    user_id: NotRequired[str | None]

    bbox: NotRequired[list[float] | None]
    start_date: NotRequired[str | None]
    end_date: NotRequired[str | None]
    modality: NotRequired[str]
    max_cloud_cover: NotRequired[float]
    width: NotRequired[int]
    height: NotRequired[int]

    plan: NotRequired[Plan | None]

    # Annotated[..., add] means: if a node returns a list, concatenate it.
    # Execute therefore returns {"tool_results": [one_item]}, not the full history.
    tool_results: Annotated[list[ToolResult], add]
    errors: Annotated[list[str], add]

    final_answer: NotRequired[str | None]
    status: NotRequired[str]


def empty_state(query: str, **overrides: Any) -> SatQueryState:
    """Build a valid initial clipboard. Always start lists as empty."""

    state: SatQueryState = {
        "query": query,
        "user_id": None,
        "bbox": None,
        "start_date": None,
        "end_date": None,
        "modality": "optical",
        "max_cloud_cover": 30.0,
        "width": 512,
        "height": 512,
        "plan": None,
        "tool_results": [],
        "errors": [],
        "final_answer": None,
        "status": "pending",
    }
    state.update(overrides)
    return state
