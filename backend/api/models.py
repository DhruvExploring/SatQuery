"""
API Pydantic models — request and response shapes for the HTTP layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# SatQuery project root (this file is backend/api/models.py).
_SATQUERY_ROOT = Path(__file__).resolve().parents[2]


def resolve_data_path(value: str | None) -> str | None:
    """Resolve a GeoTIFF path against cwd, then the SatQuery project root."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    candidate = Path(raw)
    if candidate.is_file():
        return str(candidate.resolve())
    nested = _SATQUERY_ROOT / raw
    if nested.is_file():
        return str(nested.resolve())
    # Leave unresolved paths as-is; the tool returns validation_error if missing.
    return raw


def resolve_output_dir(value: str | None) -> str | None:
    """Resolve an output folder against the SatQuery project root when relative."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    candidate = Path(raw)
    if candidate.is_absolute():
        return str(candidate)
    return str(_SATQUERY_ROOT / raw)


# Request-body examples for the Swagger /docs dropdown (one per tool).
QUERY_OPENAPI_EXAMPLES: dict[str, dict[str, Any]] = {
    "tool1_optical": {
        "summary": "Tool 1 — fetch optical RGB",
        "description": "Needs bbox. Hits Sentinel Hub.",
        "value": {
            "query": "Fetch Sentinel-2 optical imagery for Delhi",
            "bbox": [77.1, 28.5, 77.3, 28.7],
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
        },
    },
    "tool2_multispectral": {
        "summary": "Tool 2 — fetch multispectral",
        "description": "Needs bbox. Hits Sentinel Hub.",
        "value": {
            "query": "Fetch Sentinel-2 multispectral imagery for Delhi",
            "bbox": [77.1, 28.5, 77.3, 28.7],
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
        },
    },
    "tool3_sar": {
        "summary": "Tool 3 — fetch SAR",
        "description": "Needs bbox. Hits Sentinel Hub.",
        "value": {
            "query": "Get SAR radar imagery for Delhi",
            "bbox": [77.1, 28.5, 77.3, 28.7],
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
        },
    },
    "tool4_weather": {
        "summary": "Tool 4 — weather / ERA5",
        "description": "Needs bbox or lat/lon. Open-Meteo, no API key.",
        "value": {
            "query": "Get weather and rainfall for this location",
            "latitude": 28.61,
            "longitude": 77.21,
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
        },
    },
    "tool5_indices": {
        "summary": "Tool 5 — vegetation indices",
        "description": "Offline. Needs input_file pointing at an 8-band Tool 2 GeoTIFF.",
        "value": {
            "query": "Compute NDVI vegetation indices from this GeoTIFF",
            "input_file": (
                "Tool_2_fetch_multispectral_imagery/test_runs/"
                "sample_multispectral_output.tif"
            ),
            "indices": [
                "NDVI",
                "EVI",
                "SAVI",
                "GNDVI",
                "NDRE_B5",
                "NDRE_B7",
                "NDMI",
                "NDWI",
                "MSAVI",
                "NBR",
            ],
            "calculate_heuristic_classification": True,
            "analysis_output_dir": "Tool_5_compute_vegetation_indices/test_runs",
        },
    },
    "tool6_inspect": {
        "summary": "Tool 6 — inspect GeoTIFF QA",
        "description": "Offline. Needs input_file. compare_with is optional grid-alignment check.",
        "value": {
            "query": "Inspect this GeoTIFF and run raster QA",
            "input_file": (
                "Tool_7_analyze_temporal_change/test_runs/sample_indices_t1.tif"
            ),
            "compare_with": (
                "Tool_7_analyze_temporal_change/test_runs/sample_indices_t2.tif"
            ),
            "calculate_statistics": True,
            "calculate_histogram": True,
        },
    },
    "tool7_change": {
        "summary": "Tool 7 — temporal change",
        "description": "Offline. Needs two aligned GeoTIFFs (before / after).",
        "value": {
            "query": "Analyze temporal change between these two rasters",
            "raster_before_path": (
                "Tool_7_analyze_temporal_change/test_runs/sample_indices_t1.tif"
            ),
            "raster_after_path": (
                "Tool_7_analyze_temporal_change/test_runs/sample_indices_t2.tif"
            ),
            "band_selection": "NDVI",
            "threshold_type": "absolute",
            "threshold_value": 0.15,
            "relative_change_threshold_percent": 20.0,
            "mask_encoding": "bipolar_3class",
            "analysis_output_dir": "Tool_7_analyze_temporal_change/test_runs",
            "generate_difference_raster": True,
            "generate_change_mask": True,
        },
    },
    "tool8_lulc": {
        "summary": "Tool 8 — land cover and terrain",
        "description": "Offline. Needs lulc_raster_path. DEM and Tool 7 change mask are optional.",
        "value": {
            "query": "Analyze land cover and terrain for this WorldCover raster",
            "lulc_raster_path": (
                "Tool_8_analyze_spatial_landcover_terrain/test_runs/"
                "sample_worldcover_10m.tif"
            ),
            "dem_raster_path": (
                "Tool_8_analyze_spatial_landcover_terrain/test_runs/"
                "sample_copernicus_dem_30m.tif"
            ),
            "zone_mask_path": (
                "Tool_7_analyze_temporal_change/test_runs/"
                "sample_indices_t1_vs_sample_indices_t2_NDVI_change_mask.tif"
            ),
            "calculate_fragmentation": True,
        },
    },
    "chain_deforestation": {
        "summary": "Handshake — deforestation (2→5→6→7→8)",
        "description": (
            "Needs bbox, T1 dates, T2 dates, and lulc_raster_path. "
            "Fetches two multispectral scenes, computes indices, gates on Tool 6, "
            "then Tool 7 and Tool 8."
        ),
        "value": {
            "query": "Detect deforestation and vegetation loss before and after",
            "bbox": [77.1, 28.5, 77.3, 28.7],
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "post_start_date": "2025-01-01",
            "post_end_date": "2025-01-31",
            "lulc_raster_path": (
                "Tool_8_analyze_spatial_landcover_terrain/test_runs/"
                "sample_worldcover_10m.tif"
            ),
        },
    },
    "mission_wildfire": {
        "summary": "Pipeline A — wildfire burn severity",
        "description": "Files-only: pre/post multispectral + LULC. DEM optional.",
        "value": {
            "query": "Map wildfire burn severity and fire scar",
            "raster_before_path": (
                "Tool_2_fetch_multispectral_imagery/test_runs/"
                "sample_multispectral_output.tif"
            ),
            "raster_after_path": (
                "Tool_2_fetch_multispectral_imagery/test_runs/"
                "sample_multispectral_output.tif"
            ),
            "lulc_raster_path": (
                "Tool_8_analyze_spatial_landcover_terrain/test_runs/"
                "sample_worldcover_10m.tif"
            ),
            "dem_raster_path": (
                "Tool_8_analyze_spatial_landcover_terrain/test_runs/"
                "sample_copernicus_dem_30m.tif"
            ),
        },
    },
    "mission_flood": {
        "summary": "Pipeline B — flood inundation",
        "description": "Needs two SAR windows (or files) plus LULC. Not SAR-fetch-only.",
        "value": {
            "query": "Assess flood inundation impact",
            "bbox": [77.1, 28.5, 77.3, 28.7],
            "start_date": "2024-07-01",
            "end_date": "2024-07-10",
            "post_start_date": "2024-07-20",
            "post_end_date": "2024-07-31",
            "lulc_raster_path": (
                "Tool_8_analyze_spatial_landcover_terrain/test_runs/"
                "sample_worldcover_10m.tif"
            ),
        },
    },
    "mission_drought": {
        "summary": "Pipeline C — agricultural drought",
        "description": "Fetches multispectral if needed, then NDVI/NDMI/EVI + ERA5.",
        "value": {
            "query": "Analyze agricultural drought and canopy stress",
            "bbox": [77.1, 28.5, 77.3, 28.7],
            "start_date": "2025-04-01",
            "end_date": "2025-04-30",
        },
    },
    "tool_describe_region": {
        "summary": "Describe a marked region (vision, grounded)",
        "description": (
            "Needs input_file (a GeoTIFF) and region_bbox. Crops the raster to "
            "region_bbox and describes only that crop. Vision tool must be enabled."
        ),
        "value": {
            "query": "What is in the region I marked?",
            "input_file": (
                "Tool_1_fetch_optical_imagery/test_runs/sample_optical_output.tif"
            ),
            "region_bbox": [77.15, 28.55, 77.20, 28.60],
        },
    },
    "tool1_sar_fallback": {
        "summary": "Tool 1 — optical (SAR fallback is automatic)",
        "description": (
            "Same as Tool 1. If the optical result sets flags.sar_recommended or "
            "flags.optical_quality_poor, the graph appends a Tool 3 fetch."
        ),
        "value": {
            "query": "Fetch Sentinel-2 optical imagery for Delhi",
            "bbox": [77.1, 28.5, 77.3, 28.7],
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
        },
    },
}


class QueryRequest(BaseModel):
    """Body for POST /api/v1/query."""

    query: str = Field(
        ...,
        min_length=1,
        description=(
            "Natural-language request. Handshake classifies missions "
            "(wildfire / flood / drought) and chains (NDVI, deforestation) "
            "before single-tool keywords. Examples: "
            "'Fetch Sentinel-2 imagery', 'Compute NDVI', 'Inspect this GeoTIFF', "
            "'Detect deforestation before and after', 'Map wildfire burn severity'."
        ),
    )
    bbox: list[float] | None = Field(
        default=None,
        description="[min_lon, min_lat, max_lon, max_lat]. Required for imagery tools.",
    )
    region_bbox: list[float] | None = Field(
        default=None,
        description=(
            "[min_lon, min_lat, max_lon, max_lat] of a sub-region of input_file "
            "the user has already marked/drawn (e.g. a frontend ROI box "
            "converted to real coordinates via the image's own bounds_wgs84). "
            "Distinct from bbox, which is the AOI for fetch tools or the whole "
            "image's own extent. Used by describe_marked_region."
        ),
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
    start_date: str | None = Field(
        default=None,
        description="YYYY-MM-DD. T1 / single-scene fetch window.",
    )
    end_date: str | None = Field(
        default=None,
        description="YYYY-MM-DD. T1 / single-scene fetch window.",
    )
    post_start_date: str | None = Field(
        default=None,
        description="YYYY-MM-DD. T2 fetch window for temporal missions and chains.",
    )
    post_end_date: str | None = Field(
        default=None,
        description="YYYY-MM-DD. T2 fetch window for temporal missions and chains.",
    )
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

    # Tools 5–8: local GeoTIFF analysis inputs for POST /api/v1/query.
    input_file: str | None = Field(
        default=None,
        description=(
            "GeoTIFF path for Tool 5 (multispectral) or Tool 6 (any raster). "
            "Relative to the SatQuery folder or an absolute path."
        ),
    )
    indices: list[str] | None = Field(
        default=None,
        description="Tool 5 index names, e.g. NDVI, EVI, NBR. Default is all 10.",
    )
    band_mapping: dict[str, str] | None = Field(
        default=None,
        description='Tool 5 band map, e.g. {"Band_1": "B02", "Band_6": "B08"}.',
    )
    calculate_heuristic_classification: bool = Field(
        default=True,
        description="Tool 5: compute canopy-vigor area classes from NDVI.",
    )
    compare_with: str | None = Field(
        default=None,
        description="Tool 6: optional second GeoTIFF for grid-alignment QA.",
    )
    calculate_statistics: bool = Field(
        default=True,
        description="Tool 6: per-band percentiles.",
    )
    calculate_histogram: bool = Field(
        default=True,
        description="Tool 6: 10-bin histograms.",
    )
    raster_before_path: str | None = Field(
        default=None,
        description="Tool 7: baseline / T1 GeoTIFF.",
    )
    raster_after_path: str | None = Field(
        default=None,
        description="Tool 7: target / T2 GeoTIFF.",
    )
    band_selection: int | str | None = Field(
        default=1,
        description='Tool 7 band: 1-based index or name such as "NDVI" or "VV_dB".',
    )
    threshold_type: str = Field(
        default="absolute",
        description='Tool 7: "absolute" or "statistical".',
    )
    threshold_value: float | None = Field(
        default=None,
        description=(
            "Tool 7: absolute delta, or k for μ ± kσ when statistical. Left "
            "unset, the backend picks 0.15 for a vegetation-index-style "
            "raster or 3.0 for SAR backscatter (dB), detected from the file "
            "names."
        ),
    )
    relative_change_threshold_percent: float | None = Field(
        default=None,
        description="Tool 7 optional relative % cutoff. Do not use on SAR dB.",
    )
    mask_encoding: str = Field(
        default="bipolar_3class",
        description='Tool 7: "bipolar_3class" or "severity_5class".',
    )
    analysis_output_dir: str | None = Field(
        default=None,
        description="Output folder for Tool 5 / 7 / 8 products.",
    )
    generate_difference_raster: bool = Field(
        default=True,
        description="Tool 7: write the continuous delta GeoTIFF.",
    )
    generate_change_mask: bool = Field(
        default=True,
        description="Tool 7: write the integer change-mask GeoTIFF.",
    )
    lulc_raster_path: str | None = Field(
        default=None,
        description="Tool 8: classified land-cover GeoTIFF (e.g. ESA WorldCover).",
    )
    dem_raster_path: str | None = Field(
        default=None,
        description="Tool 8: optional DEM GeoTIFF in metres.",
    )
    zone_mask_path: str | None = Field(
        default=None,
        description="Tool 8: optional Tool 7 change_mask.tif for zonal tabulation.",
    )
    calculate_fragmentation: bool = Field(
        default=True,
        description="Tool 8: 8-connectivity patch metrics.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                example["value"] for example in QUERY_OPENAPI_EXAMPLES.values()
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
    knowledge_base: dict[str, Any] | None = Field(
        default=None,
        description="Per-image knowledge base (bands/lat/long/place_name) built at upload time, if input_file has one.",
    )
    initial_description: str | None = Field(
        default=None,
        description="The VLM's first-pass description of input_file, grounded in knowledge_base, before any further tool calls.",
    )


class HealthResponse(BaseModel):
    status: str = "ok"


class ResetConversationRequest(BaseModel):
    session_id: str | None = Field(
        default=None,
        description="Optional session or thread identifier to reset.",
    )
    temp_files: list[str] = Field(
        default_factory=list,
        description="List of temporary uploaded file paths to clean up from disk.",
    )


class ResetConversationResponse(BaseModel):
    status: str = "ok"
    message: str = "Conversation context reset."
    deleted_temp_files: list[str] = Field(
        default_factory=list,
        description="Temporary upload files successfully removed from disk.",
    )
