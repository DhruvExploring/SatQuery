from backend.orchestrator.graph import build_graph
from backend.orchestrator.state import empty_state


def test_fetch_delhi_uses_tool_and_succeeds():
    graph = build_graph()
    result = graph.invoke(
        empty_state(
            query="Fetch Sentinel-2 imagery for Delhi.",
            bbox=[77.10, 28.50, 77.30, 28.70],
            start_date="2025-01-01",
            end_date="2025-01-31",
        )
    )

    assert result["status"] == "success"
    assert result["plan"]["tool"] == "fetch_satellite_imagery"
    assert len(result["tool_results"]) == 1
    tool_json = result["tool_results"][0]["result"]
    assert tool_json["status"] == "success"
    assert "GeoTIFF" in result["final_answer"] or "tif" in result["final_answer"]
    assert tool_json["data"]["file_path"] in result["final_answer"]


def test_fetch_without_bbox_asks_for_clarification():
    graph = build_graph()
    result = graph.invoke(empty_state(query="Fetch Sentinel-2 imagery for Delhi."))

    assert result["status"] == "clarify"
    assert result["plan"]["action"] == "clarify"
    assert result["tool_results"] == []
    assert "bounding box" in result["final_answer"].lower()


def test_invalid_bbox_does_not_call_a_tool():
    graph = build_graph()
    result = graph.invoke(
        empty_state(
            query="Fetch Sentinel-2 imagery for Delhi.",
            bbox=[200, 28.5, 77.3, 28.7],
        )
    )

    assert result["status"] == "error"
    assert result["tool_results"] == []
    assert result["errors"]


# ---------------------------------------------------------------------------
# SAR routing tests (Milestone 5)
# ---------------------------------------------------------------------------
def test_sar_query_routes_to_fetch_sar():
    """A SAR query should be planned as fetch_sar, not fetch_satellite_imagery."""
    graph = build_graph()
    result = graph.invoke(
        empty_state(
            query="Download SAR radar imagery for Mumbai.",
            bbox=[72.8, 18.9, 73.0, 19.1],
            start_date="2025-01-01",
            end_date="2025-01-31",
        )
    )

    assert result["plan"]["tool"] == "fetch_sar"
    assert result["plan"]["action"] == "call_tool"
    # Tool is not implemented yet — should get a clean error, not a crash
    assert result["status"] == "error"
    assert "not implemented" in result["final_answer"].lower()


def test_sar_without_bbox_asks_for_clarification():
    graph = build_graph()
    result = graph.invoke(
        empty_state(query="Get Sentinel-1 SAR data for Delhi.")
    )

    assert result["status"] == "clarify"
    assert result["plan"]["action"] == "clarify"
    assert result["tool_results"] == []


def test_optical_query_still_routes_to_fetch_satellite_imagery():
    """Ensure adding SAR did not break optical routing."""
    graph = build_graph()
    result = graph.invoke(
        empty_state(
            query="Download satellite imagery of Delhi.",
            bbox=[77.10, 28.50, 77.30, 28.70],
        )
    )

    assert result["plan"]["tool"] == "fetch_satellite_imagery"
    assert result["status"] == "success"
