"""LangGraph state shared by SatQuery nodes."""

from __future__ import annotations

from datetime import datetime, timezone
from operator import add
from typing import Annotated, Any, Literal, TypedDict
from typing_extensions import NotRequired


PlanAction = Literal["call_tool", "clarify", "chat", "respond_error"]


class Plan(TypedDict):
    action: PlanAction
    tool: str | None
    args: dict[str, Any]
    reason: str


class ToolResult(TypedDict):
    tool: str
    result: dict[str, Any]
    duration_ms: NotRequired[float]
    timestamp: NotRequired[str]


class ExecutionTraceEntry(TypedDict):
    node: str
    timestamp: str
    summary: str


class SatQueryState(TypedDict):
    query: str

    # Identity for optional LangMem namespaces.
    user_id: NotRequired[str | None]

    bbox: NotRequired[list[float] | None]
    latitude: NotRequired[float | None]
    longitude: NotRequired[float | None]

    start_date: NotRequired[str | None]
    end_date: NotRequired[str | None]
    post_start_date: NotRequired[str | None]
    post_end_date: NotRequired[str | None]
    modality: NotRequired[str]
    bands: NotRequired[list[str] | None]
    max_cloud_cover: NotRequired[float]
    width: NotRequired[int]
    height: NotRequired[int]
    polarization: NotRequired[list[str] | None]
    orbit_direction: NotRequired[str | None]
    scene_selection: NotRequired[str | None]

    # Tool 5-8 analytical inputs
    input_file: NotRequired[str | None]
    indices: NotRequired[list[str] | None]
    band_mapping: NotRequired[dict[str, str] | None]
    calculate_heuristic_classification: NotRequired[bool]
    compare_with: NotRequired[str | None]
    calculate_statistics: NotRequired[bool]
    calculate_histogram: NotRequired[bool]
    raster_before_path: NotRequired[str | None]
    raster_after_path: NotRequired[str | None]
    band_selection: NotRequired[int | str]
    threshold_type: NotRequired[str]
    threshold_value: NotRequired[float]
    relative_change_threshold_percent: NotRequired[float | None]
    mask_encoding: NotRequired[str]
    analysis_output_dir: NotRequired[str | None]
    generate_difference_raster: NotRequired[bool]
    generate_change_mask: NotRequired[bool]
    lulc_raster_path: NotRequired[str | None]
    dem_raster_path: NotRequired[str | None]
    zone_mask_path: NotRequired[str | None]
    last_change_mask_path: NotRequired[str | None]
    index_before_path: NotRequired[str | None]
    index_after_path: NotRequired[str | None]
    intent: NotRequired[str | None]
    agenda: NotRequired[list[dict[str, Any]]]
    agenda_index: NotRequired[int]
    handshake_complete: NotRequired[bool]
    handshake_hops: NotRequired[int]
    class_legend: NotRequired[dict[int, str] | None]
    zone_legend: NotRequired[dict[int, str] | None]
    calculate_fragmentation: NotRequired[bool]

    plan: NotRequired[Plan | None]

    tool_results: Annotated[list[ToolResult], add]
    errors: Annotated[list[str], add]
    execution_trace: Annotated[list[ExecutionTraceEntry], add]

    final_answer: NotRequired[str | None]
    status: NotRequired[str]


def trace_entry(node: str, summary: str) -> ExecutionTraceEntry:
    """Create a trace entry without exposing secrets."""
    return {
        "node": node,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
    }


def empty_state(query: str, **overrides: Any) -> SatQueryState:
    state: SatQueryState = {
        "query": query,
        "user_id": None,
        "bbox": None,
        "latitude": None,
        "longitude": None,
        "start_date": None,
        "end_date": None,
        "post_start_date": None,
        "post_end_date": None,
        "modality": "optical",
        "bands": None,
        "max_cloud_cover": 30.0,
        "width": 512,
        "height": 512,
        "polarization": None,
        "orbit_direction": None,
        "scene_selection": None,
        "input_file": None,
        "indices": None,
        "band_mapping": None,
        "calculate_heuristic_classification": True,
        "compare_with": None,
        "calculate_statistics": True,
        "calculate_histogram": True,
        "raster_before_path": None,
        "raster_after_path": None,
        "band_selection": 1,
        "threshold_type": "absolute",
        "threshold_value": 0.15,
        "relative_change_threshold_percent": None,
        "mask_encoding": "bipolar_3class",
        "analysis_output_dir": None,
        "generate_difference_raster": True,
        "generate_change_mask": True,
        "lulc_raster_path": None,
        "dem_raster_path": None,
        "zone_mask_path": None,
        "last_change_mask_path": None,
        "index_before_path": None,
        "index_after_path": None,
        "intent": None,
        "agenda": [],
        "agenda_index": 0,
        "handshake_complete": False,
        "handshake_hops": 0,
        "class_legend": None,
        "zone_legend": None,
        "calculate_fragmentation": True,
        "plan": None,
        "tool_results": [],
        "errors": [],
        "execution_trace": [],
        "final_answer": None,
        "status": "pending",
    }
    state.update(overrides)
    return state
