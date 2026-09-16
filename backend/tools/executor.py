"""Tool execution dispatcher for SatQuery Tools 1–11."""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from backend.config.settings import settings
from backend.orchestrator.registry import ANALYTICAL_S2_BANDS

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _wrap_tool_error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ValueError):
        logger.exception("SATQUERY_TOOL_VALUE_ERROR")
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


def _first_present(args: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in args and args[key] is not None:
            return args[key]
    return None


def _optional_fields(
    args: dict[str, Any],
    mapping: dict[str, str | tuple[str, ...]],
) -> dict[str, Any]:
    """Pass through caller-supplied values only.

    Missing keys are omitted so each tool's Pydantic model keeps its own defaults
    (e.g. VegetationIndicesRequest.calculate_heuristic_classification=True).
    """
    out: dict[str, Any] = {}
    for dest, sources in mapping.items():
        keys = sources if isinstance(sources, tuple) else (sources,)
        value = _first_present(args, *keys)
        if value is not None:
            out[dest] = value
    return out


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
            bands=args.get("bands") or ANALYTICAL_S2_BANDS,
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
            **_optional_fields(
                args,
                {
                    "indices": "indices",
                    "band_mapping": "band_mapping",
                    "calculate_heuristic_classification": (
                        "calculate_heuristic_classification"
                    ),
                    "output_dir": ("output_dir", "analysis_output_dir"),
                },
            ),
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
            **_optional_fields(
                args,
                {
                    "compare_with": "compare_with",
                    "calculate_statistics": "calculate_statistics",
                    "calculate_histogram": "calculate_histogram",
                },
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
            **_optional_fields(
                args,
                {
                    "band_selection": "band_selection",
                    "threshold_type": "threshold_type",
                    "threshold_value": "threshold_value",
                    "relative_change_threshold_percent": (
                        "relative_change_threshold_percent"
                    ),
                    "mask_encoding": "mask_encoding",
                    "output_dir": ("output_dir", "analysis_output_dir"),
                    "generate_difference_raster": "generate_difference_raster",
                    "generate_change_mask": "generate_change_mask",
                },
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
            **_optional_fields(
                args,
                {
                    "dem_raster_path": "dem_raster_path",
                    "zone_mask_path": (
                        "zone_mask_path",
                        "last_change_mask_path",
                    ),
                    "calculate_fragmentation": "calculate_fragmentation",
                    "output_dir": ("output_dir", "analysis_output_dir"),
                    "class_legend": "class_legend",
                    "zone_legend": "zone_legend",
                },
            ),
        )

        return analyze_spatial_landcover_terrain(req)

    except Exception as exc:
        return _wrap_tool_error(exc)


def _weather_request_from_args(args: dict[str, Any]):
    from Tool_4_fetch_weather_environment.fetch_weather_environment import (
        WeatherEnvironmentRequest,
    )

    has_location = args.get("bbox") or (
        args.get("latitude") is not None and args.get("longitude") is not None
    )
    if not has_location:
        return None
    return WeatherEnvironmentRequest(
        bbox=args.get("bbox"),
        latitude=args.get("latitude"),
        longitude=args.get("longitude"),
        start_date=args.get("start_date") or settings.default_start_date,
        end_date=args.get("end_date") or settings.default_end_date,
        rolling_windows=args.get("rolling_windows") or [7, 30],
    )


def _run_workflow_wildfire(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from satquery_workflows import workflow_wildfire_burn_severity

        return workflow_wildfire_burn_severity(
            pre_raster_path=args.get("pre_raster_path"),
            post_raster_path=args.get("post_raster_path"),
            lulc_raster_path=args.get("lulc_raster_path"),
            dem_raster_path=args.get("dem_raster_path"),
            output_dir=args.get("output_dir") or args.get("analysis_output_dir"),
        )
    except Exception as exc:
        return _wrap_tool_error(exc)


def _run_workflow_flood(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from satquery_workflows import workflow_flood_inundation_impact

        weather_request = None
        if args.get("include_weather", True):
            weather_request = _weather_request_from_args(args)
        return workflow_flood_inundation_impact(
            sar_pre_raster_path=args.get("sar_pre_raster_path"),
            sar_post_raster_path=args.get("sar_post_raster_path"),
            lulc_raster_path=args.get("lulc_raster_path"),
            weather_request=weather_request,
            dem_raster_path=args.get("dem_raster_path"),
            output_dir=args.get("output_dir") or args.get("analysis_output_dir"),
        )
    except Exception as exc:
        return _wrap_tool_error(exc)


def _run_workflow_drought(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from satquery_workflows import workflow_agricultural_drought_canopy_stress

        weather_request = _weather_request_from_args(args)
        if weather_request is None:
            raise ValueError(
                "Drought workflow requires bbox or latitude and longitude."
            )
        return workflow_agricultural_drought_canopy_stress(
            multispectral_raster_path=args.get("multispectral_raster_path"),
            weather_request=weather_request,
            output_dir=args.get("output_dir") or args.get("analysis_output_dir"),
        )
    except Exception as exc:
        return _wrap_tool_error(exc)


# ---------------------------------------------------------------------
# TOOL 9 — fetch_web_intelligence: ground-truth web search context.
# ---------------------------------------------------------------------

def _run_web_intelligence(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from Tool_9_fetch_web_intelligence.fetch_web_intelligence import (
            WebIntelligenceRequest,
            fetch_web_intelligence,
        )

        query = args.get("query")
        if not query:
            raise ValueError("fetch_web_intelligence requires a query.")

        req = WebIntelligenceRequest(
            query=query,
            **_optional_fields(
                args,
                {
                    "max_results": "max_results",
                    "search_depth": "search_depth",
                    "include_domains": "include_domains",
                    "exclude_domains": "exclude_domains",
                    "location_hint": "location_hint",
                    "bbox": "bbox",
                    "latitude": "latitude",
                    "longitude": "longitude",
                },
            ),
        )

        return fetch_web_intelligence(req)

    except Exception as exc:
        return _wrap_tool_error(exc)


# ---------------------------------------------------------------------
# TOOL 10 — spatial_geocoding_poi: forward geocoding, scene identity, and
# in-AOI POI discovery (reverse geocoding is wired separately below, behind
# the existing get_place_name_from_coordinates name).
# ---------------------------------------------------------------------

def _run_geocode_forward(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from Tool_10_spatial_geocoding_poi.spatial_geocoding_poi import forward_geocode

        query = args.get("query")
        if not query:
            raise ValueError("geocode_place_to_coordinates requires a query.")

        return forward_geocode(
            query=query,
            bbox=args.get("bbox"),
            viewbox_clamping=args.get("viewbox_clamping", True),
            max_results=int(args.get("max_results") or 5),
        )

    except Exception as exc:
        return _wrap_tool_error(exc)


def _run_scene_identity(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from Tool_10_spatial_geocoding_poi.spatial_geocoding_poi import resolve_scene_identity

        bbox = args.get("bbox")
        if not bbox:
            raise ValueError("resolve_scene_identity requires bbox.")

        return resolve_scene_identity(bbox=bbox, query=args.get("query"))

    except Exception as exc:
        return _wrap_tool_error(exc)


def _run_poi_discovery(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from Tool_10_spatial_geocoding_poi.spatial_geocoding_poi import discover_in_aoi_pois

        bbox = args.get("bbox")
        if not bbox:
            raise ValueError("discover_points_of_interest requires bbox.")

        return discover_in_aoi_pois(
            bbox=bbox,
            categories=args.get("poi_categories"),
            max_results=int(args.get("max_results") or 15),
        )

    except Exception as exc:
        return _wrap_tool_error(exc)


# ---------------------------------------------------------------------
# TOOL 11 — deterministic_affine_markup: exact pixel projection of known
# lat/long features onto a rendered GeoTIFF preview (no VLM guessing).
# ---------------------------------------------------------------------

def _run_affine_markup(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from Tool_11_deterministic_affine_markup.deterministic_affine_markup import (
            AffineMarkupRequest,
            FeatureItem,
            project_and_markup_raster,
        )

        geotiff_path = args.get("geotiff_path") or args.get("input_file")
        if not geotiff_path:
            raise ValueError("deterministic_affine_markup requires geotiff_path.")

        features = [FeatureItem(**f) for f in (args.get("features") or [])]
        req = AffineMarkupRequest(
            geotiff_path=geotiff_path,
            features=features,
            **_optional_fields(
                args,
                {
                    "base_image_path": "base_image_path",
                    "output_dir": ("output_dir", "analysis_output_dir"),
                    "draw_pill_badges": "draw_pill_badges",
                    "draw_bounding_boxes": "draw_bounding_boxes",
                    "color_palette": "color_palette",
                },
            ),
        )

        return project_and_markup_raster(req)

    except Exception as exc:
        return _wrap_tool_error(exc)


# ---------------------------------------------------------------------
# GEOCODE TOOL — lat/long -> place name.
# ---------------------------------------------------------------------

def _run_geocode(args: dict[str, Any]) -> dict[str, Any]:
    latitude = args.get("latitude")
    longitude = args.get("longitude")
    if latitude is None or longitude is None:
        return {
            "status": "error",
            "error": {
                "type": "validation_error",
                "message": "get_place_name_from_coordinates requires latitude and longitude.",
            },
        }
    try:
        from backend.tools.geocode import reverse_geocode

        result = reverse_geocode(float(latitude), float(longitude))
        return {"status": "success", **result}
    except Exception as exc:
        return _wrap_tool_error(exc)


# ---------------------------------------------------------------------
# VISION TOOL — interprets a rendered image with a swappable VLM backend.
# ---------------------------------------------------------------------

_VIEWABLE_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def _resolve_viewable_image(image_path: str) -> str:
    """A vision model needs a plain image; a GeoTIFF gets rendered to a
    temporary PNG first (same as the raster-preview endpoint)."""
    source = Path(image_path)
    if source.suffix.lower() in _VIEWABLE_IMAGE_SUFFIXES:
        return str(source)
    from backend.rendering.raster_preview import render_geotiff_preview

    logger.info("[VISION RENDER] %s is not a viewable image, rendering a PNG preview", source.name)
    png_bytes = render_geotiff_preview(str(source))
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as rendered:
        rendered.write(png_bytes)
        return rendered.name


def _run_vlm_analysis(args: dict[str, Any]) -> dict[str, Any]:
    if not settings.vision_tool_enabled:
        return {
            "status": "error",
            "error": {
                "type": "validation_error",
                "message": "The vision tool is disabled (SATQUERY_VISION_TOOL_ENABLED=false).",
            },
        }

    image_path = args.get("image_path")
    if not image_path:
        return {
            "status": "error",
            "error": {
                "type": "validation_error",
                "message": "analyze_imagery_vlm requires image_path.",
            },
        }
    query = args.get("query") or "Describe what this image shows."
    logger.info("[IMAGE RECEIVED] path=%s query=%r", image_path, query)

    try:
        from backend.vision.factory import get_vision_provider

        resolved_path = _resolve_viewable_image(image_path)

        logger.info(
            "[VISION CALL] provider=%s model=%s",
            settings.vision_tool_provider,
            settings.vision_tool_model,
        )
        result = get_vision_provider().interpret(resolved_path, query)
        logger.info(
            "[VISION RESPONSE] provider=%s chars=%d",
            result.get("provider", settings.vision_tool_provider),
            len(result.get("text") or ""),
        )
        return {"status": "success", **result}

    except Exception as exc:
        logger.info("[VISION ERROR] %s", exc)
        return _wrap_tool_error(exc)


def _run_visual_compare(args: dict[str, Any]) -> dict[str, Any]:
    """compare_images_visually: a qualitative two-image comparison via the
    vision model -- unlike analyze_temporal_change, this never requires the
    two rasters to be grid-aligned (same CRS/dimensions/transform), so it
    still works across different sensors, dates, or even different places.
    """
    if not settings.vision_tool_enabled:
        return {
            "status": "error",
            "error": {
                "type": "validation_error",
                "message": "The vision tool is disabled (SATQUERY_VISION_TOOL_ENABLED=false).",
            },
        }

    image_path_a = args.get("image_path_a")
    image_path_b = args.get("image_path_b")
    if not image_path_a or not image_path_b:
        return {
            "status": "error",
            "error": {
                "type": "validation_error",
                "message": "compare_images_visually requires image_path_a and image_path_b.",
            },
        }
    query = args.get("query") or "Compare these two images and describe what's different between them."
    logger.info("[IMAGE PAIR RECEIVED] a=%s b=%s query=%r", image_path_a, image_path_b, query)

    try:
        from backend.vision.factory import get_vision_provider

        resolved_a = _resolve_viewable_image(image_path_a)
        resolved_b = _resolve_viewable_image(image_path_b)

        provider = get_vision_provider()
        if not hasattr(provider, "compare"):
            return {
                "status": "error",
                "error": {
                    "type": "unsupported",
                    "message": (
                        f"The configured vision provider ({settings.vision_tool_provider}) "
                        "does not support two-image comparison."
                    ),
                },
            }

        logger.info(
            "[VISION COMPARE CALL] provider=%s model=%s",
            settings.vision_tool_provider,
            settings.vision_tool_model,
        )
        result = provider.compare([resolved_a, resolved_b], query)
        logger.info(
            "[VISION COMPARE RESPONSE] provider=%s chars=%d",
            result.get("provider", settings.vision_tool_provider),
            len(result.get("text") or ""),
        )
        return {"status": "success", **result}

    except Exception as exc:
        logger.info("[VISION COMPARE ERROR] %s", exc)
        return _wrap_tool_error(exc)


# ---------------------------------------------------------------------
# REGION TOOL -- describes exactly what's inside a user-marked sub-region of
# a GeoTIFF, by cropping the raster's own pixels to that real-world bbox
# (registry.py::TOOL_DESCRIBE_REGION) instead of describing the whole image
# or asking a vision model to re-locate an already-known region.
# ---------------------------------------------------------------------

def _run_describe_region(args: dict[str, Any]) -> dict[str, Any]:
    if not settings.vision_tool_enabled:
        return {
            "status": "error",
            "error": {
                "type": "validation_error",
                "message": "The vision tool is disabled (SATQUERY_VISION_TOOL_ENABLED=false).",
            },
        }

    image_path = args.get("image_path")
    region_bbox = args.get("region_bbox")
    if not image_path:
        return {
            "status": "error",
            "error": {
                "type": "validation_error",
                "message": "describe_marked_region requires image_path.",
            },
        }
    if not region_bbox or len(region_bbox) != 4:
        return {
            "status": "error",
            "error": {
                "type": "validation_error",
                "message": "describe_marked_region requires region_bbox [min_lon, min_lat, max_lon, max_lat].",
            },
        }

    query = args.get("query") or "Describe what is in this marked region."
    logger.info("[REGION DESCRIBE] image=%s region_bbox=%s query=%r", image_path, region_bbox, query)

    try:
        from backend.rendering.raster_preview import render_geotiff_region_preview

        png_bytes, region_info = render_geotiff_region_preview(image_path, region_bbox)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as rendered:
            rendered.write(png_bytes)
            cropped_path = rendered.name

        from backend.vision.factory import get_vision_provider

        logger.info(
            "[VISION CALL region] provider=%s model=%s window=%s",
            settings.vision_tool_provider,
            settings.vision_tool_model,
            region_info["pixel_window"],
        )
        result = get_vision_provider().interpret(cropped_path, query)
        logger.info(
            "[VISION RESPONSE region] provider=%s chars=%d",
            result.get("provider", settings.vision_tool_provider),
            len(result.get("text") or ""),
        )

        # Best-effort: a verified place name for the region's own center
        # (Tool 10, via the geocode adapter) grounds the answer in a real
        # lookup instead of leaving place identification to the vision
        # model's guess, which can disagree with other context (e.g. the
        # whole image's own knowledge-base place_name) with no way to tell
        # which one is actually right.
        min_lon, min_lat, max_lon, max_lat = region_bbox
        center_lat = (min_lat + max_lat) / 2.0
        center_lon = (min_lon + max_lon) / 2.0
        place_name = None
        try:
            from backend.tools.geocode import reverse_geocode

            place_name = reverse_geocode(center_lat, center_lon).get("place_name")
            logger.info(
                "[REGION DESCRIBE] reverse geocode center=(%.6f, %.6f) place_name=%r",
                center_lat, center_lon, place_name,
            )
        except Exception as geocode_exc:
            logger.info(
                "[REGION DESCRIBE] reverse geocode failed for center=(%.6f, %.6f): %s",
                center_lat, center_lon, geocode_exc,
            )

        return {
            "status": "success",
            **result,
            "region": region_info,
            "region_center": {"latitude": center_lat, "longitude": center_lon},
            "place_name": place_name,
        }

    except Exception as exc:
        logger.info("[REGION DESCRIBE ERROR] %s", exc)
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

    # Named science missions (satquery_workflows.py)
    "workflow_wildfire_burn_severity": _run_workflow_wildfire,
    "workflow_flood_inundation_impact": _run_workflow_flood,
    "workflow_agricultural_drought_canopy_stress": _run_workflow_drought,

    # Vision tool -- mark_region_in_image is the same underlying call, just a
    # distinct planner-facing name for "locate/mark X" requests (see
    # backend/vision/openai_provider.py, whose own prompt decides whether to
    # return a bbox based on the query wording either way).
    "analyze_imagery_vlm": _run_vlm_analysis,
    "mark_region_in_image": _run_vlm_analysis,
    "compare_images_visually": _run_visual_compare,

    # Reverse geocoding: lat/long -> place name.
    "get_place_name_from_coordinates": _run_geocode,

    # Tool 9 -- web search ground truth.
    "fetch_web_intelligence": _run_web_intelligence,

    # Tool 10 -- forward geocoding, scene identity, POI discovery.
    "geocode_place_to_coordinates": _run_geocode_forward,
    "resolve_scene_identity": _run_scene_identity,
    "discover_points_of_interest": _run_poi_discovery,

    # Tool 11 -- deterministic affine coordinate-to-pixel markup.
    "deterministic_affine_markup": _run_affine_markup,

    # Describe a user-marked sub-region, cropped from the source raster.
    "describe_marked_region": _run_describe_region,
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

    return executor(args)