"""Executor-level dispatch tests for Tools 9-11 and the reverse-geocode
adapter -- the underlying tool functions are monkeypatched so these never
hit a real network call (Tavily/DuckDuckGo/LocationIQ/Nominatim/Overpass).
"""
from __future__ import annotations

from backend.tools.executor import (
    _run_affine_markup,
    _run_geocode,
    _run_geocode_forward,
    _run_poi_discovery,
    _run_scene_identity,
    _run_web_intelligence,
)


def test_web_intelligence_requires_query():
    result = _run_web_intelligence({})
    assert result["status"] == "error"
    assert result["error"]["type"] == "validation_error"


def test_web_intelligence_success(monkeypatch):
    import Tool_9_fetch_web_intelligence.fetch_web_intelligence as tool9

    monkeypatch.setattr(
        tool9,
        "fetch_web_intelligence",
        lambda req: {"status": "success", "summary": f"stub for {req.query}", "results": []},
    )
    result = _run_web_intelligence({"query": "Why did the Yamuna flood?"})
    assert result["status"] == "success"
    assert "stub for" in result["summary"]


def test_geocode_forward_requires_query():
    result = _run_geocode_forward({})
    assert result["status"] == "error"
    assert result["error"]["type"] == "validation_error"


def test_geocode_forward_success(monkeypatch):
    import Tool_10_spatial_geocoding_poi.spatial_geocoding_poi as tool10

    monkeypatch.setattr(
        tool10,
        "forward_geocode",
        lambda query, **kwargs: {
            "status": "success",
            "query": query,
            "best_match": {"name": "Red Fort", "latitude": 28.6562, "longitude": 77.2410},
        },
    )
    result = _run_geocode_forward({"query": "Red Fort"})
    assert result["status"] == "success"
    assert result["best_match"]["latitude"] == 28.6562


def test_scene_identity_requires_bbox():
    result = _run_scene_identity({})
    assert result["status"] == "error"
    assert result["error"]["type"] == "validation_error"


def test_scene_identity_success(monkeypatch):
    import Tool_10_spatial_geocoding_poi.spatial_geocoding_poi as tool10

    monkeypatch.setattr(
        tool10,
        "resolve_scene_identity",
        lambda bbox, query=None: {"status": "success", "bbox": bbox, "narrative_summary": "stub"},
    )
    result = _run_scene_identity({"bbox": [77.1, 28.5, 77.3, 28.7]})
    assert result["status"] == "success"
    assert result["narrative_summary"] == "stub"


def test_poi_discovery_requires_bbox():
    result = _run_poi_discovery({})
    assert result["status"] == "error"
    assert result["error"]["type"] == "validation_error"


def test_poi_discovery_success(monkeypatch):
    import Tool_10_spatial_geocoding_poi.spatial_geocoding_poi as tool10

    monkeypatch.setattr(
        tool10,
        "discover_in_aoi_pois",
        lambda bbox, categories=None, max_results=15: {"status": "success", "poi_count": 0, "pois": []},
    )
    result = _run_poi_discovery({"bbox": [77.1, 28.5, 77.3, 28.7]})
    assert result["status"] == "success"


def test_affine_markup_requires_geotiff_path():
    result = _run_affine_markup({"features": []})
    assert result["status"] == "error"
    assert result["error"]["type"] == "validation_error"


def test_affine_markup_success(monkeypatch):
    import Tool_11_deterministic_affine_markup.deterministic_affine_markup as tool11

    monkeypatch.setattr(
        tool11,
        "project_and_markup_raster",
        lambda req: {"status": "success", "marked_image_path": "stub_marked.png", "features_inside_aoi": 1},
    )
    result = _run_affine_markup({
        "geotiff_path": "scene.tif",
        "features": [{"name": "Red Fort", "latitude": 28.6562, "longitude": 77.2410}],
    })
    assert result["status"] == "success"
    assert result["marked_image_path"] == "stub_marked.png"


def test_reverse_geocode_adapter_maps_display_name_to_place_name(monkeypatch):
    import Tool_10_spatial_geocoding_poi.spatial_geocoding_poi as tool10

    monkeypatch.setattr(
        tool10,
        "reverse_geocode",
        lambda latitude, longitude, zoom=None: {
            "status": "success",
            "display_name": "Red Fort, Old Delhi, Delhi, India",
        },
    )
    result = _run_geocode({"latitude": 28.6562, "longitude": 77.2410})
    assert result["status"] == "success"
    assert result["place_name"] == "Red Fort, Old Delhi, Delhi, India"


def test_reverse_geocode_adapter_wraps_failure_as_service_error(monkeypatch):
    import Tool_10_spatial_geocoding_poi.spatial_geocoding_poi as tool10

    monkeypatch.setattr(
        tool10,
        "reverse_geocode",
        lambda latitude, longitude, zoom=None: {
            "status": "error",
            "message": "Could not reverse geocode coordinates.",
        },
    )
    result = _run_geocode({"latitude": 0.0, "longitude": 0.0})
    assert result["status"] == "error"
    assert result["error"]["type"] == "service_error"
