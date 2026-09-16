"""End-to-end: an uploaded image with a knowledge base already on disk (as
ingest_graph.py would have written at upload time) grounds the VLM's first
description when a query comes in, before any further tool calls."""

from __future__ import annotations

import json

from backend.orchestrator.graph import build_graph
from backend.orchestrator.state import empty_state


def test_query_against_uploaded_image_loads_kb_and_describes_it(tmp_path):
    input_file = tmp_path / "scene.tif"
    input_file.write_bytes(b"")  # never opened -- execute_tool is stubbed
    kb_path = tmp_path / "scene.kb.json"
    knowledge_base = {
        "file_path": str(input_file),
        "bands": ["B02", "B03", "B04"],
        "latitude": 28.6,
        "longitude": 77.2,
        "place_name": "New Delhi, India",
    }
    kb_path.write_text(json.dumps(knowledge_base))

    graph = build_graph()
    result = graph.invoke(
        empty_state(query="Tell me about this scene", input_file=str(input_file))
    )

    assert result["knowledge_base"] == knowledge_base
    assert result["initial_description"] == "A mock description of the image."
    assert [r["tool"] for r in result["tool_results"]] == ["analyze_imagery_vlm"]
    assert result["status"] == "success"
    assert result["final_answer"] == "A mock description of the image."

    nodes = [row["node"] for row in result["execution_trace"]]
    assert nodes == [
        "validate",
        "load_knowledge_base",
        "vlm_initial_description",
        "describe_region_auto",
        "llm",
        "respond",
    ]


def test_query_without_uploaded_image_skips_vlm_description():
    graph = build_graph()
    result = graph.invoke(empty_state(query="What is the capital of France?"))

    assert result["knowledge_base"] is None
    assert result["initial_description"] is None
    nodes = [row["node"] for row in result["execution_trace"]]
    assert "vlm_initial_description" not in nodes
    assert nodes[:2] == ["validate", "load_knowledge_base"]
