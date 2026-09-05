"""
API Pydantic models — request and response shapes for the HTTP layer.

These models are ONLY for serialising/deserialising HTTP bodies.
They are NOT used by LangGraph. The graph uses SatQueryState (TypedDict).

Why separate models from state?
  - SatQueryState is LangGraph's internal clipboard; it carries runtime
    data (plan, tool_results, errors) that callers should never send.
  - These models enforce exactly what the API accepts and returns.
  - If state.py ever changes internals, API contracts stay stable.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------
class QueryRequest(BaseModel):
    """Body for POST /api/v1/query."""

    query: str = Field(
        ...,
        min_length=1,
        description="Natural-language request, e.g. 'Fetch Sentinel-2 imagery for Delhi'.",
    )
    bbox: list[float] | None = Field(
        default=None,
        description="[min_lon, min_lat, max_lon, max_lat]. Required for fetch requests.",
    )
    start_date: str | None = Field(
        default=None,
        description="Start of date range. YYYY-MM-DD.",
    )
    end_date: str | None = Field(
        default=None,
        description="End of date range. YYYY-MM-DD.",
    )
    modality: str = Field(
        default="optical",
        description="'optical' or 'multispectral'.",
    )
    max_cloud_cover: float = Field(
        default=30.0,
        ge=0.0,
        le=100.0,
        description="Maximum cloud cover percentage allowed.",
    )
    width: int = Field(default=512, ge=1, le=4096)
    height: int = Field(default=512, ge=1, le=4096)

    # Identity — scopes LangMem memories to a specific user.
    # Optional: omit for anonymous / stateless queries.
    user_id: str | None = Field(
        default=None,
        description="Optional user identifier for scoped long-term memory.",
    )

    model_config = {"json_schema_extra": {
        "examples": [{
            "query": "Fetch Sentinel-2 imagery for Delhi",
            "bbox": [77.1, 28.5, 77.3, 28.7],
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
            "user_id": "user-123",
        }]
    }}


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------
class QueryResponse(BaseModel):
    """Body returned by POST /api/v1/query."""

    status: str = Field(description="'success' | 'error' | 'clarify' | 'pending'")
    final_answer: str | None = Field(default=None)

    # Optional fields — only present when relevant
    plan: dict[str, Any] | None = Field(
        default=None,
        description="The planner's decision (action, tool, args, reason).",
    )
    tool_results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Raw tool output(s) from the executor.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Validation or execution errors, if any.",
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str = "ok"
