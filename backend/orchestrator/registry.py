"""Single table of fetch-tool specs (Week-1: Tools 1–4).

The planner chooses a tool name. This module owns args, location rules,
capability keywords, and success messages. LLM output never invents
coordinates, dates, or extra parameters.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

from backend.config.settings import settings
from backend.orchestrator.state import Plan, SatQueryState

TOOL_OPTICAL = "fetch_optical_imagery"
TOOL_MULTI = "fetch_multispectral_imagery"
TOOL_SAR = "fetch_sar_imagery"
TOOL_WEATHER = "fetch_weather_environment"

ArgsBuilder = Callable[[SatQueryState], dict[str, Any]]
ResponseFormatter = Callable[[dict[str, Any], str], str]


class ToolSpec(TypedDict):
    name: str
    description: str
    requires: list[str]
    keywords: tuple[str, ...]
    args_builder: ArgsBuilder
    response_formatter: ResponseFormatter


def has_bbox(state: SatQueryState) -> bool:
    bbox = state.get("bbox")
    return isinstance(bbox, list) and len(bbox) == 4


def has_weather_location(state: SatQueryState) -> bool:
    if has_bbox(state):
        return True
    return state.get("latitude") is not None and state.get("longitude") is not None


def _common_imagery_args(state: SatQueryState) -> dict[str, Any]:
    return {
        "bbox": state.get("bbox"),
        "start_date": state.get("start_date") or settings.default_start_date,
        "end_date": state.get("end_date") or settings.default_end_date,
        "max_cloud_cover": state.get("max_cloud_cover") or settings.default_max_cloud_cover,
        "width": state.get("width") or settings.default_width,
        "height": state.get("height") or settings.default_height,
        "crs": settings.default_crs,
    }


def _optical_args(state: SatQueryState) -> dict[str, Any]:
    return _common_imagery_args(state)


def _multispectral_args(state: SatQueryState) -> dict[str, Any]:
    args = _common_imagery_args(state)
    args["bands"] = state.get("bands") or ["B02", "B03", "B04", "B08"]
    return args


def _sar_args(state: SatQueryState) -> dict[str, Any]:
    return {
        "bbox": state.get("bbox"),
        "start_date": state.get("start_date") or settings.default_start_date,
        "end_date": state.get("end_date") or settings.default_end_date,
        "polarization": state.get("polarization") or ["VV", "VH"],
        "orbit_direction": state.get("orbit_direction") or "BOTH",
        "scene_selection": state.get("scene_selection") or "most_recent",
        "width": state.get("width") or settings.default_width,
        "height": state.get("height") or settings.default_height,
        "crs": settings.default_crs,
    }


def _weather_args(state: SatQueryState) -> dict[str, Any]:
    args: dict[str, Any] = {
        "start_date": state.get("start_date") or settings.default_start_date,
        "end_date": state.get("end_date") or settings.default_end_date,
        "rolling_windows": [7, 30],
    }
    if has_bbox(state):
        args["bbox"] = state.get("bbox")
    else:
        args["latitude"] = state.get("latitude")
        args["longitude"] = state.get("longitude")
    return args


def format_imagery_success(result: dict[str, Any], tool_name: str) -> str:
    data = result.get("data") or {}
    source = result.get("source") or {}
    quality = result.get("quality") or {}
    collection = source.get("collection") or tool_name
    scene_id = source.get("scene_id")
    parts: list[str] = []
    parts.append(
        f"Fetched {collection} scene {scene_id}."
        if scene_id
        else f"{tool_name} completed successfully."
    )
    if quality.get("cloud_cover") is not None:
        parts.append(f"Cloud cover {quality['cloud_cover']}%.")
    if data.get("file_path"):
        parts.append(f"{data.get('format', 'file')} saved at {data['file_path']}.")
    return " ".join(parts)


def format_weather_success(result: dict[str, Any], tool_name: str) -> str:
    metrics = result.get("observed_metrics") or {}
    parts = ["Weather environment fetch completed."]
    if metrics.get("temperature_2m_mean_c") is not None:
        parts.append(f"Mean temperature {metrics['temperature_2m_mean_c']} °C.")
    if metrics.get("precipitation_sum_mm") is not None:
        parts.append(f"Precipitation sum {metrics['precipitation_sum_mm']} mm.")
    return " ".join(parts)


TOOL_SPEC: dict[str, ToolSpec] = {
    TOOL_SAR: {
        "name": TOOL_SAR,
        "description": (
            "Download Sentinel-1 GRD SAR imagery (flood, radar, backscatter). "
            "Requires: bbox, start_date, end_date."
        ),
        "requires": ["bbox"],
        "keywords": (
            "sar", "radar", "sentinel-1", "sentinel1", "backscatter",
            "flood", "floods", "flooded", "flooding", "inundat",
        ),
        "args_builder": _sar_args,
        "response_formatter": format_imagery_success,
    },
    TOOL_WEATHER: {
        "name": TOOL_WEATHER,
        "description": (
            "Fetch Open-Meteo / ERA5 weather and environment context. "
            "Requires: start_date, end_date, and bbox or lat/lon."
        ),
        "requires": ["bbox_or_latlon"],
        "keywords": (
            "weather", "rain", "rainfall", "precipitation", "temperature",
            "era5", "climate", "humidity", "drought", "soil moisture",
            "environment", "meteorolog",
        ),
        "args_builder": _weather_args,
        "response_formatter": format_weather_success,
    },
    TOOL_MULTI: {
        "name": TOOL_MULTI,
        "description": (
            "Download Sentinel-2 L2A multi-band surface reflectance for "
            "vegetation / NDVI / crop health. Requires: bbox, start_date, end_date."
        ),
        "requires": ["bbox"],
        "keywords": (
            "multispectral", "surface reflectance", "ndvi", "band", "bands",
            "spectral", "vegetation", "crop", "crops", "canopy", "vigor",
            "chlorophyll", "crop health",
        ),
        "args_builder": _multispectral_args,
        "response_formatter": format_imagery_success,
    },
    TOOL_OPTICAL: {
        "name": TOOL_OPTICAL,
        "description": (
            "Download Sentinel-2 L2A true-color RGB GeoTIFF. "
            "Requires: bbox, start_date, end_date."
        ),
        "requires": ["bbox"],
        "keywords": (
            "optical", "imagery", "image", "sentinel-2", "sentinel2", "rgb",
            "true-color", "true color", "geotiff", "satellite", "fetch",
            "download", "show",
        ),
        "args_builder": _optical_args,
        "response_formatter": format_imagery_success,
    },
}

# Keyword / LLM disambiguation: SAR/flood > weather > vegetation > optical RGB.
PLANNER_PRIORITY: tuple[str, ...] = (TOOL_SAR, TOOL_WEATHER, TOOL_MULTI, TOOL_OPTICAL)

TOOL_REGISTRY: dict[str, str] = {
    name: spec["description"] for name, spec in TOOL_SPEC.items()
}

_CLARIFY_REASON: dict[str, str] = {
    TOOL_OPTICAL: "Optical fetch requested but bbox is missing.",
    TOOL_MULTI: "Multispectral fetch requested but bbox is missing.",
    TOOL_SAR: "SAR fetch requested but bbox is missing.",
    TOOL_WEATHER: "Weather requested but bbox or lat/lon is missing.",
}


def default_args_for_tool(tool: str | None, state: SatQueryState) -> dict[str, Any]:
    if not tool:
        return {}
    spec = TOOL_SPEC.get(tool)
    if spec is None:
        return {}
    return spec["args_builder"](state)


def reconcile_sar_args(args: dict[str, Any], state: SatQueryState) -> dict[str, Any]:
    """HTTP body and query text beat any LLM guess for orbit / polarization."""
    query = (state.get("query") or "").lower()
    if state.get("orbit_direction"):
        args["orbit_direction"] = state["orbit_direction"]
    elif "ascending" in query:
        args["orbit_direction"] = "ASCENDING"
    elif "descending" in query:
        args["orbit_direction"] = "DESCENDING"
    else:
        args["orbit_direction"] = "BOTH"
    if state.get("polarization"):
        args["polarization"] = state["polarization"]
    elif "polarization" not in args:
        args["polarization"] = ["VV", "VH"]
    return args


def trusted_args_for_tool(tool: str | None, state: SatQueryState) -> dict[str, Any]:
    """Build tool args only from HTTP/state defaults — never from LLM JSON."""
    args = default_args_for_tool(tool, state)
    if tool == TOOL_SAR:
        args = reconcile_sar_args(args, state)
    return args


def match_tool_from_query(query: str) -> tuple[str | None, str]:
    """Return (tool, reason) using PLANNER_PRIORITY keyword scan."""
    lowered = query.lower()
    for name in PLANNER_PRIORITY:
        spec = TOOL_SPEC[name]
        if any(kw in lowered for kw in spec["keywords"]):
            return name, f"Query matched {name} capability keywords."
    return None, ""


def location_ready_for_tool(tool: str | None, state: SatQueryState) -> bool:
    """True when the tool's location precondition is satisfied on state."""
    if not tool:
        return False
    spec = TOOL_SPEC.get(tool)
    if spec is None:
        return True
    requires = spec["requires"]
    if "bbox" in requires:
        return has_bbox(state)
    if "bbox_or_latlon" in requires:
        return has_weather_location(state)
    return True


def clarify_missing_location(tool: str | None) -> Plan:
    reason = _CLARIFY_REASON.get(
        tool or "",
        f"{tool or 'Tool'} requested but required location is missing.",
    )
    return {"action": "clarify", "tool": None, "args": {}, "reason": reason}


def enforce_call_tool_location(plan: Plan, state: SatQueryState) -> Plan:
    """Downgrade call_tool → clarify when the chosen tool lacks location on state.

    Shared by the keyword planner and the LLM planner so a hallucinated
    call_tool cannot skip the clarify UX.
    """
    if plan.get("action") != "call_tool":
        return plan
    tool = plan.get("tool")
    if tool and tool not in TOOL_SPEC:
        return {
            "action": "respond_error",
            "tool": None,
            "args": {},
            "reason": f"Unknown tool '{tool}'.",
        }
    if location_ready_for_tool(tool, state):
        return plan
    return clarify_missing_location(tool)


def format_tool_success(tool_name: str, result: dict[str, Any]) -> str:
    spec = TOOL_SPEC.get(tool_name)
    formatter = spec["response_formatter"] if spec else format_imagery_success
    return formatter(result, tool_name)
