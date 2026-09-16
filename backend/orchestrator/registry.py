"""Single source of truth for SatQuery tools, routing and trusted arguments."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from backend.config.settings import settings
from backend.orchestrator.state import Plan, SatQueryState

# Canonical tool names
TOOL_OPTICAL = "fetch_optical_imagery"
TOOL_MULTI = "fetch_multispectral_imagery"
TOOL_SAR = "fetch_sar_imagery"
TOOL_WEATHER = "fetch_weather_environment"
TOOL_INDICES = "compute_vegetation_indices"
TOOL_INSPECT = "inspect_geotiff_metadata"
TOOL_TEMPORAL = "analyze_temporal_change"
TOOL_SPATIAL = "analyze_spatial_landcover_terrain"
TOOL_WILDFIRE = "workflow_wildfire_burn_severity"
TOOL_FLOOD = "workflow_flood_inundation_impact"
TOOL_DROUGHT = "workflow_agricultural_drought_canopy_stress"
TOOL_VLM = "analyze_imagery_vlm"
TOOL_MARK_REGION = "mark_region_in_image"
TOOL_VISUAL_COMPARE = "compare_images_visually"
TOOL_GEOCODE = "get_place_name_from_coordinates"
TOOL_WEB_INTEL = "fetch_web_intelligence"
TOOL_GEOCODE_FORWARD = "geocode_place_to_coordinates"
TOOL_SCENE_IDENTITY = "resolve_scene_identity"
TOOL_POI_DISCOVERY = "discover_points_of_interest"
TOOL_AFFINE_MARKUP = "deterministic_affine_markup"
TOOL_DESCRIBE_REGION = "describe_marked_region"

PLANNER_PRIORITY = (
    TOOL_SAR,
    TOOL_WEATHER,
    TOOL_MULTI,
    TOOL_OPTICAL,
)

# Bands required by Tool 5's default 10-index set (NDVI…NBR, including NDRE/NDMI).
ANALYTICAL_S2_BANDS = ["B02", "B03", "B04", "B05", "B07", "B08", "B11", "B12"]
DEFAULT_VEGETATION_INDICES = [
    "NDVI",
    "EVI",
    "SAVI",
    "GNDVI",
    "NDRE_B5",
    "NDRE_B7",
    "NDMI",
    "NDWI",
    "MSAVI",
    "NBR",
]


def reconcile_sar_args(args: dict[str, Any], state: SatQueryState) -> dict[str, Any]:
    """Reconcile SAR parameters between user state, query text, and planner args."""
    reconciled = dict(args)
    query_text = (state.get("query") or "").lower()

    # Orbit: HTTP state > query keywords > BOTH (ignore hallucinated LLM values)
    if state.get("orbit_direction"):
        reconciled["orbit_direction"] = state["orbit_direction"]
    elif "ascending" in query_text:
        reconciled["orbit_direction"] = "ASCENDING"
    elif "descending" in query_text:
        reconciled["orbit_direction"] = "DESCENDING"
    else:
        reconciled["orbit_direction"] = "BOTH"

    # Polarization: HTTP state > caller args > ["VV", "VH"]
    if state.get("polarization"):
        reconciled["polarization"] = state["polarization"]
    elif reconciled.get("polarization"):
        pass
    else:
        reconciled["polarization"] = ["VV", "VH"]

    return reconciled


def _last_raster_path(state: SatQueryState) -> str | None:
    for item in reversed(state.get("tool_results") or []):
        result = item.get("result") or {}
        candidates = [
            result.get("data", {}).get("file_path") if isinstance(result.get("data"), dict) else None,
            result.get("file", {}).get("file_path") if isinstance(result.get("file"), dict) else None,
            result.get("generated_products", {}).get("difference_raster_path") if isinstance(result.get("generated_products"), dict) else None,
        ]
        for path in candidates:
            if path:
                return path
    return None


def _tool7_paths(state: SatQueryState) -> tuple[str | None, str | None]:
    before = state.get("raster_before_path")
    after = state.get("raster_after_path")
    if before and after:
        return before, after
    rasters: list[str] = []
    for item in state.get("tool_results") or []:
        result = item.get("result") or {}
        for path in (
            result.get("data", {}).get("file_path") if isinstance(result.get("data"), dict) else None,
            result.get("file", {}).get("file_path") if isinstance(result.get("file"), dict) else None,
        ):
            if path and path not in rasters:
                rasters.append(path)
    if len(rasters) >= 2:
        return rasters[-2], rasters[-1]
    return before, after


def _default_change_threshold(before: str | None, after: str | None) -> float:
    """0.15 suits a -1..1 vegetation index; SAR backscatter is in dB, where a
    real flood/burn signal is several dB, so a much larger absolute
    threshold is needed or nearly every pixel reads as "changed" from normal
    speckle noise alone. Detected from the file names, same heuristic
    _relative_percent_for_temporal_change below uses for SAR.
    """
    joined = ((before or "") + (after or "")).lower()
    return 3.0 if "sar" in joined else 0.15


def _relative_percent_for_temporal_change(
    before: str | None, after: str | None, state: SatQueryState
) -> float | None:
    """A relative-percent change threshold doesn't apply to SAR backscatter
    (dB, not a bounded -1..1 index) -- ignore any explicitly-set value when
    either raster looks like a SAR product."""
    joined = ((before or "") + (after or "")).lower()
    if "sar" in joined:
        return None
    return state.get("relative_change_threshold_percent")


def derive_grounding_fields(metadata_result: dict[str, Any]) -> dict[str, Any]:
    """Every field any downstream tool's location/trusted-args logic can
    legitimately derive from a single GeoTIFF's own inspect_geotiff_metadata
    output: its real-world bounding box and centroid.
    """
    bounds = (metadata_result.get("spatial") or {}).get("bounds_wgs84")
    if not bounds:
        return {}
    return {
        "bbox": [bounds["min_lon"], bounds["min_lat"], bounds["max_lon"], bounds["max_lat"]],
        "latitude": (bounds["min_lat"] + bounds["max_lat"]) / 2.0,
        "longitude": (bounds["min_lon"] + bounds["max_lon"]) / 2.0,
    }


def _region_center(state: SatQueryState) -> tuple[float, float] | None:
    """Geometric center of a marked region_bbox: the intersection of its two
    diagonals, i.e. the midpoint of its min/max lat and min/max lon. Returns
    (latitude, longitude) or None if no region is marked."""
    region_bbox = state.get("region_bbox")
    if not region_bbox or len(region_bbox) != 4:
        return None
    min_lon, min_lat, max_lon, max_lat = region_bbox
    return (min_lat + max_lat) / 2.0, (min_lon + max_lon) / 2.0


def _effective_point(state: SatQueryState) -> tuple[float, float] | None:
    """The (latitude, longitude) any location-based tool should search.

    A marked region's center takes priority over a plain latitude/longitude
    already on state: marking a region is a deliberate, specific signal of
    what "here" means, and should override a coarser point (e.g. the whole
    uploaded image's centroid) for any tool consulted afterward.
    """
    center = _region_center(state)
    if center is not None:
        return center
    latitude, longitude = state.get("latitude"), state.get("longitude")
    if latitude is not None and longitude is not None:
        return latitude, longitude
    return None


def _effective_bbox(state: SatQueryState) -> list[float] | None:
    """The bbox any area-based tool should search: a marked region takes
    priority over the whole image/AOI bbox, for the same reason as above."""
    return state.get("region_bbox") or state.get("bbox")


def _geocoded_features_for_markup(state: SatQueryState) -> list[dict[str, Any]]:
    """Known-coordinate features to project onto a raster with Tool 11.

    Prefers landmarks already resolved by a prior geocode_place_to_coordinates
    or resolve_scene_identity call; falls back to the effective point (a
    marked region's center, or the plain lat/long already on state -- e.g.
    from a weather/geocode request) using the query as a name.
    """
    landmarks = state.get("geocoded_landmarks")
    if landmarks:
        return landmarks
    point = _effective_point(state)
    if point is not None:
        return [{
            "name": state.get("query") or "Target location",
            "latitude": point[0],
            "longitude": point[1],
        }]
    return []


def trusted_args_for_tool(tool: str, state: SatQueryState) -> dict[str, Any]:
    """Build tool args only from request state/defaults and prior trusted outputs."""
    if tool in (TOOL_OPTICAL, "fetch_satellite_imagery"):
        return {
            "bbox": state.get("bbox"),
            "start_date": state.get("start_date") or settings.default_start_date,
            "end_date": state.get("end_date") or settings.default_end_date,
            "modality": state.get("modality") or "optical",
            "bands": state.get("bands"),
            "max_cloud_cover": state.get("max_cloud_cover", settings.default_max_cloud_cover),
            "width": state.get("width", settings.default_width),
            "height": state.get("height", settings.default_height),
            "crs": settings.default_crs,
        }
    if tool == TOOL_MULTI:
        return {
            "bbox": state.get("bbox"),
            "start_date": state.get("start_date") or settings.default_start_date,
            "end_date": state.get("end_date") or settings.default_end_date,
            "modality": "multispectral",
            "bands": state.get("bands") or ANALYTICAL_S2_BANDS,
            "max_cloud_cover": state.get("max_cloud_cover", settings.default_max_cloud_cover),
            "width": state.get("width", settings.default_width),
            "height": state.get("height", settings.default_height),
            "crs": settings.default_crs,
        }
    if tool in (TOOL_SAR, "fetch_sar"):
        args = {
            "bbox": state.get("bbox"),
            "start_date": state.get("start_date") or settings.default_start_date,
            "end_date": state.get("end_date") or settings.default_end_date,
            "width": state.get("width", settings.default_width),
            "height": state.get("height", settings.default_height),
            "crs": settings.default_crs,
            "polarization": state.get("polarization") or ["VV", "VH"],
            "orbit_direction": state.get("orbit_direction") or "BOTH",
            "scene_selection": state.get("scene_selection"),
        }
        return reconcile_sar_args(args, state)
    if tool == TOOL_WEATHER:
        # Unlike the imagery fetch tools, "no dates given" for weather most
        # plausibly means "conditions right now" -- default to the last 7
        # days through today rather than the fixed historical demo window,
        # so Tool 4's current/forecast support is actually reachable without
        # the caller having to name today's date explicitly.
        point = _effective_point(state)
        # Tool 4 prefers bbox over latitude/longitude when both are given
        # (see resolve_weather_sampling_points), so a marked region's center
        # point must be sent alone -- with bbox suppressed -- or the whole
        # image's larger bbox would silently win instead of the exact spot
        # the user marked.
        marked = bool(state.get("region_bbox"))
        return {
            "latitude": point[0] if point else state.get("latitude"),
            "longitude": point[1] if point else state.get("longitude"),
            "bbox": None if marked else state.get("bbox"),
            "start_date": state.get("start_date") or (date.today() - timedelta(days=7)).isoformat(),
            "end_date": state.get("end_date") or date.today().isoformat(),
        }
    if tool == TOOL_INDICES:
        return {
            "file_path": state.get("input_file") or _last_raster_path(state),
            "indices": state.get("indices") or DEFAULT_VEGETATION_INDICES,
            "band_mapping": state.get("band_mapping"),
            "calculate_heuristic_classification": state.get("calculate_heuristic_classification", True),
            "output_dir": state.get("analysis_output_dir"),
        }
    if tool == TOOL_INSPECT:
        return {
            "file_path": state.get("input_file") or _last_raster_path(state),
            "compare_with": state.get("compare_with"),
            "calculate_statistics": state.get("calculate_statistics", True),
            "calculate_histogram": state.get("calculate_histogram", True),
        }
    if tool == TOOL_TEMPORAL:
        before, after = _tool7_paths(state)
        threshold_value = state.get("threshold_value")
        if threshold_value is None:
            threshold_value = _default_change_threshold(before, after)
        return {
            "raster_before_path": before,
            "raster_after_path": after,
            "band_selection": state.get("band_selection", 1),
            "threshold_type": state.get("threshold_type", "absolute"),
            "threshold_value": threshold_value,
            "relative_change_threshold_percent": _relative_percent_for_temporal_change(before, after, state),
            "mask_encoding": state.get("mask_encoding", "bipolar_3class"),
            "output_dir": state.get("analysis_output_dir"),
            "generate_difference_raster": state.get("generate_difference_raster", True),
            "generate_change_mask": state.get("generate_change_mask", True),
        }
    if tool == TOOL_SPATIAL:
        return {
            "lulc_raster_path": state.get("lulc_raster_path"),
            "dem_raster_path": state.get("dem_raster_path"),
            "zone_mask_path": state.get("zone_mask_path") or state.get("last_change_mask_path"),
            "class_legend": state.get("class_legend"),
            "zone_legend": state.get("zone_legend"),
            "calculate_fragmentation": state.get("calculate_fragmentation", True),
            "output_dir": state.get("analysis_output_dir"),
        }
    if tool == TOOL_WILDFIRE:
        return {
            "pre_raster_path": state.get("raster_before_path"),
            "post_raster_path": state.get("raster_after_path"),
            "lulc_raster_path": state.get("lulc_raster_path"),
            "dem_raster_path": state.get("dem_raster_path"),
            "output_dir": state.get("analysis_output_dir"),
        }
    if tool == TOOL_FLOOD:
        return {
            "sar_pre_raster_path": state.get("raster_before_path"),
            "sar_post_raster_path": state.get("raster_after_path"),
            "lulc_raster_path": state.get("lulc_raster_path"),
            "dem_raster_path": state.get("dem_raster_path"),
            "output_dir": state.get("analysis_output_dir"),
            "bbox": state.get("bbox"),
            "latitude": state.get("latitude"),
            "longitude": state.get("longitude"),
            "start_date": state.get("start_date") or settings.default_start_date,
            "end_date": state.get("end_date") or settings.default_end_date,
            "include_weather": bool(
                state.get("bbox")
                or (
                    state.get("latitude") is not None
                    and state.get("longitude") is not None
                )
            ),
        }
    if tool == TOOL_DROUGHT:
        return {
            "multispectral_raster_path": state.get("input_file") or _last_raster_path(state),
            "output_dir": state.get("analysis_output_dir"),
            "bbox": state.get("bbox"),
            "latitude": state.get("latitude"),
            "longitude": state.get("longitude"),
            "start_date": state.get("start_date") or settings.default_start_date,
            "end_date": state.get("end_date") or settings.default_end_date,
        }
    if tool in (TOOL_VLM, TOOL_MARK_REGION):
        # Same underlying vision call either way -- the provider's own
        # system prompt (backend/vision/openai_provider.py) is what decides
        # whether to also return a bbox, based on the query wording. This
        # tool is just a distinct, explicit name the planner can choose for
        # "locate/mark X" requests instead of a generic description.
        return {
            "image_path": state.get("input_file") or _last_raster_path(state),
            "query": state.get("query"),
        }
    if tool == TOOL_VISUAL_COMPARE:
        before, after = _tool7_paths(state)
        return {
            "image_path_a": before,
            "image_path_b": after,
            "query": state.get("query"),
        }
    if tool == TOOL_GEOCODE:
        point = _effective_point(state)
        return {
            "latitude": point[0] if point else state.get("latitude"),
            "longitude": point[1] if point else state.get("longitude"),
        }
    if tool == TOOL_WEB_INTEL:
        point = _effective_point(state)
        return {
            "query": state.get("query"),
            "bbox": _effective_bbox(state),
            "latitude": point[0] if point else None,
            "longitude": point[1] if point else None,
        }
    if tool == TOOL_GEOCODE_FORWARD:
        return {
            "query": state.get("query"),
            "bbox": _effective_bbox(state),
            "viewbox_clamping": True,
            "max_results": 5,
        }
    if tool == TOOL_SCENE_IDENTITY:
        return {
            "bbox": _effective_bbox(state),
            "query": state.get("query"),
        }
    if tool == TOOL_POI_DISCOVERY:
        return {
            "bbox": _effective_bbox(state),
            "poi_categories": state.get("poi_categories"),
            "max_results": 15,
        }
    if tool == TOOL_AFFINE_MARKUP:
        return {
            "geotiff_path": state.get("input_file") or _last_raster_path(state),
            "features": _geocoded_features_for_markup(state),
            "output_dir": state.get("analysis_output_dir"),
        }
    if tool == TOOL_DESCRIBE_REGION:
        return {
            "image_path": state.get("input_file") or _last_raster_path(state),
            "region_bbox": state.get("region_bbox"),
            "query": state.get("query"),
        }
    raise ValueError(f"Unknown tool: {tool}")


def format_tool_success(tool: str, result: dict[str, Any]) -> str:
    if tool in (TOOL_OPTICAL, "fetch_satellite_imagery"):
        data = result.get("data", {})
        return f"Optical imagery fetched successfully: {data.get('file_path') or result.get('file_path', 'GeoTIFF saved')}."
    if tool == TOOL_MULTI:
        data = result.get("data", {})
        return f"Multispectral imagery fetched successfully: {data.get('file_path') or result.get('file_path', 'GeoTIFF saved')}."
    if tool in (TOOL_SAR, "fetch_sar"):
        data = result.get("data", {})
        return f"SAR radar imagery fetched successfully: {data.get('file_path') or result.get('file_path', 'GeoTIFF saved')}."
    if tool == TOOL_WEATHER:
        return "Weather and environmental context fetched successfully."
    if tool == TOOL_INDICES:
        data = result.get("data", {})
        return f"Vegetation indices computed successfully. Output: {data.get('file_path') or result.get('file_path', 'generated GeoTIFF')}"
    if tool == TOOL_INSPECT:
        raster = result.get("raster", {})
        quality = result.get("quality", {})
        return f"GeoTIFF inspection complete: {raster.get('width')}x{raster.get('height')}, {raster.get('band_count')} bands, CRS={result.get('spatial', {}).get('crs')}, ML-ready={quality.get('is_valid_for_ml')}."
    if tool == TOOL_TEMPORAL:
        summary = result.get("change_summary", {})
        return f"Temporal change analysis complete. Loss={summary.get('significant_decrease', {}).get('area_km2')} km², Gain={summary.get('significant_increase', {}).get('area_km2')} km²."
    if tool == TOOL_SPATIAL:
        dom = result.get("dominant_landcover", {})
        return f"Spatial land-cover/terrain analysis complete. Dominant land cover: {dom.get('name')} ({dom.get('percentage')}% of valid AOI)."
    if str(tool).startswith("workflow_"):
        pipeline = result.get("pipeline") or tool
        summary = result.get("executive_summary") or {}
        if summary:
            return f"{pipeline} completed successfully. Summary: {summary}"
        return f"{pipeline} completed successfully."
    if tool in (TOOL_VLM, TOOL_MARK_REGION, TOOL_VISUAL_COMPARE):
        return result.get("text") or "Vision interpretation completed."
    if tool == TOOL_GEOCODE:
        return f"Place resolved: {result.get('place_name', 'unknown')}."
    if tool == TOOL_WEB_INTEL:
        return result.get("summary") or "Web intelligence retrieved successfully."
    if tool == TOOL_GEOCODE_FORWARD:
        best = result.get("best_match") or {}
        return (
            f"Resolved '{result.get('query')}' to "
            f"({best.get('latitude')}, {best.get('longitude')})."
        )
    if tool == TOOL_SCENE_IDENTITY:
        return result.get("narrative_summary") or "Scene identity resolved."
    if tool == TOOL_POI_DISCOVERY:
        return f"Found {result.get('poi_count', len(result.get('pois', [])))} point(s) of interest in the AOI."
    if tool == TOOL_AFFINE_MARKUP:
        return (
            f"Marked {result.get('features_inside_aoi', 0)} feature(s) on "
            f"{result.get('marked_image_path', 'the rendered preview')}."
        )
    if tool == TOOL_DESCRIBE_REGION:
        text = result.get("text") or "Marked region described."
        place_name = result.get("place_name")
        return f"{text} (Region resolves to: {place_name}.)" if place_name else text
    return f"{tool} completed successfully."


TOOL_SPEC: dict[str, dict[str, Any]] = {
    TOOL_OPTICAL: {
        "name": TOOL_OPTICAL,
        "description": "Fetch Sentinel-2 optical imagery for a bbox and date range.",
        "requires": ["bbox", "start_date", "end_date"],
        "keywords": ("satellite", "imagery", "optical", "sentinel-2", "sentinel2", "image", "download", "visual"),
        "location": "bbox",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_OPTICAL, state),
        "response_formatter": lambda result: format_tool_success(TOOL_OPTICAL, result),
    },
    TOOL_MULTI: {
        "name": TOOL_MULTI,
        "description": "Fetch Sentinel-2 multispectral imagery for analytical processing.",
        "requires": ["bbox", "start_date", "end_date"],
        "keywords": ("multispectral", "multispectral imagery", "spectral bands", "crop health"),
        "location": "bbox",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_MULTI, state),
        "response_formatter": lambda result: format_tool_success(TOOL_MULTI, result),
    },
    TOOL_SAR: {
        "name": TOOL_SAR,
        "description": "Fetch Sentinel-1 SAR/radar imagery for a bbox and date range.",
        "requires": ["bbox", "start_date", "end_date"],
        "keywords": ("sar", "radar", "sentinel-1", "sentinel1", "backscatter", "vv", "vh", "flood"),
        "location": "bbox",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_SAR, state),
        "response_formatter": lambda result: format_tool_success(TOOL_SAR, result),
    },
    TOOL_WEATHER: {
        "name": TOOL_WEATHER,
        "description": (
            "Fetch weather/environmental context for a location and date range -- "
            "historical (ERA5 archive), current conditions, or a short-range forecast "
            "(up to ~16 days ahead), chosen automatically from the dates given. If no "
            "dates are given, defaults to the last 7 days through today."
        ),
        "requires": ["bbox_or_coords"],
        "keywords": ("weather", "rainfall", "temperature", "precipitation", "environment", "forecast", "right now", "currently", "today's weather"),
        "location": "weather",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_WEATHER, state),
        "response_formatter": lambda result: format_tool_success(TOOL_WEATHER, result),
    },
    TOOL_INDICES: {
        "name": TOOL_INDICES,
        "description": "Compute NDVI, EVI, SAVI, GNDVI, NDRE, NDMI, NDWI, MSAVI and NBR from a multispectral GeoTIFF.",
        "requires": ["input_file"],
        "keywords": ("ndvi", "evi", "savi", "gndvi", "ndre", "ndmi", "ndwi", "msavi", "nbr", "vegetation index", "vegetation indices", "compute indices"),
        "location": "file",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_INDICES, state),
        "response_formatter": lambda result: format_tool_success(TOOL_INDICES, result),
    },
    TOOL_INSPECT: {
        "name": TOOL_INSPECT,
        "description": "Deeply inspect a GeoTIFF, including CRS, bounds, bands, integrity, statistics and grid compatibility.",
        "requires": ["input_file"],
        "keywords": ("inspect geotiff", "inspect tiff", "inspect this geotiff", "inspect raster", "geotiff metadata", "raster metadata", "raster qa", "quality check", "check raster", "crs", "nodata", "histogram"),
        "location": "file",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_INSPECT, state),
        "response_formatter": lambda result: format_tool_success(TOOL_INSPECT, result),
    },
    TOOL_TEMPORAL: {
        "name": TOOL_TEMPORAL,
        "description": "Compare two aligned GeoTIFF rasters over time and produce difference and change-mask rasters.",
        "requires": ["raster_before_path", "raster_after_path"],
        "keywords": ("temporal change", "change detection", "change between", "compare dates", "before and after", "change mask", "deforestation", "vegetation loss", "vegetation gain"),
        "location": "files",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_TEMPORAL, state),
        "response_formatter": lambda result: format_tool_success(TOOL_TEMPORAL, result),
    },
    TOOL_SPATIAL: {
        "name": TOOL_SPATIAL,
        "description": "Analyze LULC composition, fragmentation, DEM terrain and zonal change-mask impacts.",
        "requires": ["lulc_raster_path"],
        "keywords": ("land cover", "landcover", "lulc", "worldcover", "terrain", "slope", "elevation", "fragmentation", "patch"),
        "location": "lulc",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_SPATIAL, state),
        "response_formatter": lambda result: format_tool_success(TOOL_SPATIAL, result),
    },
    TOOL_WILDFIRE: {
        "name": TOOL_WILDFIRE,
        "description": "Pipeline A: NBR burn severity, slope risk and forest loss.",
        "requires": ["raster_before_path", "raster_after_path", "lulc_raster_path"],
        "keywords": ("wildfire", "wild fire", "burn severity", "burn scar", "fire scar", "forest fire", "pre-fire", "post-fire"),
        "location": "mission_pair_lulc",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_WILDFIRE, state),
        "response_formatter": lambda result: format_tool_success(TOOL_WILDFIRE, result),
    },
    TOOL_FLOOD: {
        "name": TOOL_FLOOD,
        "description": "Pipeline B: SAR flood inundation and LULC impact.",
        "requires": ["raster_before_path", "raster_after_path", "lulc_raster_path"],
        "keywords": ("flood", "inundation", "monsoon flood"),
        "location": "mission_pair_lulc",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_FLOOD, state),
        "response_formatter": lambda result: format_tool_success(TOOL_FLOOD, result),
    },
    TOOL_DROUGHT: {
        "name": TOOL_DROUGHT,
        "description": "Pipeline C: agricultural drought and canopy stress.",
        "requires": ["input_file"],
        "keywords": ("drought", "canopy stress", "agricultural drought", "crop water stress"),
        "location": "mission_drought",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_DROUGHT, state),
        "response_formatter": lambda result: format_tool_success(TOOL_DROUGHT, result),
    },
    TOOL_VLM: {
        "name": TOOL_VLM,
        "description": (
            "Interpret a rendered satellite image with a vision-language model "
            "(EarthMind, InternVL, or an OpenAI vision model, depending on config), "
            "answering a natural-language question about what it shows."
        ),
        "requires": ["image_path"],
        "keywords": (
            "describe this image",
            "describe the image",
            "what do you see",
            "what does this look like",
            "interpret this imagery",
            "interpret this image",
            "visually describe",
        ),
        "location": "vlm",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_VLM, state),
        "response_formatter": lambda result: format_tool_success(TOOL_VLM, result),
    },
    TOOL_MARK_REGION: {
        "name": TOOL_MARK_REGION,
        "description": (
            "Locate a specific region, object, or feature the user asks about in an "
            "image, returning both a description and an approximate bounding box "
            "(as fractions of image width/height) for where it is -- a rough visual "
            "estimate from a general vision model, not a precise pixel measurement."
        ),
        "requires": ["image_path"],
        "keywords": (
            "mark the region",
            "mark this region",
            "mark the area",
            "highlight the region",
            "highlight the area",
            "circle the",
            "draw a box around",
            "point out",
            "where exactly is",
            "locate the",
        ),
        "location": "vlm",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_MARK_REGION, state),
        "response_formatter": lambda result: format_tool_success(TOOL_MARK_REGION, result),
    },
    TOOL_VISUAL_COMPARE: {
        "name": TOOL_VISUAL_COMPARE,
        "description": (
            "Qualitatively compare two images with a vision-language model and describe "
            "what's visually similar or different between them (land cover, built-up area, "
            "vegetation, water extent, visible damage). Unlike analyze_temporal_change, this "
            "never requires the two rasters to be grid-aligned -- it works across different "
            "sensors, dates, or even different locations, and will say so if the two images "
            "don't actually show the same place. Prefer this over analyze_temporal_change "
            "whenever the two rasters might not be pixel-aligned, or after "
            "analyze_temporal_change has already failed due to misalignment."
        ),
        "requires": ["raster_before_path", "raster_after_path"],
        "keywords": (),
        "location": "files",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_VISUAL_COMPARE, state),
        "response_formatter": lambda result: format_tool_success(TOOL_VISUAL_COMPARE, result),
    },
    TOOL_GEOCODE: {
        "name": TOOL_GEOCODE,
        "description": "Resolve a latitude/longitude pair to a human-readable place name.",
        "requires": ["latitude", "longitude"],
        "keywords": ("place name", "location name", "where is this", "what place", "what is this place called"),
        "location": "coords",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_GEOCODE, state),
        "response_formatter": lambda result: format_tool_success(TOOL_GEOCODE, result),
    },
    TOOL_WEB_INTEL: {
        "name": TOOL_WEB_INTEL,
        "description": (
            "Fetch ground-truth real-world context via web search (Tavily, "
            "falling back to DuckDuckGo): event causes, disaster reports, "
            "infrastructure project names, and location background that "
            "satellite imagery cannot itself provide."
        ),
        "requires": ["query"],
        "keywords": ("news about", "what happened", "why did", "event context", "background on", "disaster report", "search the web", "web search", "ground truth"),
        "location": "query",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_WEB_INTEL, state),
        "response_formatter": lambda result: format_tool_success(TOOL_WEB_INTEL, result),
    },
    TOOL_GEOCODE_FORWARD: {
        "name": TOOL_GEOCODE_FORWARD,
        "description": "Resolve a place name or landmark (e.g. 'Red Fort') to WGS84 coordinates and a bounding box.",
        "requires": ["query"],
        "keywords": ("coordinates of", "lat/long of", "latitude and longitude of", "where is", "find the location of", "geocode"),
        "location": "query",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_GEOCODE_FORWARD, state),
        "response_formatter": lambda result: format_tool_success(TOOL_GEOCODE_FORWARD, result),
    },
    TOOL_SCENE_IDENTITY: {
        "name": TOOL_SCENE_IDENTITY,
        "description": (
            "Given a bbox, resolve which region/locality/city it covers and, "
            "when the query names specific landmarks, forward-geocode each "
            "one and report whether it actually falls inside the scene."
        ),
        "requires": ["bbox"],
        "keywords": ("what region is this", "what area is this", "scene identity", "which city is this", "which district", "identify this scene", "what place does this scene cover"),
        "location": "bbox",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_SCENE_IDENTITY, state),
        "response_formatter": lambda result: format_tool_success(TOOL_SCENE_IDENTITY, result),
    },
    TOOL_POI_DISCOVERY: {
        "name": TOOL_POI_DISCOVERY,
        "description": "Discover real-world points of interest (tourism, historic, amenity, natural, infrastructure) strictly inside a bbox via OpenStreetMap/Overpass.",
        "requires": ["bbox"],
        "keywords": ("points of interest", "poi discovery", "landmarks in this area", "what's nearby", "attractions in", "things to see", "nearby monuments"),
        "location": "bbox",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_POI_DISCOVERY, state),
        "response_formatter": lambda result: format_tool_success(TOOL_POI_DISCOVERY, result),
    },
    TOOL_AFFINE_MARKUP: {
        "name": TOOL_AFFINE_MARKUP,
        "description": (
            "Compute the exact pixel location of one or more known lat/long "
            "features on a GeoTIFF using its own affine transform (zero "
            "hallucination, unlike a vision model's guess), and draw badge "
            "markers on a rendered preview. Requires the feature coordinates "
            "to already be known -- run geocode_place_to_coordinates or "
            "resolve_scene_identity first if they are not."
        ),
        "requires": ["geotiff_path", "features"],
        "keywords": ("mark the exact location", "precisely mark", "pinpoint", "exact pixel location of", "project coordinates onto"),
        "location": "affine_markup",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_AFFINE_MARKUP, state),
        "response_formatter": lambda result: format_tool_success(TOOL_AFFINE_MARKUP, result),
    },
    TOOL_DESCRIBE_REGION: {
        "name": TOOL_DESCRIBE_REGION,
        "description": (
            "Describe exactly what is inside a region the user has already "
            "marked/drawn/selected on an image (region_bbox, in real-world "
            "WGS84 coordinates), by cropping the source GeoTIFF's own pixels "
            "to that exact bounding box and running the vision model only on "
            "that crop -- grounded in the region's real coordinates and pixel "
            "resolution, not a guess over the whole image or a re-located "
            "estimate of an unmarked area. Also reverse-geocodes the region's "
            "own center for a verified place_name, instead of leaving place "
            "identification to the vision model's guess. Runs automatically, "
            "once, whenever region_bbox is present -- you do not need to (and "
            "should not) call it yourself; its result is already in "
            "tool_results_so_far on any hop where a region is marked."
        ),
        "requires": ["input_file", "region_bbox"],
        "keywords": (
            "the marked region", "the marked area", "this marked region", "this marked area",
            "the region i marked", "the area i marked", "the region i selected", "the area i selected",
            "in the box i drew", "the selected region", "the selected area", "region_bbox",
        ),
        "location": "marked_region",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_DESCRIBE_REGION, state),
        "response_formatter": lambda result: format_tool_success(TOOL_DESCRIBE_REGION, result),
    },
    "fetch_satellite_imagery": {
        "name": "fetch_satellite_imagery",
        "description": "Fetch Sentinel-2 optical imagery for a bbox and date range.",
        "requires": ["bbox", "start_date", "end_date"],
        "keywords": ("satellite", "imagery", "optical", "sentinel-2", "sentinel2", "image", "download", "visual"),
        "location": "bbox",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_OPTICAL, state),
        "response_formatter": lambda result: format_tool_success(TOOL_OPTICAL, result),
    },
    "fetch_sar": {
        "name": "fetch_sar",
        "description": "Fetch Sentinel-1 SAR/radar imagery for a bbox and date range.",
        "requires": ["bbox", "start_date", "end_date"],
        "keywords": ("sar", "radar", "sentinel-1", "sentinel1", "backscatter", "vv", "vh", "flood"),
        "location": "bbox",
        "args_builder": lambda state: trusted_args_for_tool(TOOL_SAR, state),
        "response_formatter": lambda result: format_tool_success(TOOL_SAR, result),
    },
}

# LLM prompt lists canonical tools only (no aliases). Mission workflow tools
# ARE included -- with the deterministic handshake/agenda system removed,
# the free-form planner is now the only way to reach them.
TOOL_REGISTRY = {
    name: spec["description"]
    for name, spec in TOOL_SPEC.items()
    if name not in {"fetch_satellite_imagery", "fetch_sar"}
}

_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (TOOL_DESCRIBE_REGION, (
        "the marked region", "the marked area", "this marked region", "this marked area",
        "the region i marked", "the area i marked", "the region i selected", "the area i selected",
        "in the box i drew", "the selected region", "the selected area",
    )),
    (TOOL_AFFINE_MARKUP, ("mark the exact location", "precisely mark", "pinpoint", "exact pixel location of", "project coordinates onto")),
    (TOOL_POI_DISCOVERY, ("points of interest", "poi discovery", "landmarks in this area", "what's nearby", "attractions in", "things to see", "nearby monuments")),
    (TOOL_SCENE_IDENTITY, ("what region is this", "what area is this", "scene identity", "which city is this", "which district", "identify this scene", "what place does this scene cover")),
    (TOOL_GEOCODE_FORWARD, ("coordinates of", "lat/long of", "latitude and longitude of", "find the location of", "geocode")),
    (TOOL_WEB_INTEL, ("news about", "what happened", "why did", "event context", "background on", "disaster report", "search the web", "web search", "ground truth")),
    (TOOL_GEOCODE, ("place name", "location name", "where is this", "what place", "what is this place called")),
    (TOOL_WILDFIRE, ("wildfire", "wild fire", "burn severity", "burn scar", "fire scar", "forest fire", "pre-fire", "post-fire")),
    (TOOL_FLOOD, ("flood", "inundation", "monsoon flood")),
    (TOOL_DROUGHT, ("drought", "canopy stress", "agricultural drought", "crop water stress")),
    (TOOL_MARK_REGION, ("mark the region", "mark this region", "mark the area", "highlight the region", "highlight the area", "circle the", "draw a box around", "point out", "where exactly is", "locate the")),
    (TOOL_VLM, ("describe this image", "describe the image", "what do you see", "what does this look like", "interpret this imagery", "interpret this image", "visually describe")),
    (TOOL_SPATIAL, ("land cover", "landcover", "lulc", "worldcover", "terrain", "slope", "elevation", "fragmentation", "patch")),
    (TOOL_TEMPORAL, ("temporal change", "change detection", "change between", "compare dates", "before and after", "change mask", "deforestation", "vegetation loss", "vegetation gain")),
    (TOOL_INDICES, ("ndvi", "evi", "savi", "gndvi", "ndre", "ndmi", "ndwi", "msavi", "nbr", "vegetation index", "vegetation indices", "compute indices")),
    (TOOL_INSPECT, ("inspect geotiff", "inspect tiff", "inspect this geotiff", "inspect raster", "geotiff metadata", "raster metadata", "raster qa", "quality check", "check raster", "crs", "nodata", "histogram")),
    (TOOL_SAR, ("sar", "radar", "sentinel-1", "sentinel1", "backscatter", "vv", "vh", "flood")),
    (TOOL_WEATHER, ("weather", "rainfall", "temperature", "precipitation", "environment", "forecast", "right now", "currently", "today's weather")),
    (TOOL_MULTI, ("multispectral", "multispectral imagery", "spectral bands", "crop health")),
    (TOOL_OPTICAL, ("satellite", "imagery", "optical", "sentinel-2", "sentinel2", "image", "download", "visual")),
]


def match_tool_from_query(query: str) -> tuple[str | None, str]:
    q = query.lower().strip()
    for tool, words in _KEYWORDS:
        for word in words:
            if word in q:
                return tool, f"Query matched {tool} via '{word}'."
    return None, "No registered remote-sensing tool matched the query."


def location_ready_for_tool(tool: str, state: SatQueryState) -> bool:
    if tool not in TOOL_SPEC:
        return False
    loc = TOOL_SPEC[tool]["location"]
    if loc in {"file", "files"}:
        if loc == "file":
            return bool(state.get("input_file") or _last_raster_path(state))
        before, after = _tool7_paths(state)
        return bool(before and after)
    if loc == "lulc":
        return bool(state.get("lulc_raster_path"))
    if loc == "vlm":
        return bool(state.get("input_file") or _last_raster_path(state))
    if loc == "weather":
        return bool(state.get("bbox") or _effective_point(state) is not None)
    if loc == "mission_pair_lulc":
        return bool(
            state.get("raster_before_path")
            and state.get("raster_after_path")
            and state.get("lulc_raster_path")
        )
    if loc == "mission_drought":
        has_file = bool(state.get("input_file") or _last_raster_path(state))
        has_weather = bool(
            state.get("bbox")
            or (
                state.get("latitude") is not None
                and state.get("longitude") is not None
            )
        )
        return has_file and has_weather
    if loc == "coords":
        return _effective_point(state) is not None
    if loc == "query":
        return bool((state.get("query") or "").strip())
    if loc == "affine_markup":
        has_file = bool(state.get("input_file") or _last_raster_path(state))
        has_features = bool(_geocoded_features_for_markup(state))
        return has_file and has_features
    if loc == "marked_region":
        has_file = bool(state.get("input_file") or _last_raster_path(state))
        return has_file and bool(state.get("region_bbox"))
    return bool(state.get("bbox"))


def enforce_call_tool_location(plan: Plan, state: SatQueryState) -> Plan:
    if plan.get("action") != "call_tool" or not plan.get("tool"):
        return plan
    tool = plan["tool"]
    if tool not in TOOL_SPEC:
        return {"action": "respond_error", "tool": None, "args": {}, "reason": f"Unknown tool '{tool}'."}
    if not location_ready_for_tool(tool, state):
        # Keep `tool` on the clarify plan rather than dropping it -- a fetch
        # tool that's only missing a bbox may still be reachable next hop:
        # the routing hints steer the LLM planner to call
        # inspect_geotiff_metadata first when an input_file is present,
        # which derives bbox/latitude/longitude (see tool_loop_graph.py's
        # tool_node) so a retry of this same tool then succeeds.
        return {"action": "clarify", "tool": tool, "args": {}, "reason": _missing_input_reason(tool)}
    plan["args"] = trusted_args_for_tool(tool, state)
    return plan


def _missing_input_reason(tool: str) -> str:
    loc = TOOL_SPEC.get(tool, {}).get("location", "bbox")
    return {
        "bbox": f"{tool} requires bbox [min_lon, min_lat, max_lon, max_lat].",
        "weather": f"{tool} requires bbox or latitude and longitude.",
        "file": f"{tool} requires a GeoTIFF input file.",
        "files": f"{tool} requires raster_before_path and raster_after_path.",
        "lulc": f"{tool} requires lulc_raster_path.",
        "vlm": f"{tool} requires a rendered image or GeoTIFF (input_file) to interpret.",
        "mission_pair_lulc": (
            f"{tool} requires raster_before_path, raster_after_path, and lulc_raster_path."
        ),
        "mission_drought": (
            f"{tool} requires a multispectral GeoTIFF and bbox or latitude/longitude."
        ),
        "coords": f"{tool} requires latitude and longitude.",
        "query": f"{tool} requires a non-empty query.",
        "affine_markup": (
            f"{tool} requires a GeoTIFF (input_file) and at least one resolved "
            "lat/long feature -- run geocode_place_to_coordinates or "
            "resolve_scene_identity first."
        ),
        "marked_region": (
            f"{tool} requires a GeoTIFF (input_file) and a marked region_bbox "
            "-- draw/select a region on the image first."
        ),
    }.get(loc, f"{tool} is missing required input.")
