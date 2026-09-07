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
    path = f"sih_satellite_data/{name}_{scene}_test.tif"
    return {
        "status": "success",
        "data": {"file_path": path, "file_name": path.split("/")[-1], "format": "GeoTIFF"},
        "source": {"provider": "test", "collection": collection, "scene_id": scene},
        "quality": {"cloud_cover": 0.0, "valid": True},
        "request": args,
    }


def pytest_configure() -> None:
    import backend.orchestrator.llm as llm
    import backend.orchestrator.nodes as nodes
    import backend.tools.executor as executor

    # Deterministic planner for tests regardless of .env
    llm.make_plan = llm._keyword_plan  # type: ignore[assignment]

    # Stub tool execution so pytest never hits live APIs
    executor.execute_tool = _stub_execute_tool  # type: ignore[assignment]
    nodes.execute_tool = _stub_execute_tool  # type: ignore[assignment]
