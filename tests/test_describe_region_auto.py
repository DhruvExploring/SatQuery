"""describe_marked_region now runs deterministically, once, before the
tool-loop planner is consulted -- whenever region_bbox is present -- instead
of being left to the planner's discretion (which was observed to sometimes
skip it entirely; see backend/orchestrator/nodes.py::describe_region_if_marked).
"""
from __future__ import annotations

from backend.orchestrator.graph import build_graph
from backend.orchestrator.nodes import describe_region_if_marked
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
