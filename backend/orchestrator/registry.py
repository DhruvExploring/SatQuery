"""Single source of truth for SatQuery tools, routing and trusted arguments."""
from __future__ import annotations

from typing import Any

from backend.config.settings import settings
from backend.orchestrator.state import Plan, SatQueryState

TOOL_SPEC: dict[str, dict[str, Any]] = {
    "fetch_satellite_imagery": {"description": "Fetch Sentinel-2 optical imagery for a bbox and date range.", "location": "bbox"},
    "fetch_multispectral_imagery": {"description": "Fetch Sentinel-2 multispectral imagery for analytical processing.", "location": "bbox"},
    "fetch_sar": {"description": "Fetch Sentinel-1 SAR/radar imagery for a bbox and date range.", "location": "bbox"},
    "fetch_weather_environment": {"description": "Fetch weather/environmental context for a location.", "location": "weather"},
    "compute_vegetation_indices": {"description": "Compute NDVI, EVI, SAVI, GNDVI, NDRE, NDMI, NDWI, MSAVI and NBR from a multispectral GeoTIFF.", "location": "file"},
    "inspect_geotiff_metadata": {"description": "Deeply inspect a GeoTIFF, including CRS, bounds, bands, integrity, statistics and grid compatibility.", "location": "file"},
    "analyze_temporal_change": {"description": "Compare two aligned GeoTIFF rasters over time and produce difference and change-mask rasters.", "location": "files"},
    "analyze_spatial_landcover_terrain": {"description": "Analyze LULC composition, fragmentation, DEM terrain and zonal change-mask impacts.", "location": "lulc"},
}
TOOL_REGISTRY = {name: spec["description"] for name, spec in TOOL_SPEC.items()}

_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("analyze_spatial_landcover_terrain", ("land cover", "landcover", "lulc", "worldcover", "terrain", "slope", "elevation", "fragmentation", "patch")),
    ("analyze_temporal_change", ("temporal change", "change detection", "change between", "compare dates", "before and after", "change mask", "deforestation", "vegetation loss", "vegetation gain")),
    ("compute_vegetation_indices", ("ndvi", "evi", "savi", "gndvi", "ndre", "ndmi", "ndwi", "msavi", "nbr", "vegetation index", "vegetation indices", "crop health")),
    ("inspect_geotiff_metadata", ("inspect geotiff", "inspect tiff", "inspect this geotiff", "inspect raster", "geotiff metadata", "raster metadata", "raster qa", "quality check", "check raster", "crs", "nodata", "histogram")),
    ("fetch_weather_environment", ("weather", "rainfall", "temperature", "precipitation", "environment")),
    ("fetch_sar", ("sar", "radar", "sentinel-1", "sentinel1", "backscatter", "vv", "vh")),
    ("fetch_multispectral_imagery", ("multispectral", "multispectral imagery", "spectral bands")),
    ("fetch_satellite_imagery", ("satellite", "imagery", "optical", "sentinel-2", "sentinel2", "image", "download")),
]

def match_tool_from_query(query: str) -> tuple[str | None, str]:
    q = query.lower().strip()
    for tool, words in _KEYWORDS:
        for word in words:
            if word in q:
                return tool, f"Query matched {tool} via '{word}'."
    return None, "No registered remote-sensing tool matched the query."

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

