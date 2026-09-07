"""Conditional routing after the planner node."""
from __future__ import annotations
from backend.orchestrator.state import SatQueryState

def route_after_plan(state: SatQueryState) -> str:
    plan = state.get("plan") or {}
    return "execute" if plan.get("action") == "call_tool" else "respond"
