"""describe_marked_region: registry wiring (keywords, trusted args, location
gate) and executor dispatch with the cropper/vision provider stubbed out --
no real rasterio window read, no real model call.
"""
from __future__ import annotations

import dataclasses

import pytest

from backend.orchestrator.registry import (
    TOOL_DESCRIBE_REGION,
    location_ready_for_tool,
    match_tool_from_query,
    trusted_args_for_tool,
)
from backend.orchestrator.state import empty_state
from backend.tools.executor import _run_describe_region

REGION = [77.15, 28.55, 77.20, 28.60]


def test_describe_region_keyword_match():
    tool, _reason = match_tool_from_query("what's in the region I marked?")
    assert tool == TOOL_DESCRIBE_REGION


def test_describe_region_location_requires_file_and_region_bbox():
    state = empty_state(query="what's in the marked region?")
    assert not location_ready_for_tool(TOOL_DESCRIBE_REGION, state)

    state["input_file"] = "scene.tif"
    assert not location_ready_for_tool(TOOL_DESCRIBE_REGION, state)

    state["region_bbox"] = REGION
    assert location_ready_for_tool(TOOL_DESCRIBE_REGION, state)


def test_describe_region_trusted_args():
    state = empty_state(
        query="what's in the marked region?",
        input_file="scene.tif",
        region_bbox=REGION,
    )
    args = trusted_args_for_tool(TOOL_DESCRIBE_REGION, state)
    assert args["image_path"] == "scene.tif"
    assert args["region_bbox"] == REGION
    assert args["query"] == state["query"]


def test_describe_region_disabled_returns_validation_error(monkeypatch):
    import backend.tools.executor as executor

    monkeypatch.setattr(
        executor, "settings", dataclasses.replace(executor.settings, vision_tool_enabled=False)
    )
    result = _run_describe_region({"image_path": "scene.tif", "region_bbox": REGION})
    assert result["status"] == "error"
    assert result["error"]["type"] == "validation_error"


def test_describe_region_missing_region_bbox_returns_validation_error(monkeypatch):
    import backend.tools.executor as executor

    monkeypatch.setattr(
        executor, "settings", dataclasses.replace(executor.settings, vision_tool_enabled=True)
    )
    result = _run_describe_region({"image_path": "scene.tif"})
    assert result["status"] == "error"
    assert result["error"]["type"] == "validation_error"


def test_describe_region_success(monkeypatch):
    import backend.rendering.raster_preview as raster_preview
    import backend.tools.executor as executor
    import backend.vision.factory as vision_factory

    monkeypatch.setattr(
        executor, "settings", dataclasses.replace(executor.settings, vision_tool_enabled=True)
    )
    monkeypatch.setattr(
        raster_preview,
        "render_geotiff_region_preview",
        lambda path, bbox, **kw: (
            b"\x89PNG\r\n\x1a\nstub",
            {"pixel_window": {"col_off": 0, "row_off": 0, "width": 10, "height": 10}},
        ),
    )

    class _StubProvider:
        def interpret(self, image_path: str, query: str) -> dict:
            return {"text": f"stub description for {query}", "model": "stub", "provider": "stub"}

    monkeypatch.setattr(vision_factory, "get_vision_provider", lambda: _StubProvider())

    import backend.tools.geocode as geocode_module

    monkeypatch.setattr(
        geocode_module,
        "reverse_geocode",
        lambda lat, lon: {"place_name": "Stub Place, Netherlands", "raw": {}},
    )

    result = _run_describe_region({
        "image_path": "scene.tif",
        "region_bbox": REGION,
        "query": "what's here?",
    })
    assert result["status"] == "success"
    assert "stub description" in result["text"]
    assert result["region"]["pixel_window"]["width"] == 10
    assert result["place_name"] == "Stub Place, Netherlands"
    assert result["region_center"]["latitude"] == pytest.approx((REGION[1] + REGION[3]) / 2.0)
    assert result["region_center"]["longitude"] == pytest.approx((REGION[0] + REGION[2]) / 2.0)


def test_describe_region_geocode_failure_is_non_fatal(monkeypatch):
    import backend.rendering.raster_preview as raster_preview
    import backend.tools.executor as executor
    import backend.tools.geocode as geocode_module
    import backend.vision.factory as vision_factory

    monkeypatch.setattr(
        executor, "settings", dataclasses.replace(executor.settings, vision_tool_enabled=True)
    )
    monkeypatch.setattr(
        raster_preview,
        "render_geotiff_region_preview",
        lambda path, bbox, **kw: (b"\x89PNG\r\n\x1a\nstub", {"pixel_window": {}}),
    )

    class _StubProvider:
        def interpret(self, image_path: str, query: str) -> dict:
            return {"text": "stub", "model": "stub", "provider": "stub"}

    monkeypatch.setattr(vision_factory, "get_vision_provider", lambda: _StubProvider())

    def _boom(lat, lon):
        raise RuntimeError("reverse geocode is down")

    monkeypatch.setattr(geocode_module, "reverse_geocode", _boom)

    result = _run_describe_region({
        "image_path": "scene.tif",
        "region_bbox": REGION,
        "query": "what's here?",
    })
    assert result["status"] == "success"
    assert result["place_name"] is None


def test_describe_region_logs_geocode_outcome_to_console(monkeypatch, caplog):
    """Console visibility for the geocode sub-step -- previously silent on
    success, which made a wrong final answer (vision guess overriding a
    correctly-resolved place_name) undiagnosable from the logs alone."""
    import logging

    import backend.rendering.raster_preview as raster_preview
    import backend.tools.executor as executor
    import backend.tools.geocode as geocode_module
    import backend.vision.factory as vision_factory

    monkeypatch.setattr(
        executor, "settings", dataclasses.replace(executor.settings, vision_tool_enabled=True)
    )
    monkeypatch.setattr(
        raster_preview,
        "render_geotiff_region_preview",
        lambda path, bbox, **kw: (b"\x89PNG\r\n\x1a\nstub", {"pixel_window": {}}),
    )

    class _StubProvider:
        def interpret(self, image_path: str, query: str) -> dict:
            return {"text": "stub", "model": "stub", "provider": "stub"}

    monkeypatch.setattr(vision_factory, "get_vision_provider", lambda: _StubProvider())
    monkeypatch.setattr(
        geocode_module,
        "reverse_geocode",
        lambda lat, lon: {"place_name": "Vasant Vihar Tehsil, New Delhi", "raw": {}},
    )

    with caplog.at_level(logging.INFO, logger="backend.tools.executor"):
        _run_describe_region({"image_path": "scene.tif", "region_bbox": REGION, "query": "x"})

    assert any(
        "Vasant Vihar Tehsil" in record.message and "reverse geocode" in record.message
        for record in caplog.records
    )
