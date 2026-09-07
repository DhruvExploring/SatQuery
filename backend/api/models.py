"""
API Pydantic models — request and response shapes for the HTTP layer.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Body for POST /api/v1/query."""

    query: str = Field(
        ...,
        min_length=1,
        description="Natural-language request, e.g. 'Fetch Sentinel-2 imagery for Delhi'.",
    )
    bbox: list[float] | None = Field(
        default=None,
        description="[min_lon, min_lat, max_lon, max_lat]. Required for imagery tools.",
    )
    latitude: float | None = Field(
        default=None,
        ge=-90.0,
        le=90.0,
        description="Optional point latitude for weather tool.",
    )
    longitude: float | None = Field(
        default=None,
        ge=-180.0,
        le=180.0,
        description="Optional point longitude for weather tool.",
    )
    start_date: str | None = Field(default=None, description="YYYY-MM-DD")
    end_date: str | None = Field(default=None, description="YYYY-MM-DD")
    bands: list[str] | None = Field(
        default=None,
        description="Optional Sentinel-2 bands for multispectral fetches.",
    )
    max_cloud_cover: float = Field(default=30.0, ge=0.0, le=100.0)
    width: int = Field(default=512, ge=1, le=4096)
    height: int = Field(default=512, ge=1, le=4096)
    polarization: list[str] | None = Field(
        default=None,
        description="Optional SAR polarizations, e.g. ['VV','VH'].",
    )
    orbit_direction: str | None = Field(
        default=None,
        description="ASCENDING | DESCENDING | BOTH",
    )
    scene_selection: str | None = Field(default=None)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "query": "Fetch Sentinel-2 optical imagery for Delhi",
                    "bbox": [77.1, 28.5, 77.3, 28.7],
                    "start_date": "2025-01-01",
                    "end_date": "2025-01-31",
                }
            ]
        }
    }


class QueryResponse(BaseModel):
    status: str = Field(
        description=(
            "Semantic outcome: success | ok | clarify | error. "
            "HTTP codes: 200 success/ok, 400 invalid/missing input, "
            "404 no matching scene/data, 502 upstream tool failure, 500 internal."
        )
    )
    final_answer: str | None = Field(default=None)
    plan: dict[str, Any] | None = Field(default=None)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    execution_trace: list[dict[str, Any]] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
