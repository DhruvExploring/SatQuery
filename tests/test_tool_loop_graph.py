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


def test_mark_region_result_fills_empty_region_bbox(monkeypatch):
    """A mark_region_in_image call whose bbox was affine-converted to an
    exact WGS84 region_bbox (backend/tools/executor.py::_geometry_to_region_fields)
    should thread that region_bbox into state for the next hop, the same way
    inspect_geotiff_metadata's derived bbox does above."""
    import backend.orchestrator.tool_loop_graph as tool_loop_graph

    def _stub(name, args):
        if name == "mark_region_in_image":
            return {
                "status": "success",
                "text": "the flooded field is here",
                "bbox": [0.25, 0.25, 0.75, 0.75],
                "region_bbox": [77.21, 28.63, 77.27, 28.67],
            }
        return {"status": "success"}

    monkeypatch.setattr(tool_loop_graph, "execute_tool", _stub)

    plans = [
        {
            "action": "call_tool",
            "tool": "mark_region_in_image",
            "args": {},
            "reason": "locate the flooded field",
        },
        {"action": "chat", "tool": None, "args": {}, "reason": "done"},
    ]
    calls = iter(plans)
    monkeypatch.setattr(llm_module, "plan_single_tool", lambda state: next(calls))

    result = tool_loop_subgraph.invoke(
        empty_state(query="mark the flooded field", input_file="uploaded.tif")
    )

    assert result["region_bbox"] == [77.21, 28.63, 77.27, 28.67]


def test_mark_region_result_also_threads_region_polygon_and_centroid(monkeypatch):
    """When mark_region_in_image's result includes an affine-converted
    polygon (an elongated feature's own path) and centroid, both should
    thread onto state alongside region_bbox, for describe_marked_region's
    masking and _region_center's more accurate anchor point."""
    import backend.orchestrator.tool_loop_graph as tool_loop_graph

    polygon = [{"latitude": 28.66, "longitude": 77.22}, {"latitude": 28.65, "longitude": 77.24}, {"latitude": 28.64, "longitude": 77.26}]
    centroid = {"latitude": 28.65, "longitude": 77.24}

    def _stub(name, args):
        if name == "mark_region_in_image":
            return {
                "status": "success",
                "text": "the river runs through here",
                "bbox": [0.25, 0.25, 0.75, 0.75],
                "polygon": [[0.25, 0.1], [0.5, 0.5], [0.75, 0.9]],
                "region_bbox": [77.21, 28.63, 77.27, 28.67],
                "region_polygon": polygon,
                "region_centroid": centroid,
            }
        return {"status": "success"}

    monkeypatch.setattr(tool_loop_graph, "execute_tool", _stub)

    plans = [
        {
            "action": "call_tool",
            "tool": "mark_region_in_image",
            "args": {},
            "reason": "locate the river",
        },
        {"action": "chat", "tool": None, "args": {}, "reason": "done"},
    ]
    calls = iter(plans)
    monkeypatch.setattr(llm_module, "plan_single_tool", lambda state: next(calls))

    result = tool_loop_subgraph.invoke(
        empty_state(query="mark the river", input_file="uploaded.tif")
    )

    assert result["region_polygon"] == polygon
    assert result["region_centroid"] == centroid


def test_mark_region_never_overwrites_an_existing_region_bbox(monkeypatch):
    """A user-drawn region_bbox is a deliberate, more specific signal --
    a later mark_region_in_image call (e.g. a general description that
    happens to also return a bbox) must not clobber it."""
    import backend.orchestrator.tool_loop_graph as tool_loop_graph

    def _stub(name, args):
        return {
            "status": "success",
            "text": "something else entirely",
            "bbox": [0.0, 0.0, 1.0, 1.0],
            "region_bbox": [10.0, 10.0, 20.0, 20.0],
        }

    monkeypatch.setattr(tool_loop_graph, "execute_tool", _stub)

    plans = [
        {
            "action": "call_tool",
            "tool": "mark_region_in_image",
            "args": {},
            "reason": "locate something",
        },
        {"action": "chat", "tool": None, "args": {}, "reason": "done"},
    ]
    calls = iter(plans)
    monkeypatch.setattr(llm_module, "plan_single_tool", lambda state: next(calls))

    original_region_bbox = [77.21, 28.63, 77.27, 28.67]
    result = tool_loop_subgraph.invoke(
        empty_state(
            query="mark something",
            input_file="uploaded.tif",
            region_bbox=original_region_bbox,
        )
    )

    assert result["region_bbox"] == original_region_bbox
