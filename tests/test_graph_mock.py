from backend.orchestrator.graph import build_graph
from backend.orchestrator.state import empty_state


def test_optical_query_uses_tool_and_succeeds():
    graph = build_graph()
    result = graph.invoke(
        empty_state(
            query="Fetch Sentinel-2 optical imagery for Delhi.",
            bbox=[77.10, 28.50, 77.30, 28.70],
            start_date="2025-01-01",
            end_date="2025-01-31",
        )
    )
    assert result["status"] == "success"
    assert result["plan"]["tool"] == "fetch_optical_imagery"
    assert result["tool_results"][0]["result"]["status"] == "success"
    assert isinstance(result["tool_results"][0]["duration_ms"], float)
    assert result["tool_results"][0]["duration_ms"] >= 0
    assert result["tool_results"][0]["timestamp"]
    nodes = [row["node"] for row in result["execution_trace"]]
    assert nodes == ["validate", "plan", "execute", "advance", "respond"]


def test_multispectral_query_routes_correctly():
    graph = build_graph()
    result = graph.invoke(
        empty_state(
            query="Get multispectral surface reflectance bands for Delhi.",
            bbox=[77.10, 28.50, 77.30, 28.70],
        )
    )
    assert result["plan"]["tool"] == "fetch_multispectral_imagery"
    assert result["status"] == "success"


def test_sar_query_routes_and_succeeds():
    graph = build_graph()
    result = graph.invoke(
        empty_state(
            query="Download SAR radar imagery for Mumbai.",
            bbox=[72.8, 18.9, 73.0, 19.1],
        )
    )
    assert result["plan"]["tool"] == "fetch_sar_imagery"
    assert result["status"] == "success"


def test_weather_query_with_bbox_succeeds():
    graph = build_graph()
    result = graph.invoke(
        empty_state(
            query="Get weather and precipitation for this AOI.",
            bbox=[77.10, 28.50, 77.30, 28.70],
        )
    )
    assert result["plan"]["tool"] == "fetch_weather_environment"
    assert result["status"] == "success"


def test_weather_query_with_lat_lon_succeeds():
    graph = build_graph()
    result = graph.invoke(
        empty_state(
            query="What is the temperature and rainfall near this point?",
            latitude=28.61,
            longitude=77.21,
        )
    )
    assert result["plan"]["tool"] == "fetch_weather_environment"
    assert result["status"] == "success"


def test_fetch_without_bbox_asks_for_clarification():
    graph = build_graph()
    result = graph.invoke(empty_state(query="Fetch Sentinel-2 optical imagery for Delhi."))
    assert result["status"] == "clarify"
    assert result["tool_results"] == []
    nodes = [row["node"] for row in result["execution_trace"]]
    assert nodes == ["validate", "plan", "respond"]


def test_invalid_bbox_does_not_call_a_tool():
    graph = build_graph()
    result = graph.invoke(
        empty_state(
            query="Fetch Sentinel-2 optical imagery for Delhi.",
            bbox=[200, 28.5, 77.3, 28.7],
        )
    )
    assert result["status"] == "error"
    assert result["tool_results"] == []
    assert result["errors"]


def test_unrelated_query_is_chat():
    graph = build_graph()
    result = graph.invoke(empty_state(query="What is the capital of France?"))
    assert result["plan"]["action"] == "chat"
    assert result["status"] == "ok"


def test_flood_query_does_not_stop_at_sar_only():
    graph = build_graph()
    result = graph.invoke(
        empty_state(
            query="detect flood area",
            bbox=[77.10, 28.50, 77.30, 28.70],
        )
    )
    assert result["status"] == "clarify"
    assert result["intent"] == "mission_flood"
    assert result["tool_results"] == []
    assert result["plan"]["action"] == "clarify"


def test_crop_health_uses_multispectral():
    graph = build_graph()
    result = graph.invoke(
        empty_state(
            query="analyze crop health",
            bbox=[77.10, 28.50, 77.30, 28.70],
        )
    )
    assert result["plan"]["tool"] == "fetch_multispectral_imagery"
    assert result["status"] == "success"
