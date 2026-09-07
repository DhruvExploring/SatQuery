"""Handshake agendas: classify intent once, then step tools without re-keywording."""

from __future__ import annotations

from typing import Any, Callable, Literal, TypedDict

from backend.config.settings import settings
from backend.orchestrator.registry import (
    _missing_input_reason,
    location_ready_for_tool,
    match_tool_from_query,
    trusted_args_for_tool,
)
from backend.orchestrator.state import Plan, SatQueryState

MAX_HANDSHAKE_HOPS = 10

Intent = Literal[
    "mission_wildfire",
    "mission_flood",
    "mission_drought",
    "chain_temporal",
    "chain_indices",
    "single_tool",
]


class AgendaStep(TypedDict, total=False):
    tool: str
    role: str
    date_window: str
    reason: str


SingleToolPlanner = Callable[[SatQueryState], Plan]

_FETCH_OPTICAL = {"fetch_optical_imagery", "fetch_satellite_imagery"}
_FETCH_SAR = {"fetch_sar_imagery", "fetch_sar"}
_FETCH_MULTI = {"fetch_multispectral_imagery"}
_FETCH_ANY = _FETCH_OPTICAL | _FETCH_SAR | _FETCH_MULTI


def classify_intent(query: str) -> Intent:
    q = (query or "").lower().strip()
    if _has_any(
        q,
        (
            "wildfire",
            "wild fire",
            "burn severity",
            "burn scar",
            "fire scar",
            "forest fire",
            "pre-fire",
            "post-fire",
        ),
    ):
        return "mission_wildfire"
    if _has_any(q, ("flood", "inundation", "monsoon flood")):
        return "mission_flood"
    if _has_any(
        q,
        (
            "drought",
            "canopy stress",
            "agricultural drought",
            "crop water stress",
        ),
    ):
        return "mission_drought"
    if _has_any(
        q,
        (
            "deforestation",
            "change detection",
            "change between",
            "before and after",
            "vegetation loss",
            "vegetation gain",
            "temporal change",
        ),
    ):
        return "chain_temporal"
    if _wants_indices(q):
        return "chain_indices"
    return "single_tool"


def build_agenda(state: SatQueryState) -> tuple[Intent, list[AgendaStep], str | None]:
    """Return (intent, steps, clarify_reason). clarify_reason set → plan should clarify."""
    intent = classify_intent(state.get("query") or "")
    if intent == "mission_wildfire":
        steps, clarify = _mission_pair_agenda(
            state,
            fetch_tool="fetch_multispectral_imagery",
            workflow_tool="workflow_wildfire_burn_severity",
            require_lulc=True,
        )
        return intent, steps, clarify
    if intent == "mission_flood":
        steps, clarify = _flood_agenda(state)
        return intent, steps, clarify
    if intent == "mission_drought":
        steps, clarify = _drought_agenda(state)
        return intent, steps, clarify
    if intent == "chain_temporal":
        steps, clarify = _temporal_agenda(state)
        return intent, steps, clarify
    if intent == "chain_indices":
        steps, clarify = _indices_agenda(state)
        return intent, steps, clarify
    return intent, *_single_tool_agenda(state)


