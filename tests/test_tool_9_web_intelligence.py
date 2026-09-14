"""Unit and integration tests for Tool 9: fetch_web_intelligence."""

import os
from unittest.mock import MagicMock, patch
import pytest

from Tool_9_fetch_web_intelligence.fetch_web_intelligence import (
    WebIntelligenceRequest,
    fetch_web_intelligence,
)
from backend.orchestrator.registry import (
    TOOL_WEB,
    match_tool_from_query,
    trusted_args_for_tool,
    format_tool_success,
    location_ready_for_tool,
)
from backend.orchestrator.state import empty_state
from backend.tools.executor import execute_tool


def test_web_intelligence_request_validation():
    req = WebIntelligenceRequest(query="Delhi Yamuna flood Hathnikund barrage", max_results=3)
    assert req.query == "Delhi Yamuna flood Hathnikund barrage"
    assert req.max_results == 3
    assert req.search_depth == "basic"

    with pytest.raises(ValueError):
        WebIntelligenceRequest(query="   ")


def test_web_intelligence_tavily_mocked():
    mock_tavily_response = {
        "answer": "The July 2023 Delhi floods were caused by Hathnikund barrage discharge.",
        "results": [
            {
                "title": "Delhi Flood 2023",
                "url": "https://example.com/delhi-flood",
                "content": "Water level reached 208.66m at Old Railway Bridge.",
                "score": 0.95,
            }
        ]
    }

    with patch("Tool_9_fetch_web_intelligence.fetch_web_intelligence._execute_tavily_search") as mock_tavily:
        mock_tavily.return_value = {
            "status": "success",
            "provider": "tavily",
            "fallback_triggered": False,
            "fallback_reason": None,
            "query": "Delhi flood 2023",
            "results_count": 1,
            "summary": mock_tavily_response["answer"],
            "results": mock_tavily_response["results"],
        }

        req = WebIntelligenceRequest(query="Delhi flood 2023")
        res = fetch_web_intelligence(req)

        assert res["status"] == "success"
        assert res["provider"] == "tavily"
        assert res["fallback_triggered"] is False
        assert len(res["results"]) == 1
        assert "208.66m" in res["results"][0]["content"]


def test_web_intelligence_duckduckgo_fallback_on_tavily_failure():
    """Verify that when Tavily raises an exception (quota exceeded / network error),
    the tool gracefully and automatically falls back to DuckDuckGo."""
    with patch("Tool_9_fetch_web_intelligence.fetch_web_intelligence._execute_tavily_search") as mock_tavily, \
         patch("Tool_9_fetch_web_intelligence.fetch_web_intelligence._execute_duckduckgo_search") as mock_ddg:

        mock_tavily.side_effect = RuntimeError("HTTP 429: Monthly rate limit / quota exceeded (1000 searches reached)")
        mock_ddg.return_value = {
            "status": "success",
            "provider": "duckduckgo",
            "fallback_triggered": True,
            "fallback_reason": "Tavily search failed (HTTP 429: Monthly rate limit / quota exceeded) — automatic fail-safe to DuckDuckGo engaged",
            "query": "Dwarka Expressway construction status",
            "results_count": 2,
            "summary": "Dwarka Expressway is an 8-lane expressway connecting Delhi and Gurugram.",
            "results": [
                {"title": "Dwarka Expressway Details", "url": "https://example.com/dwarka", "content": "8-lane elevated highway", "score": None}
            ],
        }

        req = WebIntelligenceRequest(query="Dwarka Expressway construction status")
        res = fetch_web_intelligence(req)

        assert res["status"] == "success"
        assert res["provider"] == "duckduckgo"
        assert res["fallback_triggered"] is True
        assert "Dwarka Expressway" in res["summary"]


def test_executor_runs_web_intelligence():
    with patch("Tool_9_fetch_web_intelligence.fetch_web_intelligence.fetch_web_intelligence") as mock_fn:
        mock_fn.return_value = {
            "status": "success",
            "provider": "tavily",
            "fallback_triggered": False,
            "fallback_reason": None,
            "query": "what caused the flood",
            "results_count": 1,
            "summary": "Heavy rainfall upstream.",
            "results": [],
        }

        out = execute_tool("fetch_web_intelligence", {"query": "what caused the flood", "max_results": 3})
        assert out["status"] == "success"
        assert out["provider"] == "tavily"


