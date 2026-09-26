"""
Route handlers for the SatQuery API.

Thin HTTP bridge → LangGraph. No Sentinel Hub / ERA5 logic here.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse, StreamingResponse

from backend.api.models import (
    QUERY_OPENAPI_EXAMPLES,
    HealthResponse,
    QueryRequest,
    QueryResponse,
    ResetConversationRequest,
    ResetConversationResponse,
    resolve_data_path,
    resolve_output_dir,
)
from backend.api.status_codes import http_status_for_query
from backend.orchestrator.graph import GRAPH_INVOKE_CONFIG, invoke_satquery, satquery_graph
from backend.orchestrator.state import SatQueryState, empty_state

logger = logging.getLogger(__name__)

router = APIRouter()


def _state_from_request(body: QueryRequest) -> SatQueryState:
    return empty_state(
        query=body.query,
        bbox=body.bbox,
        region_bbox=body.region_bbox,
        latitude=body.latitude,
        longitude=body.longitude,
        start_date=body.start_date,
        end_date=body.end_date,
        post_start_date=body.post_start_date,
        post_end_date=body.post_end_date,
        bands=body.bands,
        max_cloud_cover=body.max_cloud_cover,
        width=body.width,
        height=body.height,
        polarization=body.polarization,
        orbit_direction=body.orbit_direction,
        scene_selection=body.scene_selection,
        input_file=resolve_data_path(body.input_file),
        indices=body.indices,
        band_mapping=body.band_mapping,
        calculate_heuristic_classification=body.calculate_heuristic_classification,
        compare_with=resolve_data_path(body.compare_with),
        calculate_statistics=body.calculate_statistics,
        calculate_histogram=body.calculate_histogram,
        raster_before_path=resolve_data_path(body.raster_before_path),
        raster_after_path=resolve_data_path(body.raster_after_path),
        band_selection=body.band_selection if body.band_selection is not None else 1,
        threshold_type=body.threshold_type,
        threshold_value=body.threshold_value,
        relative_change_threshold_percent=body.relative_change_threshold_percent,
        mask_encoding=body.mask_encoding,
        analysis_output_dir=resolve_output_dir(body.analysis_output_dir),
        generate_difference_raster=body.generate_difference_raster,
        generate_change_mask=body.generate_change_mask,
        lulc_raster_path=resolve_data_path(body.lulc_raster_path),
        dem_raster_path=resolve_data_path(body.dem_raster_path),
        zone_mask_path=resolve_data_path(body.zone_mask_path),
        calculate_fragmentation=body.calculate_fragmentation,
    )


@router.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post(
    "/api/v1/conversation/reset",
    response_model=ResetConversationResponse,
    tags=["conversation"],
)
@router.post(
    "/api/v1/reset",
    response_model=ResetConversationResponse,
    tags=["conversation"],
)
def reset_conversation(
    body: ResetConversationRequest | None = None,
) -> ResetConversationResponse:
    """Reset active conversation state and remove any temporary uploaded files.

    Guarantees previous conversation context is not reused. Permanent satellite
    datasets are never deleted.
    """
    deleted_files = []
    if body and body.temp_files:
        from backend.api.routes.uploads import delete_temp_upload_file

        for file_path in body.temp_files:
            if delete_temp_upload_file(file_path):
                deleted_files.append(file_path)

    logger.info(
        "Conversation reset complete. Session=%s, Deleted temp files=%s",
        body.session_id if body else None,
        deleted_files,
    )
    return ResetConversationResponse(
        status="ok",
        message="Conversation context reset.",
        deleted_temp_files=deleted_files,
    )


@router.post(
    "/api/v1/query",
    response_model=QueryResponse,
    tags=["query"],
    responses={
        200: {"model": QueryResponse, "description": "Tool succeeded, or chat reply."},
        400: {"model": QueryResponse, "description": "Invalid input or missing location."},
        404: {"model": QueryResponse, "description": "No matching scene or weather data for the filters."},
        502: {"model": QueryResponse, "description": "Upstream imagery/weather provider failed."},
        500: {"model": QueryResponse, "description": "Unhandled server error."},
    },
)
def run_query(
    body: Annotated[
        QueryRequest,
        Body(openapi_examples=QUERY_OPENAPI_EXAMPLES),
    ],
) -> JSONResponse:
    logger.info(
        "Received query: %r  bbox=%s  input_file=%s",
        body.query,
        body.bbox,
        body.input_file,
    )

    state = _state_from_request(body)

    try:
        result = invoke_satquery(state)
    except Exception as exc:
        logger.exception("Graph raised an unhandled exception")
        payload = QueryResponse(
            status="error",
            final_answer="Internal server error.",
            plan=None,
            tool_results=[],
            errors=[str(exc)],
            execution_trace=[],
        )
        return JSONResponse(status_code=500, content=payload.model_dump())

    logger.info("Graph finished: status=%r", result.get("status"))

    payload = QueryResponse(
        status=result.get("status", "error"),
        final_answer=result.get("final_answer"),
        plan=result.get("plan"),
        tool_results=result.get("tool_results", []),
        errors=result.get("errors", []),
        execution_trace=result.get("execution_trace", []),
        knowledge_base=result.get("knowledge_base"),
        initial_description=result.get("initial_description"),
    )
    status_code = http_status_for_query(result)
    if status_code == 500 and _latest_tool_error_type(result) == "import_error":
        logger.error(
            "SATQUERY_IMPORT_ERROR tool import failed at request time "
            "(ops: wrong interpreter or working directory)"
        )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


@router.post("/api/v1/query/stream", tags=["query"])
def run_query_stream(
    body: Annotated[
        QueryRequest,
        Body(openapi_examples=QUERY_OPENAPI_EXAMPLES),
    ],
) -> StreamingResponse:
    """Server-Sent Events variant of /api/v1/query: emits one `step` event per
    LangGraph node (validate, load_knowledge_base, vlm_initial_description,
    llm, tool, respond) as it actually completes, then a closing `final`
    event with the same payload shape as the non-streaming endpoint -- for a
    UI that wants to show the tool chain unfolding live instead of only
    after the whole request finishes.
    """
    logger.info(
        "Received streaming query: %r  bbox=%s  input_file=%s",
        body.query,
        body.bbox,
        body.input_file,
    )
    state = _state_from_request(body)

    def event_gen():
        accumulated: dict[str, Any] = dict(state)
        try:
            for update in satquery_graph.stream(state, GRAPH_INVOKE_CONFIG, stream_mode="updates"):
                for node_update in (update or {}).values():
                    if not isinstance(node_update, dict):
                        continue
                    for key, value in node_update.items():
                        if key in ("execution_trace", "tool_results") and isinstance(value, list):
                            accumulated[key] = (accumulated.get(key) or []) + value
                        else:
                            accumulated[key] = value
                    for entry in node_update.get("execution_trace") or []:
                        yield f"data: {json.dumps({'type': 'step', 'step': entry}, default=str)}\n\n"

            logger.info("Graph finished (stream): status=%r", accumulated.get("status"))
            final_payload = {
                "type": "final",
                "status": accumulated.get("status", "error"),
                "final_answer": accumulated.get("final_answer"),
                "plan": accumulated.get("plan"),
                "tool_results": accumulated.get("tool_results", []),
                "errors": accumulated.get("errors", []),
                "execution_trace": accumulated.get("execution_trace", []),
                "knowledge_base": accumulated.get("knowledge_base"),
                "initial_description": accumulated.get("initial_description"),
            }
            yield f"data: {json.dumps(final_payload, default=str)}\n\n"
        except Exception as exc:
            logger.exception("Graph raised an unhandled exception (stream)")
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _latest_tool_error_type(result: dict) -> str | None:
    tool_results = result.get("tool_results") or []
    if not tool_results:
        return None
    error = (tool_results[-1].get("result") or {}).get("error") or {}
    return error.get("type")
