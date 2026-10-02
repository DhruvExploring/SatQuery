"""Keyword planner routing: flood/wildfire/drought missions > weather > vegetation > optical."""

from backend.orchestrator.llm import make_plan
from backend.orchestrator.registry import (
    ANALYTICAL_S2_BANDS,
    TOOL_FLOOD,
    TOOL_MULTI,
    TOOL_OPTICAL,
    TOOL_SAR,
    TOOL_SPATIAL,
    TOOL_WEATHER,
    location_ready_for_tool,
    match_tool_from_query,
    trusted_args_for_tool,
)
from backend.orchestrator.state import empty_state

DELHI = [77.10, 28.50, 77.30, 28.70]


def test_detect_flood_area_matches_flood_mission_not_bare_sar():
    # With the deterministic mission agenda removed, the flood workflow tool
    # is only reachable through this same keyword/LLM routing -- "flood"
    # must resolve to the mission tool, not the lower-level SAR fetch, so it
    # stays reachable at all.
    tool, _reason = match_tool_from_query("detect flood area")
    assert tool == TOOL_FLOOD


def test_sar_keywords_without_flood_still_match_bare_sar():
    tool, _reason = match_tool_from_query("get radar backscatter imagery")
    assert tool == TOOL_SAR


def test_detect_flood_area_clarifies_missing_mission_inputs():
    plan = make_plan(empty_state("detect flood area", bbox=DELHI))
    assert plan["action"] == "clarify"
    assert plan["tool"] == TOOL_FLOOD
    assert "lulc" in plan["reason"].lower()


def test_analyze_crop_health_selects_multispectral_not_optical():
    tool, _reason = match_tool_from_query("analyze crop health")
    assert tool == TOOL_MULTI
    plan = make_plan(empty_state("analyze crop health", bbox=DELHI))
    assert plan["tool"] == "fetch_multispectral_imagery"


def test_show_satellite_image_selects_optical():
    tool, _reason = match_tool_from_query("show satellite image")
    assert tool == TOOL_OPTICAL
    plan = make_plan(empty_state("show satellite image", bbox=DELHI))
    assert plan["tool"] == "fetch_optical_imagery"


def test_weather_conditions_selects_weather():
    tool, _reason = match_tool_from_query("weather conditions")
    assert tool == TOOL_WEATHER
    plan = make_plan(empty_state("weather conditions", latitude=28.61, longitude=77.21))
    assert plan["tool"] == "fetch_weather_environment"


def test_crop_health_does_not_select_rgb_optical():
    plan = make_plan(empty_state("analyze crop health", bbox=DELHI))
    assert plan["tool"] != TOOL_OPTICAL


def test_trusted_args_use_http_bbox_not_invented_coords():
    state = empty_state("detect flood area", bbox=DELHI, start_date="2024-06-01")
    args = trusted_args_for_tool(TOOL_SAR, state)
    assert args["bbox"] == DELHI
    assert args["start_date"] == "2024-06-01"


def test_multispectral_trusted_args_default_to_analytical_8_bands():
    state = empty_state("Calculate NDVI for Delhi", bbox=DELHI)
    args = trusted_args_for_tool(TOOL_MULTI, state)
    assert args["bands"] == ANALYTICAL_S2_BANDS


def test_multispectral_trusted_args_keep_explicit_bands():
    state = empty_state(
        "Get Sentinel-2 multispectral imagery",
        bbox=DELHI,
        bands=["B04", "B08"],
    )
    args = trusted_args_for_tool(TOOL_MULTI, state)
    assert args["bands"] == ["B04", "B08"]


def test_spatial_landcover_resolves_path_from_input_file():
    state = empty_state(
        "Analyze land cover and terrain",
        input_file="49_optical.tif",
    )
    args = trusted_args_for_tool(TOOL_SPATIAL, state)
    assert args["lulc_raster_path"] == "49_optical.tif"
    assert location_ready_for_tool(TOOL_SPATIAL, state)
    plan = make_plan(state)
    assert plan["action"] == "call_tool"
    assert plan["tool"] == "analyze_spatial_landcover_terrain"
    assert plan["args"]["lulc_raster_path"] == "49_optical.tif"


def test_spatial_landcover_resolves_path_from_knowledge_base():
    state = empty_state(
        "Analyze land cover and terrain",
        knowledge_base={"file_path": "uploads/some_scene.tif", "place_name": "Delhi"},
    )
    args = trusted_args_for_tool(TOOL_SPATIAL, state)
    assert args["lulc_raster_path"] == "uploads/some_scene.tif"
    assert location_ready_for_tool(TOOL_SPATIAL, state)


def test_spatial_landcover_resolves_dem_and_lulc_from_pair():
    state = empty_state(
        "tell me the land topography and elevation in this area",
        raster_before_path="sample_worldcover_10m.tif",
        raster_after_path="sample_copernicus_dem_30m.tif",
    )
    args = trusted_args_for_tool(TOOL_SPATIAL, state)
    assert args["lulc_raster_path"] == "sample_worldcover_10m.tif"
    assert args["dem_raster_path"] == "sample_copernicus_dem_30m.tif"
    assert location_ready_for_tool(TOOL_SPATIAL, state)