def trusted_args_for_tool(tool: str, state: SatQueryState) -> dict[str, Any]:
    """Build tool args only from request state/defaults and prior trusted outputs."""
    if tool == "fetch_satellite_imagery":
        return {"bbox": state.get("bbox"), "start_date": state.get("start_date") or settings.default_start_date, "end_date": state.get("end_date") or settings.default_end_date, "modality": state.get("modality") or "optical", "bands": state.get("bands"), "max_cloud_cover": state.get("max_cloud_cover", settings.default_max_cloud_cover), "width": state.get("width", settings.default_width), "height": state.get("height", settings.default_height), "crs": settings.default_crs}
    if tool == "fetch_multispectral_imagery":
        return {"bbox": state.get("bbox"), "start_date": state.get("start_date") or settings.default_start_date, "end_date": state.get("end_date") or settings.default_end_date, "modality": "multispectral", "bands": state.get("bands"), "max_cloud_cover": state.get("max_cloud_cover", settings.default_max_cloud_cover), "width": state.get("width", settings.default_width), "height": state.get("height", settings.default_height), "crs": settings.default_crs}
    if tool == "fetch_sar":
        return {"bbox": state.get("bbox"), "start_date": state.get("start_date") or settings.default_start_date, "end_date": state.get("end_date") or settings.default_end_date, "width": state.get("width", settings.default_width), "height": state.get("height", settings.default_height), "crs": settings.default_crs, "polarization": state.get("polarization"), "orbit_direction": state.get("orbit_direction"), "scene_selection": state.get("scene_selection")}
    if tool == "fetch_weather_environment":
        args = {"latitude": state.get("latitude"), "longitude": state.get("longitude"), "bbox": state.get("bbox"), "start_date": state.get("start_date") or settings.default_start_date, "end_date": state.get("end_date") or settings.default_end_date}
        return args
    if tool == "compute_vegetation_indices":
        return {"file_path": state.get("input_file") or _last_raster_path(state), "indices": state.get("indices") or ["NDVI", "EVI", "SAVI", "GNDVI", "NDRE_B5", "NDRE_B7", "NDMI", "NDWI", "MSAVI", "NBR"], "band_mapping": state.get("band_mapping"), "calculate_heuristic_classification": state.get("calculate_heuristic_classification", True)}
    if tool == "inspect_geotiff_metadata":
        return {"file_path": state.get("input_file") or _last_raster_path(state), "compare_with": state.get("compare_with"), "calculate_statistics": state.get("calculate_statistics", True), "calculate_histogram": state.get("calculate_histogram", True)}
    if tool == "analyze_temporal_change":
        before, after = _tool7_paths(state)
        return {"raster_before_path": before, "raster_after_path": after, "band_selection": state.get("band_selection", 1), "threshold_type": state.get("threshold_type", "absolute"), "threshold_value": state.get("threshold_value", 0.15), "relative_change_threshold_percent": state.get("relative_change_threshold_percent"), "mask_encoding": state.get("mask_encoding", "bipolar_3class"), "output_dir": state.get("analysis_output_dir"), "generate_difference_raster": state.get("generate_difference_raster", True), "generate_change_mask": state.get("generate_change_mask", True)}
    if tool == "analyze_spatial_landcover_terrain":
        return {"lulc_raster_path": state.get("lulc_raster_path"), "dem_raster_path": state.get("dem_raster_path"), "zone_mask_path": state.get("zone_mask_path") or state.get("last_change_mask_path"), "class_legend": state.get("class_legend"), "zone_legend": state.get("zone_legend"), "calculate_fragmentation": state.get("calculate_fragmentation", True), "output_dir": state.get("analysis_output_dir")}
    raise ValueError(f"Unknown tool: {tool}")

def location_ready_for_tool(tool: str, state: SatQueryState) -> bool:
    loc = TOOL_SPEC[tool]["location"]
    if loc in {"file", "files"}:
        if loc == "file": return bool(state.get("input_file") or _last_raster_path(state))
        before, after = _tool7_paths(state); return bool(before and after)
    if loc == "lulc": return bool(state.get("lulc_raster_path"))
    if loc == "weather": return bool(state.get("bbox") or (state.get("latitude") is not None and state.get("longitude") is not None))
    return bool(state.get("bbox"))

def enforce_call_tool_location(plan: Plan, state: SatQueryState) -> Plan:
    if plan.get("action") != "call_tool" or not plan.get("tool"):
        return plan
    tool = plan["tool"]
    if tool not in TOOL_SPEC:
        return {"action": "respond_error", "tool": None, "args": {}, "reason": f"Unknown tool '{tool}'."}
    if not location_ready_for_tool(tool, state):
        return {"action": "clarify", "tool": None, "args": {}, "reason": _missing_input_reason(tool)}
    plan["args"] = trusted_args_for_tool(tool, state)
    return plan

def _missing_input_reason(tool: str) -> str:
    loc = TOOL_SPEC[tool]["location"]
    return {"bbox": f"{tool} requires bbox [min_lon, min_lat, max_lon, max_lat].", "weather": f"{tool} requires bbox or latitude and longitude.", "file": f"{tool} requires a GeoTIFF input file.", "files": f"{tool} requires raster_before_path and raster_after_path.", "lulc": f"{tool} requires lulc_raster_path."}[loc]

def format_tool_success(tool: str, result: dict[str, Any]) -> str:
    if tool == "compute_vegetation_indices":
        data = result.get("data", {})
        return f"Vegetation indices computed successfully. Output: {data.get('file_path') or result.get('file_path', 'generated GeoTIFF')}"
    if tool == "inspect_geotiff_metadata":
        raster = result.get("raster", {})
        quality = result.get("quality", {})
        return f"GeoTIFF inspection complete: {raster.get('width')}x{raster.get('height')}, {raster.get('band_count')} bands, CRS={result.get('spatial', {}).get('crs')}, ML-ready={quality.get('is_valid_for_ml')}."
    if tool == "analyze_temporal_change":
        summary = result.get("change_summary", {})
        return f"Temporal change analysis complete. Loss={summary.get('significant_decrease', {}).get('area_km2')} km², Gain={summary.get('significant_increase', {}).get('area_km2')} km²."
    if tool == "analyze_spatial_landcover_terrain":
        dom = result.get("dominant_landcover", {})
        return f"Spatial land-cover/terrain analysis complete. Dominant land cover: {dom.get('name')} ({dom.get('percentage')}% of valid AOI)."
    return f"{tool} completed successfully."
