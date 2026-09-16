"""Tools 9-11: fetch_web_intelligence, spatial_geocoding_poi (forward geocode,
scene identity, POI discovery), and deterministic_affine_markup."""

from backend.orchestrator.graph import build_graph
from backend.orchestrator.registry import (
    TOOL_AFFINE_MARKUP,
    TOOL_GEOCODE_FORWARD,
    TOOL_POI_DISCOVERY,
    TOOL_SCENE_IDENTITY,
    TOOL_WEB_INTEL,
    location_ready_for_tool,
    match_tool_from_query,
    trusted_args_for_tool,
)
from backend.orchestrator.state import empty_state
from backend.orchestrator.tool_loop_graph import tool_node

DELHI = [77.10, 28.50, 77.30, 28.70]


def test_keyword_routing_matches_each_new_tool():
    assert match_tool_from_query("search the web for news about this flood")[0] == TOOL_WEB_INTEL
    assert match_tool_from_query("find the coordinates of Red Fort")[0] == TOOL_GEOCODE_FORWARD
    assert match_tool_from_query("what region is this scene")[0] == TOOL_SCENE_IDENTITY
    assert match_tool_from_query("show me points of interest in this area")[0] == TOOL_POI_DISCOVERY
    assert match_tool_from_query("precisely mark Red Fort on this image")[0] == TOOL_AFFINE_MARKUP


def test_weather_query_does_not_collide_with_poi_keyword():
    # "point" must not substring-match a bare "poi" keyword.
    tool, _ = match_tool_from_query("what is the temperature near this point?")
    assert tool != TOOL_POI_DISCOVERY


def test_web_intel_trusted_args_use_full_query_and_are_always_location_ready():
    state = empty_state("Why did the Yamuna flood in July 2023?")
    args = trusted_args_for_tool(TOOL_WEB_INTEL, state)
    assert args["query"] == state["query"]
    assert location_ready_for_tool(TOOL_WEB_INTEL, state)


def test_geocode_forward_trusted_args_use_query_as_place_name():
    state = empty_state("Where is the Red Fort?", bbox=DELHI)
    args = trusted_args_for_tool(TOOL_GEOCODE_FORWARD, state)
    assert args["query"] == state["query"]
    assert args["bbox"] == DELHI


def test_scene_identity_and_poi_discovery_require_bbox():
    state = empty_state("What region does this scene cover?")
    assert not location_ready_for_tool(TOOL_SCENE_IDENTITY, state)
    assert not location_ready_for_tool(TOOL_POI_DISCOVERY, state)

    state_with_bbox = empty_state("What region does this scene cover?", bbox=DELHI)
    assert location_ready_for_tool(TOOL_SCENE_IDENTITY, state_with_bbox)
    assert location_ready_for_tool(TOOL_POI_DISCOVERY, state_with_bbox)


def test_affine_markup_not_ready_without_resolved_coordinates():
    state = empty_state("Mark the Red Fort precisely.", input_file="scene.tif")
    assert not location_ready_for_tool(TOOL_AFFINE_MARKUP, state)


def test_affine_markup_ready_with_geocoded_landmark_and_file():
    state = empty_state(
        "Mark the Red Fort precisely.",
        input_file="scene.tif",
        geocoded_landmarks=[{"name": "Red Fort", "latitude": 28.6562, "longitude": 77.2410}],
    )
    assert location_ready_for_tool(TOOL_AFFINE_MARKUP, state)
    args = trusted_args_for_tool(TOOL_AFFINE_MARKUP, state)
    assert args["geotiff_path"] == "scene.tif"
    assert args["features"] == [{"name": "Red Fort", "latitude": 28.6562, "longitude": 77.2410}]


def test_affine_markup_falls_back_to_bare_lat_lon_using_query_as_name():
    state = empty_state(
        "Mark this location.",
        input_file="scene.tif",
        latitude=28.6562,
        longitude=77.2410,
    )
    args = trusted_args_for_tool(TOOL_AFFINE_MARKUP, state)
    assert args["features"] == [{
        "name": "Mark this location.",
        "latitude": 28.6562,
        "longitude": 77.2410,
    }]


def test_tool_node_forward_geocode_populates_landmarks_and_lat_lon():
    state = empty_state("Where is the Red Fort?")
    state["plan"] = {
        "action": "call_tool",
        "tool": TOOL_GEOCODE_FORWARD,
        "args": {"query": "Red Fort"},
        "reason": "test",
    }
    update = tool_node(state)
    assert update["geocoded_landmarks"][0]["name"] == "Mock Landmark"
    assert update["latitude"] == 28.6562
    assert update["longitude"] == 77.2410


def test_tool_node_scene_identity_populates_centroid_when_no_lat_lon_yet():
    state = empty_state("What region is this?", bbox=DELHI)
    state["plan"] = {
        "action": "call_tool",
        "tool": TOOL_SCENE_IDENTITY,
        "args": {"bbox": DELHI},
        "reason": "test",
    }
    update = tool_node(state)
    assert update["latitude"] == 28.6
    assert update["longitude"] == 77.2


def test_tool_node_affine_markup_updates_input_file_to_marked_image():
    state = empty_state(
        "Mark Red Fort.",
        input_file="scene.tif",
        geocoded_landmarks=[{"name": "Red Fort", "latitude": 28.6562, "longitude": 77.2410}],
    )
    state["plan"] = {
        "action": "call_tool",
        "tool": TOOL_AFFINE_MARKUP,
        "args": trusted_args_for_tool(TOOL_AFFINE_MARKUP, state),
        "reason": "test",
    }
    update = tool_node(state)
    assert update["input_file"] == "mock_marked.png"


def test_graph_routes_geocode_forward_query():
    graph = build_graph()
    result = graph.invoke(empty_state(query="find the coordinates of Red Fort"))
    assert result["plan"]["tool"] == TOOL_GEOCODE_FORWARD
    assert result["status"] == "success"


def test_graph_routes_poi_discovery_query():
    graph = build_graph()
    result = graph.invoke(
        empty_state(query="show me points of interest in this area", bbox=DELHI)
    )
    assert result["plan"]["tool"] == TOOL_POI_DISCOVERY
    assert result["status"] == "success"


def test_graph_routes_web_intel_query():
    graph = build_graph()
    result = graph.invoke(empty_state(query="search the web for news about this flood"))
    assert result["plan"]["tool"] == TOOL_WEB_INTEL
    assert result["status"] == "success"
