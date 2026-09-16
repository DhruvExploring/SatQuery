"""Conditional routing for the outer SatQuery graph."""
from __future__ import annotations
from backend.orchestrator.state import SatQueryState


def route_after_validate(state: SatQueryState) -> str:
    """Skip knowledge-base loading, the VLM first pass, and the tool loop
    entirely when input validation already failed -- there's nothing valid
    to ground a description in, and respond() reports the error directly."""
    return "error" if state.get("errors") else "continue"


def route_after_load_kb(state: SatQueryState) -> str:
    """Only run the VLM first-pass description when there's actually a
    knowledge base to ground it in (i.e. an uploaded/validated image)."""
    return "describe" if state.get("knowledge_base") else "skip"
