"""Vision tool: registry wiring (keywords, args, location gate) and executor
dispatch with a stubbed provider — no real model call, no network.
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from backend.orchestrator.registry import (
    TOOL_VLM,
    location_ready_for_tool,
    match_tool_from_query,
    trusted_args_for_tool,
)
from backend.orchestrator.state import empty_state

# tests/conftest.py globally stubs backend.tools.executor.execute_tool for the
# whole suite (so graph/planner tests never hit real APIs). That stub doesn't
# know about analyze_imagery_vlm, so these tests call the real dispatch
# function directly instead of going through the stubbed execute_tool().
from backend.tools.executor import _run_vlm_analysis


def test_vlm_keyword_match():
    tool, _reason = match_tool_from_query("Describe this image for me")
    assert tool == TOOL_VLM


def test_vlm_location_ready_requires_an_image():
    state = empty_state(query="describe this image")
    assert not location_ready_for_tool(TOOL_VLM, state)

    state["input_file"] = "some/rendered.png"
    assert location_ready_for_tool(TOOL_VLM, state)


def test_vlm_trusted_args_uses_query_and_input_file():
    state = empty_state(query="describe this image", input_file="some/rendered.png")
    args = trusted_args_for_tool(TOOL_VLM, state)
    assert args["image_path"] == "some/rendered.png"
    assert args["query"] == "describe this image"


def test_vlm_disabled_returns_validation_error(monkeypatch):
    import backend.tools.executor as executor

    monkeypatch.setattr(
        executor, "settings", dataclasses.replace(executor.settings, vision_tool_enabled=False)
    )
    result = _run_vlm_analysis({"image_path": "x.png", "query": "what is this?"})
    assert result["status"] == "error"
    assert result["error"]["type"] == "validation_error"


def test_vlm_missing_image_path_returns_validation_error(monkeypatch):
    import backend.tools.executor as executor

    monkeypatch.setattr(
        executor, "settings", dataclasses.replace(executor.settings, vision_tool_enabled=True)
    )
    result = _run_vlm_analysis({"image_path": None, "query": "what is this?"})
    assert result["status"] == "error"
    assert result["error"]["type"] == "validation_error"


def test_vlm_calls_configured_provider(monkeypatch):
    import backend.tools.executor as executor
    import backend.vision.factory as vision_factory

    monkeypatch.setattr(
        executor, "settings", dataclasses.replace(executor.settings, vision_tool_enabled=True)
    )

    class _StubProvider:
        def interpret(self, image_path: str, query: str) -> dict:
            return {"text": f"stub answer for {query}", "model": "stub", "provider": "stub"}

    monkeypatch.setattr(vision_factory, "get_vision_provider", lambda: _StubProvider())

    # A .png suffix skips the GeoTIFF-render step entirely, so this never
    # touches disk or rasterio.
    result = _run_vlm_analysis({"image_path": "x.png", "query": "what is this?"})
    assert result["status"] == "success"
    assert "stub answer" in result["text"]


def test_mark_region_bbox_becomes_exact_region_bbox(monkeypatch, tmp_path):
    """mark_region_in_image's fractional bbox, once the underlying image is a
    real georeferenced GeoTIFF, is affine-converted into an exact WGS84
    region_bbox -- not left as a plain image-space rectangle."""
    import backend.tools.executor as executor
    import backend.vision.factory as vision_factory

    monkeypatch.setattr(
        executor, "settings", dataclasses.replace(executor.settings, vision_tool_enabled=True)
    )

    min_lon, min_lat, max_lon, max_lat = 77.20, 28.62, 77.28, 28.68
    geotiff_path = tmp_path / "scene.tif"
    transform = from_bounds(min_lon, min_lat, max_lon, max_lat, 512, 512)
    data = (np.random.rand(3, 512, 512) * 255).astype(np.uint8)
    with rasterio.open(
        geotiff_path, "w", driver="GTiff", height=512, width=512, count=3,
        dtype="uint8", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data)

    class _StubProvider:
        def interpret(self, image_path: str, query: str) -> dict:
            return {"text": "found it", "bbox": [0.0, 0.0, 1.0, 1.0], "model": "stub", "provider": "stub"}

    monkeypatch.setattr(vision_factory, "get_vision_provider", lambda: _StubProvider())

    result = _run_vlm_analysis({"image_path": str(geotiff_path), "query": "mark the field"})
    assert result["status"] == "success"
    assert result["region_bbox"] == pytest.approx([min_lon, min_lat, max_lon, max_lat], abs=1e-9)
    assert "top_left" in result["region_bbox_corners"]


def test_mark_region_polygon_becomes_exact_region_polygon_and_centroid(monkeypatch, tmp_path):
    """When mark_region_in_image returns a polygon (an elongated feature's
    own path, e.g. a river), the executor prefers it over the plain bbox:
    region_polygon carries the exact path, and region_centroid is the
    path's own mean -- not the (potentially far-off) bbox envelope's
    midpoint."""
    import backend.tools.executor as executor
    import backend.vision.factory as vision_factory

    monkeypatch.setattr(
        executor, "settings", dataclasses.replace(executor.settings, vision_tool_enabled=True)
    )

    min_lon, min_lat, max_lon, max_lat = 77.20, 28.62, 77.28, 28.68
    geotiff_path = tmp_path / "scene.tif"
    transform = from_bounds(min_lon, min_lat, max_lon, max_lat, 512, 512)
    data = (np.random.rand(3, 512, 512) * 255).astype(np.uint8)
    with rasterio.open(
        geotiff_path, "w", driver="GTiff", height=512, width=512, count=3,
        dtype="uint8", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data)

    # A path confined to one corner: full-image bbox, but a polygon tracing
    # only the top-left corner region.
    corner_path = [[0.0, 0.0], [0.1, 0.05], [0.2, 0.0]]

    class _StubProvider:
        def interpret(self, image_path: str, query: str) -> dict:
            return {
                "text": "the river runs through the corner",
                "bbox": [0.0, 0.0, 1.0, 1.0],
                "polygon": corner_path,
                "model": "stub", "provider": "stub",
            }

    monkeypatch.setattr(vision_factory, "get_vision_provider", lambda: _StubProvider())

    result = _run_vlm_analysis({"image_path": str(geotiff_path), "query": "mark the river"})
    assert result["status"] == "success"
    assert len(result["region_polygon"]) == 3
    envelope_mid_lat = (min_lat + max_lat) / 2.0
    centroid = result["region_centroid"]
    # Near the top-left corner (max_lat), not the full-image envelope's middle.
    assert centroid["latitude"] > envelope_mid_lat


def test_vlm_bbox_without_georeferencing_has_no_region_bbox(monkeypatch):
    """A plain rendered PNG (no CRS) can't be geocoded -- region_bbox is
    silently omitted rather than the request failing."""
    import backend.tools.executor as executor
    import backend.vision.factory as vision_factory

    monkeypatch.setattr(
        executor, "settings", dataclasses.replace(executor.settings, vision_tool_enabled=True)
    )

    class _StubProvider:
        def interpret(self, image_path: str, query: str) -> dict:
            return {"text": "found it", "bbox": [0.1, 0.1, 0.9, 0.9], "model": "stub", "provider": "stub"}

    monkeypatch.setattr(vision_factory, "get_vision_provider", lambda: _StubProvider())

    result = _run_vlm_analysis({"image_path": "x.png", "query": "mark the field"})
    assert result["status"] == "success"
    assert "region_bbox" not in result
