"""MCP-shaped tool execution.

Two paths, controlled by settings.use_mock_tools:

  True  (default) → mock JSON, no network (tests always pass)
  False           → calls satellite_tool.mcp_fetch_satellite_imagery()
                    which is the extracted notebook logic

The execute node in nodes.py calls only execute_tool(name, args).
It never knows which path ran.

To add a new tool (fetch_sar, fetch_lulc, etc.):
  1. Add its real function import in _REAL_EXECUTORS
  2. Add its mock in _MOCK_EXECUTORS
  Nothing else changes.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable

from backend.config.settings import settings

TOOL_FETCH = "fetch_satellite_imagery"
TOOL_SAR = "fetch_sar"


# ---------------------------------------------------------------------------
# Mock executors — no network, always fast, used by tests
# ---------------------------------------------------------------------------
def _mock_fetch(args: dict[str, Any]) -> dict[str, Any]:
    """Stand-in for fetch_satellite_imagery. No network."""
    bbox = args.get("bbox") or [77.1, 28.5, 77.3, 28.7]
    start_date = args.get("start_date") or settings.default_start_date
    end_date = args.get("end_date") or settings.default_end_date
    scene_id = "S2C_MSIL2A_20250128T053131_N0511_R105_T43RGM_20250128T084454"
    file_name = (
        f"sentinel2_{scene_id}_{start_date}_{end_date}_"
        f"{args.get('modality', 'optical')}_mock.tif"
    )
    return {
        "status": "success",
        "data": {
            "file_path": f"sih_satellite_data/{file_name}",
            "file_name": file_name,
            "format": "GeoTIFF",
        },
        "source": {
            "provider": "Sentinel Hub",
            "collection": "sentinel-2-l2a",
            "scene_id": scene_id,
            "acquisition_time": "2025-01-28T05:41:31Z",
        },
        "request": {
            "bbox": bbox,
            "start_date": start_date,
            "end_date": end_date,
            "modality": args.get("modality", "optical"),
            "bands": args.get("bands"),
            "max_cloud_cover": args.get("max_cloud_cover", 30.0),
        },
        "raster": {
            "width": args.get("width", 512),
            "height": args.get("height", 512),
            "band_count": 3,
            "dtype": "uint16",
            "crs": args.get("crs", "EPSG:4326"),
        },
        "quality": {"cloud_cover": 0.0, "valid": True},
        "flags": {"optical_quality_poor": False, "sar_recommended": False},
    }


def _not_implemented(tool_name: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Return an executor that always reports the tool is not implemented yet."""
    def _stub(args: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "error",
            "error": {
                "type": "not_implemented",
                "message": (
                    f"Tool '{tool_name}' is registered but not implemented yet. "
                    "A real executor will be added when the tool notebook is ready."
                ),
            },
        }
    return _stub


_MOCK_EXECUTORS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    TOOL_FETCH: _mock_fetch,
    TOOL_SAR: _not_implemented(TOOL_SAR),
}


# ---------------------------------------------------------------------------
# Real executors — lazy-imported so tests never pay the import cost
# ---------------------------------------------------------------------------
def _real_fetch(args: dict[str, Any]) -> dict[str, Any]:
    """
    Delegate to the extracted notebook module.
    Import is deferred so the test suite never triggers it.
    """
    try:
        tool_module = importlib.import_module(
            "Tools.Tool_1_fetch_satellite_imagery.satellite_tool"
        )
        return tool_module.mcp_fetch_satellite_imagery(
            bbox=args.get("bbox") or [],
            start_date=args.get("start_date") or settings.default_start_date,
            end_date=args.get("end_date") or settings.default_end_date,
            modality=args.get("modality", "optical"),
            bands=args.get("bands"),
            max_cloud_cover=float(args.get("max_cloud_cover") or settings.default_max_cloud_cover),
            width=int(args.get("width") or settings.default_width),
            height=int(args.get("height") or settings.default_height),
            crs=args.get("crs", settings.default_crs),
        )
    except ImportError as exc:
        return {
            "status": "error",
            "error": {
                "type": "import_error",
                "message": (
                    f"Could not import satellite_tool: {exc}. "
                    "Ensure the Tools directory is in your PYTHONPATH "
                    "or run from the SatQuery project root."
                ),
            },
        }


_REAL_EXECUTORS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    TOOL_FETCH: _real_fetch,
    TOOL_SAR: _not_implemented(TOOL_SAR),
}


# ---------------------------------------------------------------------------
# Public dispatch — the ONLY function called by nodes.py
# ---------------------------------------------------------------------------
def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """
    Dispatch to mock or real executor based on settings.use_mock_tools.

    Returns a dict matching the MCP tool contract:
      { "status": "success"|"error", "data": ..., "source": ..., ... }
    """
    registry = _MOCK_EXECUTORS if settings.use_mock_tools else _REAL_EXECUTORS
    executor = registry.get(name)

    if executor is None:
        return {
            "status": "error",
            "error": {
                "type": "unknown_tool",
                "message": f"No executor is registered for tool '{name}'.",
            },
        }

    return executor(args)