def build_plan_update(
    state: SatQueryState,
    single_tool_planner: SingleToolPlanner,
) -> dict[str, Any]:
    """First hop builds the agenda; later hops consume agenda[agenda_index]."""
    if state.get("errors"):
        return {
            "plan": {
                "action": "respond_error",
                "tool": None,
                "args": {},
                "reason": "Input validation failed; skip tool selection.",
            },
            "handshake_complete": True,
        }

    hops = state.get("handshake_hops") or 0
    if hops >= MAX_HANDSHAKE_HOPS:
        return {
            "plan": {
                "action": "respond_error",
                "tool": None,
                "args": {},
                "reason": "Handshake exceeded max hops.",
            },
            "handshake_complete": True,
            "errors": ["Handshake exceeded max hops."],
        }

    agenda = list(state.get("agenda") or [])
    if agenda:
        idx = int(state.get("agenda_index") or 0)
        if state.get("handshake_complete") or idx >= len(agenda):
            return {
                "plan": {
                    "action": "chat",
                    "tool": None,
                    "args": {},
                    "reason": "Handshake already complete.",
                },
                "handshake_complete": True,
            }
        return {"plan": plan_agenda_step(state, agenda[idx])}

    intent, steps, clarify = build_agenda(state)
    if intent == "single_tool":
        planned = single_tool_planner(state)
        wrapped: list[AgendaStep] = []
        if planned.get("action") == "call_tool" and planned.get("tool"):
            wrapped = [{
                "tool": planned["tool"],
                "role": "single",
                "reason": planned.get("reason") or "",
            }]
        return {
            "intent": intent,
            "agenda": wrapped,
            "agenda_index": 0,
            "handshake_complete": planned.get("action") != "call_tool",
            "plan": planned,
        }

    if clarify:
        return {
            "intent": intent,
            "agenda": [],
            "agenda_index": 0,
            "handshake_complete": True,
            "plan": {
                "action": "clarify",
                "tool": None,
                "args": {},
                "reason": clarify,
            },
        }

    if not steps:
        return {
            "intent": intent,
            "agenda": [],
            "agenda_index": 0,
            "handshake_complete": True,
            "plan": {
                "action": "chat",
                "tool": None,
                "args": {},
                "reason": "Query does not match a registered remote-sensing tool.",
            },
        }

    return {
        "intent": intent,
        "agenda": steps,
        "agenda_index": 0,
        "handshake_complete": False,
        "plan": plan_agenda_step(state, steps[0]),
    }


def plan_agenda_step(state: SatQueryState, step: AgendaStep) -> Plan:
    tool = step["tool"]
    overlay: dict[str, Any] = dict(state)
    if step.get("date_window") == "t2":
        overlay["start_date"] = state.get("post_start_date")
        overlay["end_date"] = state.get("post_end_date")
    if tool == "compute_vegetation_indices":
        overlay["input_file"] = _indices_source_path(state, step.get("role"))
    if tool == "inspect_geotiff_metadata":
        overlay["input_file"] = (
            state.get("index_after_path") or state.get("raster_after_path")
        )
        overlay["compare_with"] = (
            state.get("index_before_path") or state.get("raster_before_path")
        )
    if tool == "analyze_temporal_change":
        overlay["raster_before_path"] = (
            state.get("index_before_path") or state.get("raster_before_path")
        )
        overlay["raster_after_path"] = (
            state.get("index_after_path") or state.get("raster_after_path")
        )
    overlay["relative_change_threshold_percent"] = _relative_percent_for_tool(
        tool,
        state,
    )

    if not location_ready_for_tool(tool, overlay):  # type: ignore[arg-type]
        return {
            "action": "clarify",
            "tool": None,
            "args": {},
            "reason": _missing_input_reason(tool),
        }
    args = trusted_args_for_tool(tool, overlay)  # type: ignore[arg-type]
    if step.get("date_window") == "t2":
        args["start_date"] = overlay.get("start_date") or settings.default_start_date
        args["end_date"] = overlay.get("end_date") or settings.default_end_date
    return {
        "action": "call_tool",
        "tool": tool,
        "args": args,
        "reason": step.get("reason") or f"Handshake step role={step.get('role')}",
    }


def apply_advance(state: SatQueryState) -> dict[str, Any]:
    """Record artifacts, gate Tool 6, optionally append Tool 1→3, then step the agenda."""
    hops = int(state.get("handshake_hops") or 0) + 1
    idx = int(state.get("agenda_index") or 0)
    agenda = list(state.get("agenda") or [])
    step = agenda[idx] if idx < len(agenda) else {}
    results = state.get("tool_results") or []
    latest = results[-1] if results else None

    update: dict[str, Any] = {"handshake_hops": hops}

    if not latest:
        update["handshake_complete"] = True
        return update

    result = latest.get("result") or {}
    tool_name = latest.get("tool") or step.get("tool") or ""
    role = step.get("role") or ""

    if result.get("status") != "success":
        update["handshake_complete"] = True
        return update

    path = _result_file_path(result)
    if tool_name in _FETCH_ANY and path:
        if role == "t1":
            update["raster_before_path"] = path
        elif role == "t2":
            update["raster_after_path"] = path
        update["input_file"] = path

    if tool_name == "compute_vegetation_indices" and path:
        update["input_file"] = path
        if role == "t1":
            update["index_before_path"] = path
        elif role == "t2":
            update["index_after_path"] = path

    if tool_name == "analyze_temporal_change":
        products = result.get("generated_products") or {}
        if products.get("change_mask_path"):
            update["last_change_mask_path"] = products["change_mask_path"]

    if tool_name == "inspect_geotiff_metadata":
        ready = (result.get("compatibility") or {}).get(
            "pixelwise_operation_ready",
            True,
        )
        if ready is False:
            update["errors"] = [
                "Tool 6 compatibility.pixelwise_operation_ready is false; "
                "skipping temporal change."
            ]
            update["handshake_complete"] = True
            update["agenda_index"] = idx + 1
            return update

    if tool_name in _FETCH_OPTICAL and optical_flags_recommend_sar(result):
        if not any(item.get("tool") in _FETCH_SAR for item in agenda):
            agenda.append({
                "tool": "fetch_sar_imagery",
                "role": "sar_fallback",
                "date_window": "t1",
                "reason": "Optical quality flags recommended SAR fallback",
            })
            update["agenda"] = agenda

    new_index = idx + 1
    update["agenda_index"] = new_index
    updated_agenda = update.get("agenda", agenda)
    if new_index >= len(updated_agenda):
        update["handshake_complete"] = True
    else:
        update["handshake_complete"] = False
    return update


