"""Conditional routing after planner and handshake advance."""
from __future__ import annotations
from backend.orchestrator.state import SatQueryState

def route_after_plan(state: SatQueryState) -> str:
    plan = state.get("plan") or {}
    return "execute" if plan.get("action") == "call_tool" else "respond"


def route_after_advance(state: SatQueryState) -> str:
    if state.get("handshake_complete"):
        return "respond"
    if state.get("errors"):
        return "respond"
    plan = state.get("plan") or {}
    idx = int(state.get("agenda_index") or 0)
    agenda = state.get("agenda") or []
    if idx >= len(agenda):
        return "respond"
    if plan.get("action") != "call_tool":
        return "respond"
    return "continue"
