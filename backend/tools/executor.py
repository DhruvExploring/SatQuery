"""Tool execution dispatcher for SatQuery Tools 1–8."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Callable

from backend.config.settings import settings

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _wrap_tool_error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ValueError):
        return {
            "status": "error",
            "error": {
                "type": "validation_error",
                "message": str(exc),
            },
        }

    if isinstance(exc, ImportError):
        logger.error(
            "SATQUERY_IMPORT_ERROR interpreter=%s cwd=%s",
            sys.executable,
            Path.cwd(),
            exc_info=True,
        )
        return {
            "status": "error",
            "error": {
                "type": "import_error",
                "message": (
                    f"Could not import tool module: {exc}. "
                    f"Interpreter: {sys.executable}"
                ),
            },
        }

    return {
        "status": "error",
        "error": {
            "type": "service_error",
            "message": str(exc),
        },
    }


# ---------------------------------------------------------------------
# TOOL 1
# ---------------------------------------------------------------------

def _run_optical(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from Tool_1_fetch_optical_imagery.fetch_optical_imagery import (
            OpticalSatelliteRequest,
            fetch_optical_imagery,
        )

        req = OpticalSatelliteRequest(
            bbox=args.get("bbox") or [],
            start_date=args.get("start_date") or settings.default_start_date,
            end_date=args.get("end_date") or settings.default_end_date,
            max_cloud_cover=float(
                args.get("max_cloud_cover")
                or settings.default_max_cloud_cover
            ),
            width=int(args.get("width") or settings.default_width),
            height=int(args.get("height") or settings.default_height),
            crs=args.get("crs") or settings.default_crs,
        )

        return fetch_optical_imagery(req)

    except Exception as exc:
        return _wrap_tool_error(exc)


# ---------------------------------------------------------------------
# TOOL 2
# ---------------------------------------------------------------------

def _run_multispectral(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from Tool_2_fetch_multispectral_imagery.fetch_multispectral_imagery import (
            MultispectralSatelliteRequest,
            fetch_multispectral_imagery,
        )

        req = MultispectralSatelliteRequest(
            bbox=args.get("bbox") or [],
            start_date=args.get("start_date") or settings.default_start_date,
            end_date=args.get("end_date") or settings.default_end_date,
            bands=args.get("bands") or ["B02", "B03", "B04", "B08"],
            max_cloud_cover=float(
                args.get("max_cloud_cover")
                or settings.default_max_cloud_cover
            ),
            width=int(args.get("width") or settings.default_width),
            height=int(args.get("height") or settings.default_height),
            crs=args.get("crs") or settings.default_crs,
        )

        return fetch_multispectral_imagery(req)

    except Exception as exc:
        return _wrap_tool_error(exc)


# ---------------------------------------------------------------------
# TOOL 3
# ---------------------------------------------------------------------

def _run_sar(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from Tool_3_fetch_sar_imagery.fetch_sar_imagery import (
            SARSatelliteRequest,
            fetch_sar_imagery,
        )

        req = SARSatelliteRequest(
            bbox=args.get("bbox") or [],
            start_date=args.get("start_date") or settings.default_start_date,
            end_date=args.get("end_date") or settings.default_end_date,
            scene_selection=args.get("scene_selection") or "most_recent",
            polarization=args.get("polarization") or ["VV", "VH"],
            orbit_direction=args.get("orbit_direction") or "BOTH",
            width=int(args.get("width") or settings.default_width),
            height=int(args.get("height") or settings.default_height),
            crs=args.get("crs") or settings.default_crs,
        )

        return fetch_sar_imagery(req)

    except Exception as exc:
        return _wrap_tool_error(exc)


# ---------------------------------------------------------------------
# TOOL 4
# ---------------------------------------------------------------------

def _run_weather(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from Tool_4_fetch_weather_environment.fetch_weather_environment import (
            WeatherEnvironmentRequest,
            fetch_weather_environment,
        )

        req = WeatherEnvironmentRequest(
            bbox=args.get("bbox"),
            latitude=args.get("latitude"),
            longitude=args.get("longitude"),
            start_date=args.get("start_date") or settings.default_start_date,
            end_date=args.get("end_date") or settings.default_end_date,
            rolling_windows=args.get("rolling_windows") or [7, 30],
        )

        return fetch_weather_environment(req)

    except Exception as exc:
        return _wrap_tool_error(exc)


# ---------------------------------------------------------------------
# TOOL 5
# ---------------------------------------------------------------------

def _run_vegetation_indices(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from Tool_5_compute_vegetation_indices.compute_vegetation_indices import (
            VegetationIndicesRequest,
            compute_vegetation_indices,
        )

        req = VegetationIndicesRequest(
            file_path=args.get("input_file") or args.get("file_path"),
            indices=args.get("indices") or ["NDVI"],
            band_mapping=args.get("band_mapping"),
            calculate_heuristic_classification=bool(
                args.get("calculate_heuristic_classification", False)
            ),
            output_dir=args.get("analysis_output_dir")
            or args.get("output_dir"),
        )

        return compute_vegetation_indices(req)

    except Exception as exc:
        return _wrap_tool_error(exc)


# ---------------------------------------------------------------------
# TOOL 6
# ---------------------------------------------------------------------

def _run_geotiff_inspection(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from Tool_6_inspect_geotiff_metadata.inspect_geotiff_metadata import (
            GeoTIFFInspectionRequest,
            inspect_geotiff_metadata,
        )

        req = GeoTIFFInspectionRequest(
            file_path=args.get("input_file") or args.get("file_path"),
            compare_with=args.get("compare_with"),
            calculate_statistics=bool(
                args.get("calculate_statistics", False)
            ),
            calculate_histogram=bool(
                args.get("calculate_histogram", False)
            ),
        )

        return inspect_geotiff_metadata(req)

    except Exception as exc:
        return _wrap_tool_error(exc)


# ---------------------------------------------------------------------
# TOOL 7
# ---------------------------------------------------------------------

def _run_temporal_change(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from Tool_7_analyze_temporal_change.analyze_temporal_change import (
            TemporalChangeRequest,
            analyze_temporal_change,
        )

        req = TemporalChangeRequest(
            raster_before_path=args.get("raster_before_path"),
            raster_after_path=args.get("raster_after_path"),
            band_selection=args.get("band_selection"),
            threshold_type=args.get("threshold_type"),
            threshold_value=args.get("threshold_value"),
            relative_change_threshold_percent=args.get(
                "relative_change_threshold_percent"
            ),
            mask_encoding=args.get("mask_encoding"),
            output_dir=args.get("analysis_output_dir")
            or args.get("output_dir"),
            generate_difference_raster=bool(
                args.get("generate_difference_raster", True)
            ),
            generate_change_mask=bool(
                args.get("generate_change_mask", True)
            ),
        )

        return analyze_temporal_change(req)

    except Exception as exc:
        return _wrap_tool_error(exc)


# ---------------------------------------------------------------------
# TOOL 8
# ---------------------------------------------------------------------

def _run_spatial_landcover_terrain(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from Tool_8_analyze_spatial_landcover_terrain.analyze_spatial_landcover_terrain import (
            SpatialLandcoverTerrainRequest,
            analyze_spatial_landcover_terrain,
        )

        req = SpatialLandcoverTerrainRequest(
            lulc_raster_path=args.get("lulc_raster_path"),
            dem_raster_path=args.get("dem_raster_path"),
            zone_mask_path=args.get("zone_mask_path")
            or args.get("last_change_mask_path"),
            calculate_fragmentation=bool(
                args.get("calculate_fragmentation", False)
            ),
            output_dir=args.get("analysis_output_dir")
            or args.get("output_dir"),
            class_legend=args.get("class_legend"),
            zone_legend=args.get("zone_legend"),
        )

        return analyze_spatial_landcover_terrain(req)

    except Exception as exc:
        return _wrap_tool_error(exc)


# ---------------------------------------------------------------------
# DISPATCH TABLE
# ---------------------------------------------------------------------

_EXECUTORS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    # Tool 1
    "fetch_satellite_imagery": _run_optical,
    "fetch_optical_imagery": _run_optical,

    # Tool 2
    "fetch_multispectral_imagery": _run_multispectral,

    # Tool 3
    "fetch_sar": _run_sar,
    "fetch_sar_imagery": _run_sar,

    # Tool 4
    "fetch_weather_environment": _run_weather,

    # Tool 5
    "compute_vegetation_indices": _run_vegetation_indices,

    # Tool 6
    "inspect_geotiff_metadata": _run_geotiff_inspection,

    # Tool 7
    "analyze_temporal_change": _run_temporal_change,

    # Tool 8
    "analyze_spatial_landcover_terrain": _run_spatial_landcover_terrain,
}


def execute_tool(
    name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch a tool by registry name."""

    executor = _EXECUTORS.get(name)

    if executor is None:
        return {
            "status": "error",
            "error": {
                "type": "unknown_tool",
                "message": f"No executor is registered for tool '{name}'.",
            },
        }

    logger.info("Executing SatQuery tool: %s", name)

    return executor(args)