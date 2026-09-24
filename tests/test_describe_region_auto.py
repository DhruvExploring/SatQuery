"""describe_marked_region now runs deterministically, once, before the
tool-loop planner is consulted -- whenever region_bbox is present -- instead
of being left to the planner's discretion (which was observed to sometimes
skip it entirely; see backend/orchestrator/nodes.py::describe_region_if_marked).
"""
from __future__ import annotations

from backend.orchestrator.graph import build_graph
from backend.orchestrator.nodes import describe_region_if_marked, vlm_initial_description
from backend.orchestrator.registry import TOOL_DESCRIBE_REGION
from backend.orchestrator.state import empty_state

REGION = [77.15, 28.55, 77.20, 28.60]


def test_no_op_without_a_marked_region():
    update = describe_region_if_marked(empty_state(query="describe this", input_file="scene.tif"))
    assert "tool_results" not in update
    assert update["execution_trace"][0]["summary"] == "no marked region"


def test_no_op_without_an_input_file():
    update = describe_region_if_marked(empty_state(query="describe this", region_bbox=REGION))
    assert "tool_results" not in update


def test_runs_and_records_tool_result_when_region_marked():
    state = empty_state(query="what's in this region?", input_file="scene.tif", region_bbox=REGION)
    update = describe_region_if_marked(state)
    assert update["tool_results"][0]["tool"] == TOOL_DESCRIBE_REGION
    assert update["tool_results"][0]["result"]["status"] == "success"
    assert update["tool_hops"] == 1


def test_graph_runs_describe_region_before_the_planner_and_never_repeats_it():
    # No knowledge base on disk for this path -> vlm_initial_description is
    # skipped (route_after_load_kb), isolating describe_region_auto's own
    # behavior: it must still fire from region_bbox alone, and the keyword
    # planner (whose query text -- "the marked region" -- would otherwise
    # match TOOL_DESCRIBE_REGION again) must not call it a second time.
    graph = build_graph()
    result = graph.invoke(
        empty_state(
            query="what is in the marked region?",
            input_file="scene.tif",
            region_bbox=REGION,
        )
    )
    tools_called = [r["tool"] for r in result["tool_results"]]
    assert tools_called.count(TOOL_DESCRIBE_REGION) == 1
    assert result["status"] == "success"

    nodes = [row["node"] for row in result["execution_trace"]]
    assert "describe_region_auto" in nodes
    assert nodes.index("describe_region_auto") < nodes.index("llm")


def test_vlm_initial_description_derives_region_bbox_when_vision_call_returns_one(monkeypatch):
    """The automatic first-call (analyze_imagery_vlm, fired before the
    planner is ever consulted) needs its own copy of the affine-converted
    region_bbox merge -- it goes through execute_tool() directly, not
    tool_loop_graph.py's tool_node, so a query like "mark the river" whose
    bbox comes back on this very first call must still surface region_bbox
    for describe_region_auto to pick up right after."""
    import backend.orchestrator.nodes as nodes_module

    def _stub(name, args):
        assert name == "analyze_imagery_vlm"
        return {
            "status": "success",
            "text": "the Yamuna river",
            "bbox": [0.6, 0.2, 0.8, 0.9],
            "region_bbox": REGION,
        }

    monkeypatch.setattr(nodes_module, "execute_tool", _stub)

    state = empty_state(query="mark the river", input_file="scene.tif")
    update = vlm_initial_description(state)
    assert update["region_bbox"] == REGION


def test_vlm_initial_description_never_overwrites_an_existing_region_bbox(monkeypatch):
    import backend.orchestrator.nodes as nodes_module

    def _stub(name, args):
        return {
            "status": "success",
            "text": "something else",
            "bbox": [0.0, 0.0, 1.0, 1.0],
            "region_bbox": [10.0, 10.0, 20.0, 20.0],
        }

    monkeypatch.setattr(nodes_module, "execute_tool", _stub)

    state = empty_state(query="describe this", input_file="scene.tif", region_bbox=REGION)
    update = vlm_initial_description(state)
    assert "region_bbox" not in update


def test_graph_grounds_a_bbox_from_the_automatic_initial_call(monkeypatch, tmp_path):
    """End-to-end: a region_bbox surfacing from vlm_initial_description's own
    call (not a later planner-chosen mark_region_in_image call) still reaches
    describe_region_auto in the same graph run, before the planner sees it.
    Needs a knowledge base on disk (route_after_load_kb's gate for running
    vlm_initial_description at all) -- same fixture shape as
    test_upload_flow.py."""
    import json

    import backend.orchestrator.nodes as nodes_module

    input_file = tmp_path / "scene.tif"
    input_file.write_bytes(b"")  # never opened -- execute_tool is stubbed
    kb_path = tmp_path / "scene.kb.json"
    kb_path.write_text(json.dumps({"file_path": str(input_file)}))

    def _stub(name, args):
        if name == "analyze_imagery_vlm":
            return {
                "status": "success",
                "text": "the Yamuna river",
                "bbox": [0.6, 0.2, 0.8, 0.9],
                "region_bbox": REGION,
            }
        if name == TOOL_DESCRIBE_REGION:
            return {"status": "success", "text": "A mock description of the marked region."}
        return {"status": "success"}

    monkeypatch.setattr(nodes_module, "execute_tool", _stub)

    graph = build_graph()
    result = graph.invoke(
        empty_state(query="mark the river in this image", input_file=str(input_file))
    )

    assert result["region_bbox"] == REGION
    tools_called = [r["tool"] for r in result["tool_results"]]
    assert TOOL_DESCRIBE_REGION in tools_called

    nodes = [row["node"] for row in result["execution_trace"]]
    assert nodes.index("vlm_initial_description") < nodes.index("describe_region_auto")