def test_planner_routes_ground_truth_query_to_web_intelligence():
    tool, reason = match_tool_from_query("what caused the flood in Delhi")
    assert tool == TOOL_WEB

    tool2, _ = match_tool_from_query("what is the ground reality of Hathnikund barrage")
    assert tool2 == TOOL_WEB

    tool3, _ = match_tool_from_query("which expressway is this infrastructure project")
    assert tool3 == TOOL_WEB


def test_registry_helpers_for_web_intelligence():
    state = empty_state("what caused the flood", location_hint="Delhi, India")
    args = trusted_args_for_tool(TOOL_WEB, state)
    assert args["query"] == "what caused the flood"
    assert args["location_hint"] == "Delhi, India"

    assert location_ready_for_tool(TOOL_WEB, state) is True

    formatted = format_tool_success(TOOL_WEB, {
        "status": "success",
        "provider": "tavily",
        "fallback_triggered": False,
        "summary": "3.59 lakh cusecs water released.",
    })
    assert "3.59 lakh cusecs water released." in formatted
    assert "[Tavily]" not in formatted


def test_clean_final_output_strips_internal_markers():
    from backend.orchestrator.nodes import clean_final_output

    sample1 = "Completed 2-step handshake. [Tavily] 3.59 lakh cusecs released from Hathnikund."
    assert clean_final_output(sample1) == "3.59 lakh cusecs released from Hathnikund."

    sample2 = "Completed 1-step handshake. [DuckDuckGo (Fail-safe)] Flood caused by Yamuna."
    assert clean_final_output(sample2) == "Flood caused by Yamuna."

    sample3 = "Thought: Need to search.\n3.59 lakh cusecs released."
    assert clean_final_output(sample3) == "3.59 lakh cusecs released."


def test_web_intelligence_handshake_single_step():
    from backend.orchestrator.handshake import apply_advance

    state = empty_state("what caused the flood in Delhi")
    state["intent"] = "single_tool"
    state["agenda"] = [{"tool": "fetch_web_intelligence", "role": "single"}]
    state["agenda_index"] = 0
    state["tool_results"] = [
        {
            "tool": "fetch_web_intelligence",
            "result": {
                "status": "success",
                "provider": "tavily",
                "summary": "Flood caused by Hathnikund release.",
            },
        }
    ]
    adv = apply_advance(state)
    assert adv["handshake_complete"] is True


def test_duplicate_tool_prevention_in_build_plan_update():
    from backend.orchestrator.handshake import build_plan_update

    state = empty_state("what caused the flood in Delhi")
    state["intent"] = "single_tool"
    state["agenda"] = [{"tool": "fetch_web_intelligence", "role": "single"}]
    state["agenda_index"] = 1
    state["handshake_complete"] = False
    state["tool_results"] = [
        {
            "tool": "fetch_web_intelligence",
            "result": {
                "status": "success",
                "provider": "tavily",
                "summary": "Flood caused by Hathnikund release.",
            },
        }
    ]

    def mock_repeat_planner(_state):
        return {"action": "call_tool", "tool": "fetch_web_intelligence", "args": {}, "reason": "Gather more info"}

    update = build_plan_update(state, mock_repeat_planner)
    assert update["handshake_complete"] is True
    assert update["plan"]["action"] == "finish"


def test_enforce_call_tool_location_preserves_formulated_web_query():
    from backend.orchestrator.registry import enforce_call_tool_location

    state = empty_state("Which drainage channel breached in Vijayawada flood Sept 2024?")
    formulated_query = "Vijayawada September 2024 flood drainage channel breach rivulet stream"

    planned = {
        "action": "call_tool",
        "tool": "fetch_web_intelligence",
        "args": {"query": formulated_query},
        "reason": "Search for specific drainage channel breach in Vijayawada.",
    }

    guarded = enforce_call_tool_location(planned, state)
    assert guarded["action"] == "call_tool"
    assert guarded["args"]["query"] == formulated_query


