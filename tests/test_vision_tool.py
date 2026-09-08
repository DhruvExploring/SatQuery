"""Vision tool: registry wiring (keywords, args, location gate) and executor
dispatch with a stubbed provider — no real model call, no network.
"""
from __future__ import annotations

import dataclasses

from backend.orchestrator.registry import (
    TOOL_VLM,
    location_ready_for_tool,
    match_tool_from_query,
    trusted_args_for_tool,
)
from backend.orchestrator.state import empty_state

# tests/conftest.py globally stubs backend.tools.executor.execute_tool for the
# whole suite (so graph/planner tests never hit real APIs). That stub doesn't
# know about analyze_imagery_vlm, so these tests call the real dispatch
# function directly instead of going through the stubbed execute_tool().
from backend.tools.executor import _run_vlm_analysis


def test_vlm_keyword_match():
    tool, _reason = match_tool_from_query("Describe this image for me")
    assert tool == TOOL_VLM


def test_vlm_location_ready_requires_an_image():
    state = empty_state(query="describe this image")
    assert not location_ready_for_tool(TOOL_VLM, state)

    state["input_file"] = "some/rendered.png"
    assert location_ready_for_tool(TOOL_VLM, state)


def test_vlm_trusted_args_uses_query_and_input_file():
    state = empty_state(query="describe this image", input_file="some/rendered.png")
    args = trusted_args_for_tool(TOOL_VLM, state)
    assert args["image_path"] == "some/rendered.png"
    assert args["query"] == "describe this image"


def test_vlm_disabled_returns_validation_error(monkeypatch):
    import backend.tools.executor as executor

    monkeypatch.setattr(
        executor, "settings", dataclasses.replace(executor.settings, vision_tool_enabled=False)
    )
    result = _run_vlm_analysis({"image_path": "x.png", "query": "what is this?"})
    assert result["status"] == "error"
    assert result["error"]["type"] == "validation_error"


def test_vlm_missing_image_path_returns_validation_error(monkeypatch):
    import backend.tools.executor as executor

    monkeypatch.setattr(
        executor, "settings", dataclasses.replace(executor.settings, vision_tool_enabled=True)
    )
    result = _run_vlm_analysis({"image_path": None, "query": "what is this?"})
    assert result["status"] == "error"
    assert result["error"]["type"] == "validation_error"


def test_vlm_calls_configured_provider(monkeypatch):
    import backend.tools.executor as executor
    import backend.vision.factory as vision_factory

    monkeypatch.setattr(
        executor, "settings", dataclasses.replace(executor.settings, vision_tool_enabled=True)
    )

    class _StubProvider:
        def interpret(self, image_path: str, query: str) -> dict:
            return {"text": f"stub answer for {query}", "model": "stub", "provider": "stub"}

    monkeypatch.setattr(vision_factory, "get_vision_provider", lambda: _StubProvider())

    # A .png suffix skips the GeoTIFF-render step entirely, so this never
    # touches disk or rasterio.
    result = _run_vlm_analysis({"image_path": "x.png", "query": "what is this?"})
    assert result["status"] == "success"
    assert "stub answer" in result["text"]
