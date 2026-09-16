"""The recursive start->llm->tool->end subgraph: multi-hop chaining, the
"already succeeded, stop repeating" guard, and the max-hops safety cap.

These use a scripted planner (not the real keyword/LLM planner) because
chaining multiple *distinct* tool calls together is now entirely up to the
LLM's own reasoning (guided by the routing hints in llm.py) rather than a
deterministic agenda -- there's no fixed sequence left to assert against
via keyword matching alone, so these tests verify the loop mechanics
directly: it executes whatever sequence the planner decides, threads state
between hops, and stops correctly.
"""

from __future__ import annotations

import backend.orchestrator.llm as llm_module
from backend.orchestrator.state import empty_state
from backend.orchestrator.tool_loop_graph import MAX_TOOL_HOPS, tool_loop_subgraph

DELHI = [77.10, 28.50, 77.30, 28.70]


def _tools(result) -> list[str]:
    return [item["tool"] for item in result.get("tool_results") or []]


def test_loop_stops_immediately_when_planner_says_chat(monkeypatch):
    monkeypatch.setattr(
        llm_module,
        "plan_single_tool",
        lambda state: {"action": "chat", "tool": None, "args": {}, "reason": "nothing needed"},
    )
    result = tool_loop_subgraph.invoke(empty_state(query="hello"))
    assert result["tool_results"] == []
    assert result["plan"]["action"] == "chat"


def test_loop_executes_a_scripted_two_hop_chain(monkeypatch):
    plans = [
        {
            "action": "call_tool",
            "tool": "fetch_multispectral_imagery",
            "args": {},
            "reason": "fetch first",
        },
        {
            "action": "call_tool",
            "tool": "compute_vegetation_indices",
            "args": {},
            "reason": "then compute indices",
        },
        {"action": "chat", "tool": None, "args": {}, "reason": "done"},
    ]
    calls = iter(plans)
    monkeypatch.setattr(llm_module, "plan_single_tool", lambda state: next(calls))

    result = tool_loop_subgraph.invoke(empty_state(query="ndvi please", bbox=DELHI))

    assert _tools(result) == ["fetch_multispectral_imagery", "compute_vegetation_indices"]
    assert result["tool_hops"] == 2
    # The fetch's output path was threaded into the next hop's trusted args.
    fetch_path = result["tool_results"][0]["result"]["data"]["file_path"]
    assert result["tool_results"][1]["result"]["request"]["file_path"] == fetch_path
    assert result["plan"]["action"] == "chat"


def test_loop_respects_max_tool_hops(monkeypatch):
    monkeypatch.setattr(
        llm_module,
        "plan_single_tool",
        lambda state: {
            "action": "call_tool",
            "tool": "fetch_optical_imagery",
            "args": {},
            "reason": "always fetch",
        },
    )
    result = tool_loop_subgraph.invoke(empty_state(query="fetch", bbox=DELHI))

    assert len(result["tool_results"]) == MAX_TOOL_HOPS
    assert result["plan"]["action"] == "respond_error"
    assert any("max tool hops" in err.lower() for err in result["errors"])


def test_inspect_geotiff_metadata_grounds_bbox_for_next_hop(monkeypatch):
    """A fetch tool missing only a bbox becomes reachable after an
    inspect_geotiff_metadata hop derives one from the file's own bounds --
    the replacement for handshake.py's old auto-bbox-derivation chain."""
    import backend.tools.executor as executor

    def _stub_with_bounds(name, args):
        if name == "inspect_geotiff_metadata":
            return {
                "status": "success",
                "file": {"file_path": args.get("file_path") or "mock.tif"},
                "spatial": {
                    "crs": "EPSG:4326",
                    "bounds_wgs84": {
                        "min_lon": 77.10,
                        "min_lat": 28.50,
                        "max_lon": 77.30,
                        "max_lat": 28.70,
                    },
                },
                "compatibility": {"pixelwise_operation_ready": True},
            }
        return {
            "status": "success",
            "data": {"file_path": f"mock_{name}.tif", "file_name": f"mock_{name}.tif"},
        }

    import backend.orchestrator.tool_loop_graph as tool_loop_graph

    monkeypatch.setattr(tool_loop_graph, "execute_tool", _stub_with_bounds)
    monkeypatch.setattr(executor, "execute_tool", _stub_with_bounds)

    plans = [
        {
            "action": "call_tool",
            "tool": "inspect_geotiff_metadata",
            "args": {},
            "reason": "derive bbox from the uploaded file",
        },
        {"action": "chat", "tool": None, "args": {}, "reason": "done"},
    ]
    calls = iter(plans)
    monkeypatch.setattr(llm_module, "plan_single_tool", lambda state: next(calls))

    result = tool_loop_subgraph.invoke(
        empty_state(query="what's here", input_file="uploaded.tif")
    )

    assert result["bbox"] == [77.10, 28.50, 77.30, 28.70]
    assert result["latitude"] == 28.60
    assert round(result["longitude"], 6) == 77.2
