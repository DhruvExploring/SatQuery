"""Test helpers.

Production always calls real tools. Offline unit tests stub execute_tool
here only — there is no SATQUERY_MOCK_TOOLS product flag.
"""

from __future__ import annotations

import os
from typing import Any

# Prefer keyword planner in unit tests (deterministic).
os.environ["SATQUERY_MOCK_PLANNER"] = "true"


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
    import backend.orchestrator.llm as llm
    import backend.orchestrator.nodes as nodes
    import backend.tools.executor as executor

    # Deterministic single-tool planner for tests regardless of .env
    llm.plan_single_tool = llm._keyword_plan  # type: ignore[assignment]

    # Stub tool execution so pytest never hits live APIs
    executor.execute_tool = _stub_execute_tool  # type: ignore[assignment]
    nodes.execute_tool = _stub_execute_tool  # type: ignore[assignment]
