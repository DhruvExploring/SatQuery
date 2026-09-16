"""Upload-time ingestion: validate an uploaded raster, extract the fields
worth keeping (bands, lat/long, place name), and build a small per-image
knowledge base. Run once, synchronously, from the upload endpoint -- a
separate lifecycle from a query's SatQueryState/satquery_graph.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.orchestrator.registry import derive_grounding_fields
from backend.orchestrator.state import ExecutionTraceEntry, trace_entry
from backend.tools.executor import execute_tool

logger = logging.getLogger("satquery.ingest")

VALIDATION_ERROR_MESSAGE = "Please enter a valid GeoTIFF/TIFF file."


class IngestState(TypedDict, total=False):
    file_path: str
    image_count: int
    metadata_result: dict[str, Any]
    bands: list[str]
    latitude: float | None
    longitude: float | None
    bbox: list[float] | None
    pixel_size_wgs84_degrees: dict[str, float] | None
    place_name: str | None
    knowledge_base: dict[str, Any] | None
    error: str | None
    execution_trace: list[ExecutionTraceEntry]


def count_images(state: IngestState) -> dict[str, Any]:
    # /upload-raster accepts exactly one file per request -- pair-mode
    # uploads are two separate requests, each producing its own knowledge
    # base. This node exists for traceability, not because there's a real
    # count to determine here.
    return {
        "image_count": 1,
        "execution_trace": [trace_entry("count_images", "image_count=1")],
    }


def inspect_and_validate(state: IngestState) -> dict[str, Any]:
    result = execute_tool("inspect_geotiff_metadata", {"file_path": state["file_path"]})
    if result.get("status") != "success":
        logger.info(
            "[INGEST VALIDATION FAILED] path=%s error=%s",
            state.get("file_path"),
            result.get("error"),
        )
        return {
            "error": VALIDATION_ERROR_MESSAGE,
            "execution_trace": [trace_entry("inspect_and_validate", "invalid file")],
        }
    return {
        "metadata_result": result,
        "execution_trace": [trace_entry("inspect_and_validate", "valid GeoTIFF")],
    }


def route_after_validate(state: IngestState) -> str:
    return "invalid" if state.get("error") else "valid"


def extract_fields(state: IngestState) -> dict[str, Any]:
    result = state.get("metadata_result") or {}
    bands = [b.get("description") for b in (result.get("bands") or []) if b.get("description")]
    grounding = derive_grounding_fields(result)
    spatial = result.get("spatial") or {}
    return {
        "bands": bands,
        "latitude": grounding.get("latitude"),
        "longitude": grounding.get("longitude"),
        "bbox": grounding.get("bbox"),
        "pixel_size_wgs84_degrees": spatial.get("pixel_size_wgs84_degrees"),
        "execution_trace": [trace_entry("extract_fields", f"bands={len(bands)}")],
    }


def resolve_place_name(state: IngestState) -> dict[str, Any]:
    latitude = state.get("latitude")
    longitude = state.get("longitude")
    if latitude is None or longitude is None:
        return {
            "place_name": None,
            "execution_trace": [trace_entry("resolve_place_name", "no coordinates available")],
        }

    result = execute_tool(
        "get_place_name_from_coordinates",
        {"latitude": latitude, "longitude": longitude},
    )
    if result.get("status") != "success":
        # Geocoding is best-effort -- never fail ingestion because of it.
        logger.info(
            "[INGEST GEOCODE FAILED] lat=%s lon=%s error=%s",
            latitude,
            longitude,
            result.get("error"),
        )
        return {
            "place_name": None,
            "execution_trace": [trace_entry("resolve_place_name", "geocoding unavailable")],
        }
    return {
        "place_name": result.get("place_name"),
        "execution_trace": [trace_entry("resolve_place_name", "resolved")],
    }


def build_knowledge_base(state: IngestState) -> dict[str, Any]:
    knowledge_base = {
        "file_path": state.get("file_path"),
        "bands": state.get("bands") or [],
        "latitude": state.get("latitude"),
        "longitude": state.get("longitude"),
        "bbox": state.get("bbox"),
        "pixel_size_wgs84_degrees": state.get("pixel_size_wgs84_degrees"),
        "place_name": state.get("place_name"),
    }

    file_path = state.get("file_path")
    if file_path:
        kb_path = Path(file_path).with_suffix(".kb.json")
        try:
            kb_path.write_text(json.dumps(knowledge_base, indent=2))
        except OSError as exc:
            logger.warning("Could not persist knowledge base to %s: %r", kb_path, exc)

    return {
        "knowledge_base": knowledge_base,
        "execution_trace": [trace_entry("build_knowledge_base", "built")],
    }


def _build_ingest_graph():
    graph = StateGraph(IngestState)

    graph.add_node("count_images", count_images)
    graph.add_node("inspect_and_validate", inspect_and_validate)
    graph.add_node("extract_fields", extract_fields)
    graph.add_node("resolve_place_name", resolve_place_name)
    graph.add_node("build_knowledge_base", build_knowledge_base)

    graph.add_edge(START, "count_images")
    graph.add_edge("count_images", "inspect_and_validate")
    graph.add_conditional_edges(
        "inspect_and_validate",
        route_after_validate,
        {"invalid": END, "valid": "extract_fields"},
    )
    graph.add_edge("extract_fields", "resolve_place_name")
    graph.add_edge("resolve_place_name", "build_knowledge_base")
    graph.add_edge("build_knowledge_base", END)

    return graph.compile()


ingest_graph = _build_ingest_graph()


def run_ingest(file_path: str) -> dict[str, Any]:
    """Validate + extract + build the knowledge base for one uploaded raster.

    Returns {"ok": True, "knowledge_base": {...}} or
    {"ok": False, "error": "<plain-text message>"}.
    """
    result = ingest_graph.invoke({"file_path": file_path})
    if result.get("error"):
        return {"ok": False, "error": result["error"]}
    return {"ok": True, "knowledge_base": result.get("knowledge_base")}
