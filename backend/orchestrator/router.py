"""Deterministic routing after the planner node.

The LLM (or mock) only fills `plan`. This file decides the next node name.
Keep it free of prompts and MCP calls so it is trivial to unit-test.
"""

from __future__ import annotations

from typing import Literal

from backend.orchestrator.state import SatQueryState

Route = Literal["execute", "respond"]


def route_after_plan(state: SatQueryState) -> Route:
    plan = state.get("plan")
    if plan and plan.get("action") == "call_tool" and plan.get("tool"):
        return "execute"
    return "respond"
