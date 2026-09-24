"""A marked region's center -- the intersection of its diagonals, i.e. the
midpoint of its min/max lat and min/max lon -- takes priority over a plain
latitude/longitude (or the whole image's bbox) for any location-based tool.
"""
from __future__ import annotations

import pytest

from backend.orchestrator.registry import (
    TOOL_GEOCODE,
    TOOL_POI_DISCOVERY,
    TOOL_SCENE_IDENTITY,
    TOOL_WEATHER,
    location_ready_for_tool,
    trusted_args_for_tool,
)
from backend.orchestrator.state import empty_state

FULL_BBOX = [77.00, 28.00, 78.00, 29.00]
REGION = [77.15, 28.55, 77.20, 28.60]  # center: (28.575, 77.175)


def test_weather_uses_region_center_not_whole_bbox():
    state = empty_state(query="weather here", bbox=FULL_BBOX, region_bbox=REGION)
    args = trusted_args_for_tool(TOOL_WEATHER, state)
    assert args["latitude"] == pytest.approx(28.575)
    assert args["longitude"] == pytest.approx(77.175)
    # bbox is suppressed so Tool 4 can't silently prefer it over the point.
    assert args["bbox"] is None


def test_weather_falls_back_to_bbox_without_a_marked_region():
    state = empty_state(query="weather here", bbox=FULL_BBOX)
    args = trusted_args_for_tool(TOOL_WEATHER, state)
    assert args["bbox"] == FULL_BBOX


def test_weather_falls_back_to_plain_lat_lon_without_a_marked_region():
    state = empty_state(query="weather here", latitude=28.61, longitude=77.21)
    args = trusted_args_for_tool(TOOL_WEATHER, state)
    assert args["latitude"] == 28.61
    assert args["longitude"] == 77.21


def test_geocode_reverse_uses_region_center_over_plain_lat_lon():
    state = empty_state(
        query="what place is this?",
        latitude=28.61, longitude=77.21,  # the whole image's centroid
        region_bbox=REGION,
    )
    args = trusted_args_for_tool(TOOL_GEOCODE, state)
    assert args["latitude"] == pytest.approx(28.575)
    assert args["longitude"] == pytest.approx(77.175)


def test_geocode_location_ready_from_region_alone():
    state = empty_state(query="what place is this?", region_bbox=REGION)
    assert location_ready_for_tool(TOOL_GEOCODE, state)


def test_scene_identity_and_poi_discovery_use_region_bbox_over_whole_bbox():
    state = empty_state(query="what's here?", bbox=FULL_BBOX, region_bbox=REGION)
    assert trusted_args_for_tool(TOOL_SCENE_IDENTITY, state)["bbox"] == REGION
    assert trusted_args_for_tool(TOOL_POI_DISCOVERY, state)["bbox"] == REGION


def test_weather_prefers_region_centroid_over_bbox_midpoint():
    """A diagonal/elongated marked region (e.g. a river's path) can have a
    centroid nowhere near region_bbox's own midpoint -- region_centroid
    (from mark_region_in_image's affine-converted polygon) must win."""
    centroid = {"latitude": 28.599, "longitude": 77.151}  # near REGION's corner, not its midpoint (28.575, 77.175)
    state = empty_state(
        query="weather here", bbox=FULL_BBOX, region_bbox=REGION, region_centroid=centroid,
    )
    args = trusted_args_for_tool(TOOL_WEATHER, state)
    assert args["latitude"] == pytest.approx(28.599)
    assert args["longitude"] == pytest.approx(77.151)


def test_weather_falls_back_to_bbox_midpoint_without_a_centroid():
    state = empty_state(query="weather here", bbox=FULL_BBOX, region_bbox=REGION)
    args = trusted_args_for_tool(TOOL_WEATHER, state)
    assert args["latitude"] == pytest.approx(28.575)
    assert args["longitude"] == pytest.approx(77.175)
