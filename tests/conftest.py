"""Test helpers.

Production always calls real tools — there is no product-level "mock tools"
flag. Offline unit tests stub execute_tool here only.
"""

from __future__ import annotations

import os
from typing import Any

# Prefer keyword planner in unit tests (deterministic).
os.environ["SATQUERY_ORCHESTRATOR_PROVIDER"] = "mock"


def _stub_execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "fetch_weather_environment":
        return {
            "status": "success",
            "source": {"provider": "Open-Meteo", "dataset": "ERA5"},
            "observed_metrics": {
                "precipitation_sum_mm": 12.4,
                "temperature_2m_mean_c": 18.2,
            },
            "request": args,
            "warnings": [],
        }

    if name == "compute_vegetation_indices":
        return {
            "status": "success",
            "data": {
                "file_path": args.get("file_path") or args.get("input_file") or "mock_indices.tif",
                "file_name": "mock_indices.tif",
                "format": "GeoTIFF",
            },
            "statistics": {"NDVI": {"mean": 0.42}},
            "request": args,
        }
    if name == "inspect_geotiff_metadata":
        return {
            "status": "success",
            "file": {"file_path": args.get("file_path") or "mock.tif"},
            "spatial": {"crs": "EPSG:4326"},
            "raster": {"width": 64, "height": 64, "band_count": 1},
            "quality": {"is_valid_for_ml": True},
            "compatibility": {"pixelwise_operation_ready": True},
            "request": args,
        }
    if name == "analyze_temporal_change":
        return {
            "status": "success",
            "change_summary": {
                "significant_decrease": {"area_km2": 1.2},
                "significant_increase": {"area_km2": 0.4},
            },
            "generated_products": {
                "change_mask_path": "mock_change_mask.tif",
                "difference_raster_path": "mock_difference.tif",
            },
            "request": args,
        }
    if name == "analyze_spatial_landcover_terrain":
        return {
            "status": "success",
            "dominant_landcover": {"name": "Cropland", "percentage": 61.5},
            "request": args,
        }
    if name.startswith("workflow_"):
        return {
            "status": "success",
            "pipeline": name,
            "executive_summary": {"stub": True},
            "request": args,
        }
    if name == "get_place_name_from_coordinates":
        return {
            "status": "success",
            "place_name": "Test Location",
            "raw": {},
            "request": args,
        }
    if name == "fetch_web_intelligence":
        return {
            "status": "success",
            "provider": "mock",
            "fallback_triggered": False,
            "fallback_reason": None,
            "query": args.get("query"),
            "results_count": 1,
            "summary": "A mock web intelligence summary.",
            "results": [],
            "request": args,
        }
    if name == "geocode_place_to_coordinates":
        return {
            "status": "success",
            "provider": "mock",
            "query": args.get("query"),
            "candidates_count": 1,
            "candidates": [{"name": "Mock Landmark", "latitude": 28.6562, "longitude": 77.2410}],
            "best_match": {"name": "Mock Landmark", "latitude": 28.6562, "longitude": 77.2410},
            "request": args,
        }
    if name == "resolve_scene_identity":
        return {
            "status": "success",
            "bbox": args.get("bbox"),
            "centroid": {"latitude": 28.6, "longitude": 77.2},
            "geographic_identity": "Mock Region, Mock State, Mock Country",
            "narrative_summary": "This satellite raster covers Mock Region.",
            "hierarchy": {"locality": "Mock Region", "city": "Mock City", "state": "Mock State", "country": "Mock Country"},
            "landmarks": [],
            "boundary_audits": [],
            "request": args,
        }
    if name == "discover_points_of_interest":
        return {
            "status": "success",
            "bbox": args.get("bbox"),
            "categories_requested": args.get("poi_categories") or ["tourism", "historic"],
            "poi_count": 1,
            "pois": [{"name": "Mock POI", "category": "historic", "latitude": 28.6, "longitude": 77.2, "inside_aoi": True}],
            "request": args,
        }
    if name == "deterministic_affine_markup":
        return {
            "status": "success",
            "geotiff_path": args.get("geotiff_path"),
            "marked_image_path": "mock_marked.png",
            "features_total": len(args.get("features") or []),
            "features_inside_aoi": len(args.get("features") or []),
            "features_outside_aoi": 0,
            "features": [],
            "warnings": [],
            "request": args,
        }
    if name == "describe_marked_region":
        return {
            "status": "success",
            "region": {
                "pixel_window": {"col_off": 10.0, "row_off": 10.0, "width": 50.0, "height": 50.0},
                "bounds_wgs84_requested": {
                    "min_lon": (args.get("region_bbox") or [0, 0, 0, 0])[0],
                    "min_lat": (args.get("region_bbox") or [0, 0, 0, 0])[1],
                    "max_lon": (args.get("region_bbox") or [0, 0, 0, 0])[2],
                    "max_lat": (args.get("region_bbox") or [0, 0, 0, 0])[3],
                },
                "bounds_wgs84_achieved": {
                    "min_lon": (args.get("region_bbox") or [0, 0, 0, 0])[0],
                    "min_lat": (args.get("region_bbox") or [0, 0, 0, 0])[1],
                    "max_lon": (args.get("region_bbox") or [0, 0, 0, 0])[2],
                    "max_lat": (args.get("region_bbox") or [0, 0, 0, 0])[3],
                },
            },
            "text": "A mock description of the marked region.",
            "model": "mock",
            "provider": "mock",
            "request": args,
        }
    if name in ("analyze_imagery_vlm", "mark_region_in_image"):
        return {
            "status": "success",
            "text": "A mock description of the image.",
            "model": "mock",
            "provider": "mock",
            "request": args,
        }
    if name == "compare_images_visually":
        return {
            "status": "success",
            "text": "A mock comparison of the two images.",
            "model": "mock",
            "provider": "mock",
            "request": args,
        }

    scene = {
        "fetch_optical_imagery": "S2_OPTICAL_MOCK",
        "fetch_multispectral_imagery": "S2_MULTI_MOCK",
        "fetch_sar_imagery": "S1_SAR_MOCK",
    }.get(name, "UNKNOWN")
    collection = {
        "fetch_optical_imagery": "sentinel-2-l2a",
        "fetch_multispectral_imagery": "sentinel-2-l2a",
        "fetch_sar_imagery": "sentinel-1-grd",
    }.get(name, name)
    date_tag = args.get("start_date") or "t"
    path = f"sih_satellite_data/{name}_{scene}_{date_tag}_test.tif"
    payload = {
        "status": "success",
        "data": {"file_path": path, "file_name": path.split("/")[-1], "format": "GeoTIFF"},
        "source": {"provider": "test", "collection": collection, "scene_id": scene},
        "quality": {"cloud_cover": 0.0, "valid": True},
        "request": args,
    }
    if name in {"fetch_optical_imagery", "fetch_satellite_imagery"}:
        payload["flags"] = {
            "sar_recommended": False,
            "optical_quality_poor": False,
        }
    return payload


def pytest_configure() -> None:
    import backend.orchestrator.ingest_graph as ingest_graph
    import backend.orchestrator.llm as llm
    import backend.orchestrator.nodes as nodes
    import backend.orchestrator.tool_loop_graph as tool_loop_graph
    import backend.tools.executor as executor

    # Deterministic single-tool planner for tests regardless of .env
    llm.plan_single_tool = llm._keyword_plan  # type: ignore[assignment]

    # Stub tool execution so pytest never hits live APIs. Each module that
    # did `from backend.tools.executor import execute_tool` holds its own
    # name binding, so the module-level attribute must be patched too.
    executor.execute_tool = _stub_execute_tool  # type: ignore[assignment]
    nodes.execute_tool = _stub_execute_tool  # type: ignore[assignment]
    tool_loop_graph.execute_tool = _stub_execute_tool  # type: ignore[assignment]
    ingest_graph.execute_tool = _stub_execute_tool  # type: ignore[assignment]
