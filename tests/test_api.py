from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app
from backend.tools import executor as tools_executor

client = TestClient(app)


def test_health_returns_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_query_optical_fetch_succeeds():
    resp = client.post(
        "/api/v1/query",
        json={
            "query": "Fetch Sentinel-2 optical imagery for Delhi",
            "bbox": [77.1, 28.5, 77.3, 28.7],
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["plan"]["tool"] == "fetch_optical_imagery"


def test_query_sar_succeeds():
    resp = client.post(
        "/api/v1/query",
        json={
            "query": "Get SAR radar imagery for Mumbai",
            "bbox": [72.8, 18.9, 73.0, 19.1],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["plan"]["tool"] == "fetch_sar_imagery"


def test_query_weather_with_point_succeeds():
    resp = client.post(
        "/api/v1/query",
        json={
            "query": "Get weather and rainfall for this location",
            "latitude": 28.61,
            "longitude": 77.21,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["plan"]["tool"] == "fetch_weather_environment"


def test_query_chat_returns_200():
    resp = client.post(
        "/api/v1/query",
        json={"query": "What is the capital of France?"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_query_without_bbox_returns_400_clarify():
    resp = client.post(
        "/api/v1/query",
        json={"query": "Fetch Sentinel-2 optical imagery for Delhi"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["status"] == "clarify"
    assert body["tool_results"] == []


def test_query_invalid_bbox_returns_400():
    resp = client.post(
        "/api/v1/query",
        json={
            "query": "Fetch Sentinel-2 optical imagery for Delhi",
            "bbox": [200, 28.5, 77.3, 28.7],
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["status"] == "error"
    assert body["errors"]
    assert "bbox longitude" in body["final_answer"]


def test_query_empty_string_returns_400():
    resp = client.post("/api/v1/query", json={"query": ""})
    assert resp.status_code == 400
    body = resp.json()
    assert body["status"] == "error"
    assert body["errors"]


def test_query_out_of_range_latitude_returns_400():
    resp = client.post(
        "/api/v1/query",
        json={"query": "Get weather", "latitude": 200, "longitude": 77.21},
    )
    assert resp.status_code == 400
    assert resp.json()["status"] == "error"


def test_query_no_suitable_scene_returns_404(monkeypatch):
    def _empty(_name, _args):
        return {
            "status": "error",
            "error": {
                "type": "no_suitable_scene",
                "message": (
                    "No suitable Sentinel-1 GRD SAR scene was found. "
                    "3 scene(s) exist but all are DESCENDING."
                ),
            },
        }

    monkeypatch.setattr(tools_executor, "execute_tool", _empty)
    import backend.orchestrator.nodes as nodes
    import backend.orchestrator.tool_loop_graph as tool_loop_graph

    monkeypatch.setattr(nodes, "execute_tool", _empty)
    monkeypatch.setattr(tool_loop_graph, "execute_tool", _empty)

    resp = client.post(
        "/api/v1/query",
        json={
            "query": "Download Sentinel-1 SAR backscatter",
            "bbox": [72.8, 18.9, 73.0, 19.1],
            "orbit_direction": "ASCENDING",
        },
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["status"] == "error"
    assert "DESCENDING" in body["final_answer"]


def test_query_upstream_tool_failure_returns_502(monkeypatch):
    def _fail(_name, _args):
        return {
            "status": "error",
            "error": {"type": "service_error", "message": "Sentinel Hub timeout"},
        }

    monkeypatch.setattr(tools_executor, "execute_tool", _fail)
    import backend.orchestrator.nodes as nodes
    import backend.orchestrator.tool_loop_graph as tool_loop_graph

    monkeypatch.setattr(nodes, "execute_tool", _fail)
    monkeypatch.setattr(tool_loop_graph, "execute_tool", _fail)

    resp = client.post(
        "/api/v1/query",
        json={
            "query": "Fetch Sentinel-2 optical imagery for Delhi",
            "bbox": [77.1, 28.5, 77.3, 28.7],
        },
    )
    assert resp.status_code == 502
    body = resp.json()
    assert body["status"] == "error"
    assert "failed" in body["final_answer"].lower()


def test_query_ndvi_without_file_returns_400_clarify():
    resp = client.post(
        "/api/v1/query",
        json={"query": "Compute NDVI vegetation indices from this GeoTIFF"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["status"] == "clarify"
    assert body["tool_results"] == []


def test_query_tool5_indices_succeeds():
    resp = client.post(
        "/api/v1/query",
        json={
            "query": "Compute NDVI vegetation indices from this GeoTIFF",
            "input_file": "dummy_multispectral.tif",
            "indices": ["NDVI", "NBR"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["plan"]["tool"] == "compute_vegetation_indices"
    assert body["plan"]["args"]["file_path"] == "dummy_multispectral.tif"
    assert body["plan"]["args"]["indices"] == ["NDVI", "NBR"]


def test_query_tool6_inspect_succeeds():
    resp = client.post(
        "/api/v1/query",
        json={
            "query": "Inspect this GeoTIFF and run raster QA",
            "input_file": "dummy_t1.tif",
            "compare_with": "dummy_t2.tif",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["plan"]["tool"] == "inspect_geotiff_metadata"
    assert body["plan"]["args"]["file_path"] == "dummy_t1.tif"
    assert body["plan"]["args"]["compare_with"] == "dummy_t2.tif"


def test_query_tool7_temporal_change_succeeds():
    resp = client.post(
        "/api/v1/query",
        json={
            "query": "Analyze temporal change between these two rasters",
            "raster_before_path": "dummy_before.tif",
            "raster_after_path": "dummy_after.tif",
            "band_selection": "NDVI",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["plan"]["tool"] == "analyze_temporal_change"
    assert body["plan"]["args"]["raster_before_path"] == "dummy_before.tif"
    assert body["plan"]["args"]["raster_after_path"] == "dummy_after.tif"
    assert body["plan"]["args"]["band_selection"] == "NDVI"


def test_query_tool8_landcover_succeeds():
    resp = client.post(
        "/api/v1/query",
        json={
            "query": "Analyze land cover and terrain for this WorldCover raster",
            "lulc_raster_path": "dummy_lulc.tif",
            "dem_raster_path": "dummy_dem.tif",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["plan"]["tool"] == "analyze_spatial_landcover_terrain"
    assert body["plan"]["args"]["lulc_raster_path"] == "dummy_lulc.tif"
    assert body["plan"]["args"]["dem_raster_path"] == "dummy_dem.tif"


def test_query_against_uploaded_image_returns_kb_and_initial_description(tmp_path):
    import json

    input_file = tmp_path / "scene.tif"
    input_file.write_bytes(b"")
    knowledge_base = {
        "file_path": str(input_file),
        "bands": ["B02", "B03"],
        "latitude": 28.6,
        "longitude": 77.2,
        "place_name": "New Delhi, India",
    }
    (tmp_path / "scene.kb.json").write_text(json.dumps(knowledge_base))

    resp = client.post(
        "/api/v1/query",
        json={"query": "Tell me about this scene", "input_file": str(input_file)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["knowledge_base"] == knowledge_base
    assert body["initial_description"] == "A mock description of the image."


def test_query_import_error_returns_500(monkeypatch):
    def _fail(_name, _args):
        return {
            "status": "error",
            "error": {
                "type": "import_error",
                "message": "Could not import tool module",
            },
        }

    monkeypatch.setattr(tools_executor, "execute_tool", _fail)
    import backend.orchestrator.nodes as nodes
    import backend.orchestrator.tool_loop_graph as tool_loop_graph

    monkeypatch.setattr(nodes, "execute_tool", _fail)
    monkeypatch.setattr(tool_loop_graph, "execute_tool", _fail)

    resp = client.post(
        "/api/v1/query",
        json={
            "query": "Fetch Sentinel-2 optical imagery for Delhi",
            "bbox": [77.1, 28.5, 77.3, 28.7],
        },
    )
    assert resp.status_code == 500
    assert resp.json()["status"] == "error"
