"""Narrative synthesis: falls back to None (never raises) so respond() can use
the deterministic templated answer — a reliability safety net, mirroring the
existing planner -> keyword-planner fallback pattern already in llm.py. Not to
be confused with the (deliberately absent) automatic local/API mode failover.
"""
from __future__ import annotations

import dataclasses

import backend.orchestrator.synthesis as synthesis
from backend.orchestrator.state import empty_state


def test_synthesis_skipped_when_provider_is_mock():
    # conftest.py forces SATQUERY_ORCHESTRATOR_PROVIDER=mock for the whole suite.
    state = empty_state(query="fetch optical imagery")
    assert synthesis.synthesize_final_answer(state, tool_results=[]) is None


def test_synthesis_skipped_when_flag_disabled(monkeypatch):
    monkeypatch.setattr(
        synthesis,
        "settings",
        dataclasses.replace(
            synthesis.settings,
            orchestrator_provider="openai",
            orchestrator_synthesize_answer=False,
        ),
    )
    state = empty_state(query="fetch optical imagery")
    assert synthesis.synthesize_final_answer(state, tool_results=[]) is None


def test_synthesis_falls_back_to_none_when_llm_client_cannot_be_built(monkeypatch):
    # Bypass synthesis.py's own early "mock" short-circuit so the call actually
    # reaches _build_base_llm(). That function reads its own (unpatched, real
    # test-env) settings — provider=mock there too — so it raises ValueError,
    # exercising synthesize_final_answer's except-and-return-None safety net
    # exactly as a real build failure (bad key, network error) would.
    monkeypatch.setattr(
        synthesis,
        "settings",
        dataclasses.replace(
            synthesis.settings,
            orchestrator_provider="openai",
            orchestrator_synthesize_answer=True,
        ),
    )
    state = empty_state(query="fetch optical imagery")
    assert synthesis.synthesize_final_answer(state, tool_results=[]) is None
