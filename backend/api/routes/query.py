"""
Route handlers for the SatQuery API.

This file contains ONLY route functions.
No business logic lives here. The handler:
  1. Receives the validated request body (Pydantic does this automatically).
  2. Builds initial LangGraph state using the existing helper.
  3. Invokes the existing compiled graph.
  4. Maps the graph output to the HTTP response model.
  5. Raises HTTPException for unexpected failures.

The graph itself handles all domain errors (validation failures,
missing bbox, tool errors) by setting state["status"] and
state["errors"]. Those are returned as 200 responses with the
appropriate status field — they are not HTTP 4xx errors.

HTTP 422 is only for malformed JSON bodies (FastAPI handles automatically).
HTTP 500 is only for unhandled Python exceptions inside graph execution.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.api.models import HealthResponse, QueryRequest, QueryResponse
from backend.orchestrator.graph import satquery_graph
from backend.orchestrator.state import empty_state

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@router.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """Liveness probe. Returns 200 when the process is up."""
    return HealthResponse(status="ok")


# ---------------------------------------------------------------------------
# Main query endpoint
# ---------------------------------------------------------------------------
@router.post("/api/v1/query", response_model=QueryResponse, tags=["query"])
def run_query(body: QueryRequest) -> QueryResponse:
    """
    Accept a natural-language remote-sensing request, run it through
    the LangGraph orchestrator, and return the result.

    The graph handles all domain-level decisions:
      - Input validation (bbox range, dates)
      - Planning (which tool to call, or whether to ask for clarification)
      - Tool execution
      - Response generation

    This endpoint only bridges HTTP ↔ graph.
    """
    logger.info("Received query: %r  bbox=%s", body.query, body.bbox)

    # Build the initial state from the request body.
    # empty_state() sets safe defaults; overrides apply only what was sent.
    state = empty_state(
        query=body.query,
        bbox=body.bbox,
        start_date=body.start_date,
        end_date=body.end_date,
        modality=body.modality,
        max_cloud_cover=body.max_cloud_cover,
        width=body.width,
        height=body.height,
        user_id=body.user_id,
    )

    try:
        result = satquery_graph.invoke(state)
    except Exception as exc:
        # The graph is designed not to raise — it catches its own errors
        # and sets state["status"] = "error". If we still land here, it
        # is an infrastructure-level failure (OOM, LangGraph bug, etc.).
        logger.exception("Graph raised an unhandled exception")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info("Graph finished: status=%r", result.get("status"))

    return QueryResponse(
        status=result.get("status", "error"),
        final_answer=result.get("final_answer"),
        plan=result.get("plan"),
        tool_results=result.get("tool_results", []),
        errors=result.get("errors", []),
    )