def looks_like_optical_rgb(path: str | None) -> bool:
    if not path:
        return False
    lowered = path.replace("\\", "/").lower()
    return "optical" in lowered and "multispectral" not in lowered


def optical_flags_recommend_sar(result: dict[str, Any]) -> bool:
    flags = result.get("flags") or {}
    return bool(flags.get("sar_recommended") or flags.get("optical_quality_poor"))


def _has_any(query: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in query for phrase in phrases)


def _wants_indices(query: str) -> bool:
    tokens = (
        "ndvi",
        "evi",
        "savi",
        "gndvi",
        "ndre",
        "ndmi",
        "ndwi",
        "msavi",
        "nbr",
        "vegetation index",
        "vegetation indices",
    )
    return _has_any(query, tokens)


def _has_pair(state: SatQueryState) -> bool:
    return bool(state.get("raster_before_path") and state.get("raster_after_path"))


def _has_post_window(state: SatQueryState) -> bool:
    return bool(state.get("post_start_date") and state.get("post_end_date"))


def _has_weather_location(state: SatQueryState) -> bool:
    return bool(
        state.get("bbox")
        or (
            state.get("latitude") is not None
            and state.get("longitude") is not None
        )
    )


def _pair_missing_reason() -> str:
    return (
        "This analysis needs two scenes. Provide raster_before_path and "
        "raster_after_path, or bbox plus post_start_date and post_end_date "
        "(T1 uses start_date/end_date)."
    )


def _pair_fetch_or_clarify(
    state: SatQueryState,
    fetch_tool: str,
    steps: list[AgendaStep],
) -> str | None:
    if _has_pair(state):
        return None
    if state.get("bbox") and _has_post_window(state):
        steps.append({
            "tool": fetch_tool,
            "role": "t1",
            "date_window": "t1",
            "reason": "Fetch T1 scene",
        })
        steps.append({
            "tool": fetch_tool,
            "role": "t2",
            "date_window": "t2",
            "reason": "Fetch T2 scene",
        })
        return None
    return _pair_missing_reason()


def _mission_pair_agenda(
    state: SatQueryState,
    fetch_tool: str,
    workflow_tool: str,
    require_lulc: bool,
) -> tuple[list[AgendaStep], str | None]:
    steps: list[AgendaStep] = []
    clarify = _pair_fetch_or_clarify(state, fetch_tool, steps)
    if clarify:
        return [], clarify
    if require_lulc and not state.get("lulc_raster_path"):
        return [], "This pipeline requires lulc_raster_path (e.g. ESA WorldCover)."
    steps.append({
        "tool": workflow_tool,
        "role": "mission",
        "reason": f"Run {workflow_tool}",
    })
    return steps, None


def _flood_agenda(state: SatQueryState) -> tuple[list[AgendaStep], str | None]:
    steps, clarify = _mission_pair_agenda(
        state,
        fetch_tool="fetch_sar_imagery",
        workflow_tool="workflow_flood_inundation_impact",
        require_lulc=True,
    )
    return steps, clarify


