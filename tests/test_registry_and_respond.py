from backend.orchestrator.nodes import respond
from backend.orchestrator.registry import (
    PLANNER_PRIORITY,
    TOOL_SPEC,
    TOOL_OPTICAL,
    TOOL_WEATHER,
    enforce_call_tool_location,
    location_ready_for_tool,
)
from backend.orchestrator.state import empty_state


def test_every_tool_spec_has_required_fields():
    required = {
        "name",
        "description",
        "requires",
        "keywords",
        "args_builder",
        "response_formatter",
    }
    assert PLANNER_PRIORITY == (
        "fetch_sar_imagery",
        "fetch_weather_environment",
        "fetch_multispectral_imagery",
        "fetch_optical_imagery",
    )
    for name, spec in TOOL_SPEC.items():
        assert set(spec) >= required
        assert spec["name"] == name
        assert spec["keywords"]
        assert spec["requires"]


def test_respond_error_uses_plan_reason_when_errors_empty():
    result = respond(
        {
            "query": "fetch",
            "plan": {
                "action": "respond_error",
                "tool": None,
                "args": {},
                "reason": "Planner rejected this request.",
            },
            "tool_results": [],
            "errors": [],
        }
    )
    assert result["status"] == "error"
    assert result["final_answer"] == "Planner rejected this request."


def test_respond_error_falls_back_when_reason_blank():
    result = respond(
        {
            "query": "fetch",
            "plan": {
                "action": "respond_error",
                "tool": None,
                "args": {},
                "reason": "",
            },
            "tool_results": [],
            "errors": [],
        }
    )
    assert result["status"] == "error"
    assert result["final_answer"] == "Request could not be processed."


def test_validation_errors_still_win_over_respond_error_reason():
    result = respond(
        {
            "query": "fetch",
            "plan": {
                "action": "respond_error",
                "tool": None,
                "args": {},
                "reason": "Planner rejected this request.",
            },
            "tool_results": [],
            "errors": ["bbox longitude must be between -180 and 180."],
        }
    )
    assert result["status"] == "error"
    assert "bbox longitude" in result["final_answer"]


def test_llm_call_tool_without_bbox_downgrades_to_clarify():
    planned = {
        "action": "call_tool",
        "tool": TOOL_OPTICAL,
        "args": {"bbox": None, "start_date": "2025-01-01"},
        "reason": "LLM hallucinated a fetch.",
    }
    state = empty_state(query="Fetch Sentinel-2 optical imagery for Delhi.")
    guarded = enforce_call_tool_location(planned, state)
    assert guarded["action"] == "clarify"
    assert guarded["tool"] is None
    assert "bbox" in guarded["reason"]


def test_llm_call_tool_with_bbox_passes_guard():
    planned = {
        "action": "call_tool",
        "tool": TOOL_OPTICAL,
        "args": {},
        "reason": "ok",
    }
    state = empty_state(
        query="Fetch Sentinel-2 optical imagery for Delhi.",
        bbox=[77.10, 28.50, 77.30, 28.70],
    )
    assert enforce_call_tool_location(planned, state)["action"] == "call_tool"


def test_weather_location_accepts_lat_lon():
    state = empty_state(
        query="Get weather",
        latitude=28.61,
        longitude=77.21,
    )
    assert location_ready_for_tool(TOOL_WEATHER, state)
    assert not location_ready_for_tool(TOOL_OPTICAL, state)
