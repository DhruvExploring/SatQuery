"""
Route handlers for the SatQuery API.

Thin HTTP bridge → LangGraph. No Sentinel Hub / ERA5 logic here.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from backend.api.models import (
    QUERY_OPENAPI_EXAMPLES,
    HealthResponse,
    QueryRequest,
    QueryResponse,
    resolve_data_path,
    resolve_output_dir,
)
from backend.api.status_codes import http_status_for_query
from backend.orchestrator.graph import invoke_satquery
from backend.orchestrator.state import empty_state

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


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

    state = empty_state(
        query=body.query,
        bbox=body.bbox,
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
    )
    status_code = http_status_for_query(result)
    if status_code == 500 and _latest_tool_error_type(result) == "import_error":
        logger.error(
            "SATQUERY_IMPORT_ERROR tool import failed at request time "
            "(ops: wrong interpreter or working directory)"
        )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


def _latest_tool_error_type(result: dict) -> str | None:
    tool_results = result.get("tool_results") or []
    if not tool_results:
        return None
    error = (tool_results[-1].get("result") or {}).get("error") or {}
    return error.get("type")
