"""
Route handlers for the SatQuery API.

Thin HTTP bridge → LangGraph. No Sentinel Hub / ERA5 logic here.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.api.models import HealthResponse, QueryRequest, QueryResponse
from backend.api.status_codes import http_status_for_query
from backend.orchestrator.graph import satquery_graph
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
def run_query(body: QueryRequest) -> JSONResponse:
    logger.info("Received query: %r  bbox=%s", body.query, body.bbox)

    state = empty_state(
        query=body.query,
        bbox=body.bbox,
        latitude=body.latitude,
        longitude=body.longitude,
        start_date=body.start_date,
        end_date=body.end_date,
        bands=body.bands,
        max_cloud_cover=body.max_cloud_cover,
        width=body.width,
        height=body.height,
        polarization=body.polarization,
        orbit_direction=body.orbit_direction,
        scene_selection=body.scene_selection,
    )

    try:
        result = satquery_graph.invoke(state)
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
