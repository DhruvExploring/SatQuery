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

    # Analytical inputs for Tools 5–8
    input_file: str | None = Field(default=None, description="Path to input GeoTIFF for Tool 5 or Tool 6.")
    compare_with: str | None = Field(default=None, description="Second GeoTIFF path to compare grid compatibility in Tool 6.")
    raster_before_path: str | None = Field(default=None, description="Pre-event GeoTIFF path for Tool 7.")
    raster_after_path: str | None = Field(default=None, description="Post-event GeoTIFF path for Tool 7.")
    lulc_raster_path: str | None = Field(default=None, description="LULC GeoTIFF path for Tool 8.")
    dem_raster_path: str | None = Field(default=None, description="DEM elevation GeoTIFF path for Tool 8.")
    zone_mask_path: str | None = Field(default=None, description="Zone/change mask GeoTIFF path for Tool 8.")
    indices: list[str] | None = Field(default=None, description="List of vegetation indices to compute.")
    band_selection: int | str | None = Field(default=1, description="Band selection for change detection in Tool 7.")
    threshold_type: str | None = Field(default="absolute", description="Threshold type for change detection.")
    threshold_value: float | None = Field(default=0.15, description="Threshold value for change detection.")
    relative_change_threshold_percent: float | None = Field(default=None, description="Relative change threshold percent.")
    mask_encoding: str | None = Field(default="bipolar_3class", description="Mask encoding format for Tool 7.")
    analysis_output_dir: str | None = Field(default=None, description="Output directory for generated analysis products.")

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
