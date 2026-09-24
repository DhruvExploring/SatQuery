"""LangGraph state shared by SatQuery nodes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from operator import add
from typing import Annotated, Any, Literal, TypedDict
from typing_extensions import NotRequired

_graph_logger = logging.getLogger("satquery.graph")


PlanAction = Literal["call_tool", "clarify", "chat", "respond_error", "finish"]


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
    # LLM-extracted semantic fields -- the planner reads the raw query and
    # emits these directly (see llm.py::_PLAN_SCHEMA); tools never parse
    # natural language themselves (see registry.py::trusted_args_for_tool's
    # TOOL_GEOCODE_FORWARD/TOOL_SCENE_IDENTITY branches, and
    # Tool_10_spatial_geocoding_poi/spatial_geocoding_poi.py). Only ever set
    # transiently for the single hop that needs them (llm.py::_llm_plan),
    # never persisted/reused across hops.
    place_name: NotRequired[str | None]
    landmark_names: NotRequired[list[str] | None]
    # A user-marked sub-region of input_file, in WGS84 [min_lon, min_lat,
    # max_lon, max_lat] -- distinct from `bbox` (the AOI for fetch tools /
    # an uploaded image's own full extent). See TOOL_DESCRIBE_REGION.
    region_bbox: NotRequired[list[float] | None]
    # An elongated/curved region_bbox's own tighter path -- an ordered list
    # of {"latitude", "longitude"} vertices, set only when mark_region_in_image
    # returned a polygon (not just a bbox) for the marked feature. Lets
    # describe_marked_region mask the crop to the actual path instead of its
    # whole bounding rectangle. See registry.py::TOOL_DESCRIBE_REGION.
    region_polygon: NotRequired[list[dict[str, float]] | None]
    # The marked region's own anchor point for weather/reverse-geocode
    # lookups: a polygon's path centroid when region_polygon is set (far
    # more accurate for an elongated feature than region_bbox's own
    # midpoint, which can land nowhere near the actual feature), otherwise
    # region_bbox's plain midpoint. See registry.py::_region_center.
    region_centroid: NotRequired[dict[str, float] | None]

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
    threshold_value: NotRequired[float | None]
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
    tool_hops: NotRequired[int]
    class_legend: NotRequired[dict[int, str] | None]
    zone_legend: NotRequired[dict[int, str] | None]
    calculate_fragmentation: NotRequired[bool]

    # Upload-time knowledge base (bands/lat/long/place_name) and the VLM's
    # first-pass description grounded in it -- see ingest_graph.py.
    knowledge_base: NotRequired[dict[str, Any] | None]
    initial_description: NotRequired[str | None]

    # Tool 9-11 inputs/outputs
    poi_categories: NotRequired[list[str] | None]
    # Landmarks resolved by geocode_place_to_coordinates/resolve_scene_identity
    # (name/latitude/longitude), fed to deterministic_affine_markup's `features`.
    geocoded_landmarks: NotRequired[list[dict[str, Any]]]

    plan: NotRequired[Plan | None]

    tool_results: Annotated[list[ToolResult], add]
    errors: Annotated[list[str], add]
    execution_trace: Annotated[list[ExecutionTraceEntry], add]

    final_answer: NotRequired[str | None]
    status: NotRequired[str]


def trace_entry(node: str, summary: str) -> ExecutionTraceEntry:
    """Create a trace entry without exposing secrets.

    Every node in every graph (query graph, ingest graph, tool_loop
    subgraph) builds its execution_trace update by calling this, so logging
    it here -- once, at the single point every step already passes through
    -- guarantees the console shows every graph step in real time, in the
    same order and with the same content the frontend's StepTimeline
    receives over SSE (run_query_stream yields one `step` event per
    execution_trace entry as each node completes). No node can add a step
    that's visible in one place but not the other.
    """
    _graph_logger.info("[STEP] %s: %s", node, summary)
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
        "place_name": None,
        "landmark_names": None,
        "region_bbox": None,
        "region_polygon": None,
        "region_centroid": None,
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
        "threshold_value": None,
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
        "tool_hops": 0,
        "class_legend": None,
        "zone_legend": None,
        "calculate_fragmentation": True,
        "knowledge_base": None,
        "initial_description": None,
        "poi_categories": None,
        "geocoded_landmarks": [],
        "plan": None,
        "tool_results": [],
        "errors": [],
        "execution_trace": [],
        "final_answer": None,
        "status": "pending",
    }
    state.update(overrides)
    return state
