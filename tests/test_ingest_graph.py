"""Upload-time ingestion: validate, extract bands/lat/long, resolve a place
name, and build the per-image knowledge base (backend/orchestrator/ingest_graph.py).
"""

from __future__ import annotations

import json

import backend.orchestrator.ingest_graph as ingest_graph
from backend.orchestrator.ingest_graph import VALIDATION_ERROR_MESSAGE, run_ingest


def _stub_valid_tiff(name, args):
    if name == "inspect_geotiff_metadata":
        return {
            "status": "success",
            "file": {"file_path": args["file_path"]},
            "spatial": {
                "crs": "EPSG:4326",
                "bounds_wgs84": {
                    "min_lon": 77.10,
                    "min_lat": 28.50,
                    "max_lon": 77.30,
                    "max_lat": 28.70,
                },
            },
            "bands": [
                {"band_index": 1, "description": "B02"},
                {"band_index": 2, "description": "B03"},
                {"band_index": 3, "description": "B04"},
            ],
        }
    if name == "get_place_name_from_coordinates":
        return {"status": "success", "place_name": "New Delhi, India"}
    raise AssertionError(f"unexpected tool call: {name}")


def _stub_invalid_file(name, args):
    if name == "inspect_geotiff_metadata":
        return {
            "status": "error",
            "error": {"type": "service_error", "message": "not a valid raster"},
        }
    raise AssertionError(f"unexpected tool call: {name}")


def _stub_geocode_unavailable(name, args):
    if name == "inspect_geotiff_metadata":
        return {
            "status": "success",
            "file": {"file_path": args["file_path"]},
            "spatial": {
                "crs": "EPSG:4326",
                "bounds_wgs84": {
                    "min_lon": 77.10,
                    "min_lat": 28.50,
                    "max_lon": 77.30,
                    "max_lat": 28.70,
                },
            },
            "bands": [{"band_index": 1, "description": "B02"}],
        }
    if name == "get_place_name_from_coordinates":
        return {
            "status": "error",
            "error": {"type": "service_error", "message": "reverse_geocode is not implemented yet."},
        }
    raise AssertionError(f"unexpected tool call: {name}")


def test_valid_geotiff_builds_full_knowledge_base(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest_graph, "execute_tool", _stub_valid_tiff)
    file_path = str(tmp_path / "scene.tif")

    outcome = run_ingest(file_path)

    assert outcome["ok"] is True
    kb = outcome["knowledge_base"]
    assert kb["bands"] == ["B02", "B03", "B04"]
    assert kb["latitude"] == 28.60
    assert round(kb["longitude"], 6) == 77.2
    assert kb["place_name"] == "New Delhi, India"

    kb_path = tmp_path / "scene.kb.json"
    assert kb_path.exists()
    assert json.loads(kb_path.read_text()) == kb


def test_invalid_file_returns_plain_text_error(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest_graph, "execute_tool", _stub_invalid_file)
    file_path = str(tmp_path / "not_a_raster.tif")

    outcome = run_ingest(file_path)

    assert outcome["ok"] is False
    assert outcome["error"] == VALIDATION_ERROR_MESSAGE
    assert not (tmp_path / "not_a_raster.kb.json").exists()


def test_geocode_failure_degrades_gracefully(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest_graph, "execute_tool", _stub_geocode_unavailable)
    file_path = str(tmp_path / "scene.tif")

    outcome = run_ingest(file_path)

    assert outcome["ok"] is True
    kb = outcome["knowledge_base"]
    assert kb["place_name"] is None
    assert kb["latitude"] == 28.60
    assert kb["bands"] == ["B02"]


def _stub_valid_tiff_with_resolution(name, args):
    if name == "inspect_geotiff_metadata":
        return {
            "status": "success",
            "file": {"file_path": args["file_path"]},
            "spatial": {
                "crs": "EPSG:4326",
                "bounds_wgs84": {
                    "min_lon": 77.10,
                    "min_lat": 28.50,
                    "max_lon": 77.30,
                    "max_lat": 28.70,
                },
                "pixel_size_wgs84_degrees": {
                    "lon_per_pixel": 0.0003906,
                    "lat_per_pixel": 0.0003906,
                },
            },
            "bands": [{"band_index": 1, "description": "B02"}],
        }
    if name == "get_place_name_from_coordinates":
        return {"status": "success", "place_name": "New Delhi, India"}
    raise AssertionError(f"unexpected tool call: {name}")


def test_knowledge_base_carries_bbox_and_pixel_resolution(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest_graph, "execute_tool", _stub_valid_tiff_with_resolution)
    file_path = str(tmp_path / "scene.tif")

    outcome = run_ingest(file_path)

    assert outcome["ok"] is True
    kb = outcome["knowledge_base"]
    assert kb["bbox"] == [77.10, 28.50, 77.30, 28.70]
    assert kb["pixel_size_wgs84_degrees"] == {
        "lon_per_pixel": 0.0003906,
        "lat_per_pixel": 0.0003906,
    }