def _drought_agenda(state: SatQueryState) -> tuple[list[AgendaStep], str | None]:
    if not _has_weather_location(state):
        return [], "Drought analysis requires bbox or latitude and longitude."
    input_file = state.get("input_file")
    if looks_like_optical_rgb(input_file):
        input_file = None
    steps: list[AgendaStep] = []
    if not input_file:
        if not state.get("bbox"):
            return [], (
                "compute_vegetation_indices requires a GeoTIFF input file "
                "or bbox to fetch one."
            )
        steps.append({
            "tool": "fetch_multispectral_imagery",
            "role": "t1",
            "date_window": "t1",
            "reason": "Fetch multispectral for drought indices",
        })
    steps.append({
        "tool": "workflow_agricultural_drought_canopy_stress",
        "role": "mission",
        "reason": "Pipeline C drought workflow",
    })
    return steps, None


def _temporal_agenda(state: SatQueryState) -> tuple[list[AgendaStep], str | None]:
    steps: list[AgendaStep] = []
    if _has_pair(state):
        steps.extend(_qa_change_landcover_steps(state))
        return steps, None
    clarify = _pair_fetch_or_clarify(state, "fetch_multispectral_imagery", steps)
    if clarify:
        return [], clarify
    steps.append({
        "tool": "compute_vegetation_indices",
        "role": "t1",
        "reason": "Indices for T1",
    })
    steps.append({
        "tool": "compute_vegetation_indices",
        "role": "t2",
        "reason": "Indices for T2",
    })
    steps.extend(_qa_change_landcover_steps(state))
    return steps, None


def _qa_change_landcover_steps(state: SatQueryState) -> list[AgendaStep]:
    steps: list[AgendaStep] = [
        {
            "tool": "inspect_geotiff_metadata",
            "role": "qa",
            "reason": "Pre-flight grid alignment",
        },
        {
            "tool": "analyze_temporal_change",
            "role": "change",
            "reason": "T2 minus T1 change mask",
        },
    ]
    if state.get("lulc_raster_path"):
        steps.append({
            "tool": "analyze_spatial_landcover_terrain",
            "role": "zonal",
            "reason": "Tool 7 to Tool 8 handshake",
        })
    return steps


def _indices_agenda(state: SatQueryState) -> tuple[list[AgendaStep], str | None]:
    input_file = state.get("input_file")
    if looks_like_optical_rgb(input_file):
        input_file = None
    if input_file:
        return [{
            "tool": "compute_vegetation_indices",
            "role": "indices",
            "reason": "Compute vegetation indices",
        }], None
    if state.get("bbox"):
        return [
            {
                "tool": "fetch_multispectral_imagery",
                "role": "t1",
                "date_window": "t1",
                "reason": "Fetch 8-band SR for indices",
            },
            {
                "tool": "compute_vegetation_indices",
                "role": "indices",
                "reason": "Compute vegetation indices",
            },
        ], None
    return [], "compute_vegetation_indices requires a GeoTIFF input file."


def _single_tool_agenda(state: SatQueryState) -> tuple[list[AgendaStep], str | None]:
    tool, reason = match_tool_from_query(state.get("query") or "")
    if not tool:
        return [], None
    return [{"tool": tool, "role": "single", "reason": reason}], None


def _indices_source_path(state: SatQueryState, role: str | None) -> str | None:
    if role == "t1":
        return state.get("raster_before_path") or state.get("input_file")
    if role == "t2":
        return state.get("raster_after_path")
    path = (
        state.get("input_file")
        or state.get("raster_after_path")
        or state.get("raster_before_path")
    )
    if looks_like_optical_rgb(path):
        return None
    return path


def _relative_percent_for_tool(tool: str, state: SatQueryState) -> float | None:
    if tool in {
        "fetch_sar_imagery",
        "fetch_sar",
        "workflow_flood_inundation_impact",
    }:
        return None
    if tool == "analyze_temporal_change":
        joined = (
            (state.get("raster_before_path") or "")
            + (state.get("raster_after_path") or "")
            + (state.get("index_before_path") or "")
            + (state.get("index_after_path") or "")
        ).lower()
        if "sar" in joined:
            return None
    return state.get("relative_change_threshold_percent")


def _result_file_path(result: dict[str, Any]) -> str | None:
    data = result.get("data")
    if isinstance(data, dict) and data.get("file_path"):
        return data["file_path"]
    file_info = result.get("file")
    if isinstance(file_info, dict) and file_info.get("file_path"):
        return file_info["file_path"]
    return result.get("file_path")
