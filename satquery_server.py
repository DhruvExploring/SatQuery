"""SatQuery Unified FastMCP Production Server.

Exposes the complete 11-Tool Earth Observation & Spatial Intelligence Suite
under a single unified FastMCP interface with comprehensive validation and error trapping.
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Literal, Optional, Union, Any

try:
    from fastmcp import FastMCP
except (ImportError, Exception):
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        FastMCP = None

# Add root directory to sys.path to ensure module imports succeed in any environment
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Import individual tool engines and Pydantic models
from Tool_1_fetch_optical_imagery.fetch_optical_imagery import (
    OpticalSatelliteRequest,
    fetch_optical_imagery,
)
from Tool_2_fetch_multispectral_imagery.fetch_multispectral_imagery import (
    MultispectralSatelliteRequest,
    fetch_multispectral_imagery,
)
from Tool_3_fetch_sar_imagery.fetch_sar_imagery import (
    SARSatelliteRequest,
    fetch_sar_imagery,
)
from Tool_4_fetch_weather_environment.fetch_weather_environment import (
    WeatherEnvironmentRequest,
    fetch_weather_environment,
)
from Tool_5_compute_vegetation_indices.compute_vegetation_indices import (
    VegetationIndicesRequest,
    compute_vegetation_indices,
)
from Tool_6_inspect_geotiff_metadata.inspect_geotiff_metadata import (
    GeoTIFFInspectionRequest,
    inspect_geotiff_metadata,
)
from Tool_7_analyze_temporal_change.analyze_temporal_change import (
    TemporalChangeRequest,
    analyze_temporal_change,
)
from Tool_8_analyze_spatial_landcover_terrain.analyze_spatial_landcover_terrain import (
    SpatialLandcoverTerrainRequest,
    analyze_spatial_landcover_terrain,
)
from Tool_9_fetch_web_intelligence.fetch_web_intelligence import (
    WebIntelligenceRequest,
    fetch_web_intelligence,
)
from Tool_10_spatial_geocoding_poi.spatial_geocoding_poi import (
    SpatialGeocodingRequest,
    fetch_spatial_geocoding_poi,
)
from Tool_11_deterministic_affine_markup.deterministic_affine_markup import (
    AffineMarkupRequest,
    FeatureItem,
    project_and_markup_raster,
)

if FastMCP is None:
    class _DummyMCP:
        def tool(self, *args, **kwargs):
            return lambda fn: fn
        async def list_tools(self):
            return []
    mcp = _DummyMCP()
else:
    mcp = FastMCP("SatQuery Earth Observation Intelligence System")


# =============================================================================
# Tool 1: Visual Optical Imagery (Sentinel-2 L2A True Color)
# =============================================================================
@mcp.tool(
    name="fetch_optical_imagery",
    description="Fetch Sentinel-2 L2A visual RGB (B04, B03, B02) True-Color GeoTIFF imagery with AOI-level Scene Classification Layer (SCL) quality analysis."
)
def mcp_fetch_optical_imagery(
    bbox: list[float],
    start_date: str,
    end_date: str,
    max_cloud_cover: float = 30.0,
    width: int = 512,
    height: int = 512
) -> dict:
    try:
        req = OpticalSatelliteRequest(
            bbox=bbox,
            start_date=start_date,
            end_date=end_date,
            max_cloud_cover=max_cloud_cover,
            width=width,
            height=height
        )
        return fetch_optical_imagery(req)
    except ValueError as e:
        return {"status": "error", "error": {"type": "validation_error", "message": str(e)}}
    except Exception as e:
        return {"status": "error", "error": {"type": "service_error", "message": str(e)}}


# =============================================================================
# Tool 2: Surface Reflectance Multispectral Imagery (Sentinel-2 L2A 8-Band)
# =============================================================================
@mcp.tool(
    name="fetch_multispectral_imagery",
    description="Retrieve multi-band Surface Reflectance FLOAT32 Sentinel-2 Level-2A GeoTIFF rasters with embedded GDAL band descriptions."
)
def mcp_fetch_multispectral_imagery(
    bbox: list[float],
    start_date: str,
    end_date: str,
    max_cloud_cover: float = 30.0,
    bands: list[str] = ["B02", "B03", "B04", "B05", "B07", "B08", "B11", "B12"],
    width: int = 256,
    height: int = 256
) -> dict:
    try:
        req = MultispectralSatelliteRequest(
            bbox=bbox,
            start_date=start_date,
            end_date=end_date,
            max_cloud_cover=max_cloud_cover,
            bands=bands,
            width=width,
            height=height
        )
        return fetch_multispectral_imagery(req)
    except ValueError as e:
        return {"status": "error", "error": {"type": "validation_error", "message": str(e)}}
    except Exception as e:
        return {"status": "error", "error": {"type": "service_error", "message": str(e)}}


# =============================================================================
# Tool 3: All-Weather Synthetic Aperture Radar (Sentinel-1 GRD)
# =============================================================================
@mcp.tool(
    name="fetch_sar_imagery",
    description="Fetch Sentinel-1 GRD Synthetic Aperture Radar (SAR) C-Band backscatter GeoTIFF imagery in decibels (dB) with incidence angle and radar shadow geometry checks."
)
def mcp_fetch_sar_imagery(
    bbox: list[float],
    start_date: str,
    end_date: str,
    polarizations: list[Literal["VV", "VH"]] = ["VV", "VH"],
    orbit_direction: Literal["ASCENDING", "DESCENDING", "EITHER"] = "EITHER",
    scene_selection: Literal["closest_to_start_date", "closest_to_end_date", "most_recent"] = "most_recent",
    width: int = 256,
    height: int = 256
) -> dict:
    try:
        req = SARSatelliteRequest(
            bbox=bbox,
            start_date=start_date,
            end_date=end_date,
            polarizations=polarizations,
            orbit_direction=orbit_direction,
            scene_selection=scene_selection,
            width=width,
            height=height
        )
        return fetch_sar_imagery(req)
    except ValueError as e:
        return {"status": "error", "error": {"type": "validation_error", "message": str(e)}}
    except Exception as e:
        return {"status": "error", "error": {"type": "service_error", "message": str(e)}}


# =============================================================================
# Tool 4: Meteorological & Environmental Context (ERA5 / ERA5-Land)
# =============================================================================
@mcp.tool(
    name="fetch_weather_environment",
    description="Fetch factual ERA5/ERA5-Land reanalysis meteorological metrics (temperature, precipitation, soil moisture, ET0, water balance) and derived climatic stress indicators."
)
def mcp_fetch_weather_environment(
    start_date: str,
    end_date: str,
    bbox: Optional[list[float]] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    rolling_windows: list[int] = [7, 30]
) -> dict:
    try:
        req = WeatherEnvironmentRequest(
            bbox=bbox,
            latitude=latitude,
            longitude=longitude,
            start_date=start_date,
            end_date=end_date,
            rolling_windows=rolling_windows
        )
        return fetch_weather_environment(req)
    except ValueError as e:
        return {"status": "error", "error": {"type": "validation_error", "message": str(e)}}
    except Exception as e:
        return {"status": "error", "error": {"type": "service_error", "message": str(e)}}


# =============================================================================
# Tool 5: Biophysical & Spectral Vegetation Indices Engine
# =============================================================================
@mcp.tool(
    name="compute_vegetation_indices",
    description="Compute 10+ standard biophysical and spectral indices (NDVI, EVI, SAVI, GNDVI, NDRE_B5, NDRE_B7, NDMI, NDWI, MSAVI, NBR) from multi-band surface reflectance GeoTIFFs."
)
def mcp_compute_vegetation_indices(
    file_path: str,
    indices: list[str] = ["NDVI", "EVI", "SAVI", "GNDVI", "NDRE_B5", "NDRE_B7", "NDMI", "NDWI", "MSAVI", "NBR"],
    band_mapping: Optional[dict[str, str]] = None,
    output_dir: Optional[str] = None
) -> dict:
    try:
        req = VegetationIndicesRequest(
            file_path=file_path,
            indices=indices,
            band_mapping=band_mapping,
            output_dir=output_dir
        )
        return compute_vegetation_indices(req)
    except ValueError as e:
        return {"status": "error", "error": {"type": "validation_error", "message": str(e)}}
    except Exception as e:
        return {"status": "error", "error": {"type": "service_error", "message": str(e)}}


# =============================================================================
# Tool 6: Universal Pre-Flight Raster QA & Metadata Inspector
# =============================================================================
@mcp.tool(
    name="inspect_geotiff_metadata",
    description="Deep spatial inspection of GeoTIFF rasters (CRS, affine bounds, NoData/NaN integrity, GSD resolution, and cross-raster grid alignment checks)."
)
def mcp_inspect_geotiff_metadata(
    file_path: str,
    calculate_statistics: bool = True,
    calculate_histogram: bool = True,
    compare_with: Optional[str] = None
) -> dict:
    try:
        req = GeoTIFFInspectionRequest(
            file_path=file_path,
            calculate_statistics=calculate_statistics,
            calculate_histogram=calculate_histogram,
            compare_with=compare_with
        )
        return inspect_geotiff_metadata(req)
    except ValueError as e:
        return {"status": "error", "error": {"type": "validation_error", "message": str(e)}}
    except Exception as e:
        return {"status": "error", "error": {"type": "service_error", "message": str(e)}}


# =============================================================================
# Tool 7: Grid-Aligned Temporal Differential Change Detection
# =============================================================================
@mcp.tool(
    name="analyze_temporal_change",
    description="Perform pixel-wise temporal change detection between two aligned GeoTIFF rasters (T1 and T2), applying thresholding and generating difference and change mask products."
)
def mcp_analyze_temporal_change(
    raster_before_path: str,
    raster_after_path: str,
    band_selection: Union[int, str] = 1,
    threshold_type: Literal["absolute", "statistical"] = "absolute",
    threshold_value: float = 0.15,
    relative_change_threshold_percent: Optional[float] = None,
    mask_encoding: Literal["bipolar_3class", "severity_5class"] = "bipolar_3class",
    output_dir: Optional[str] = None,
    generate_difference_raster: bool = True,
    generate_change_mask: bool = True
) -> dict:
    try:
        req = TemporalChangeRequest(
            raster_before_path=raster_before_path,
            raster_after_path=raster_after_path,
            band_selection=band_selection,
            threshold_type=threshold_type,
            threshold_value=threshold_value,
            relative_change_threshold_percent=relative_change_threshold_percent,
            mask_encoding=mask_encoding,
            output_dir=output_dir,
            generate_difference_raster=generate_difference_raster,
            generate_change_mask=generate_change_mask
        )
        return analyze_temporal_change(req)
    except ValueError as e:
        return {"status": "error", "error": {"type": "validation_error", "message": str(e)}}
    except Exception as e:
        return {"status": "error", "error": {"type": "service_error", "message": str(e)}}


# =============================================================================
# Tool 8: Categorical GIS & Topographical Landscape Profiler
# =============================================================================
@mcp.tool(
    name="analyze_spatial_landcover_terrain",
    description="Analyze categorical LULC land-cover composition, 8-connectivity landscape patch fragmentation, DEM elevation/slope profiles, and execute zonal cross-tabulation against Tool 7 change masks."
)
def mcp_analyze_spatial_landcover_terrain(
    lulc_raster_path: str,
    dem_raster_path: Optional[str] = None,
    zone_mask_path: Optional[str] = None,
    class_legend: Optional[Dict[int, str]] = None,
    zone_legend: Optional[Dict[int, str]] = None,
    calculate_fragmentation: bool = True,
    output_dir: Optional[str] = None
) -> dict:
    try:
        req = SpatialLandcoverTerrainRequest(
            lulc_raster_path=lulc_raster_path,
            dem_raster_path=dem_raster_path,
            zone_mask_path=zone_mask_path,
            class_legend=class_legend,
            zone_legend=zone_legend,
            calculate_fragmentation=calculate_fragmentation,
            output_dir=output_dir
        )
        return analyze_spatial_landcover_terrain(req)
    except ValueError as e:
        return {"status": "error", "error": {"type": "validation_error", "message": str(e)}}
    except Exception as e:
        return {"status": "error", "error": {"type": "service_error", "message": str(e)}}


# =============================================================================
# Tool 9: Ground Truth, Event Context & Geospatial Web Intelligence
# =============================================================================
@mcp.tool(
    name="fetch_web_intelligence",
    description="Fetch ground-truth real-world context, event causes, disaster reports, infrastructure project names, and location background via web search (Tavily AI with automatic DuckDuckGo fail-safe fallback)."
)
def mcp_fetch_web_intelligence(
    query: str,
    max_results: int = 5,
    search_depth: Literal["basic", "advanced"] = "basic",
    include_domains: Optional[list[str]] = None,
    exclude_domains: Optional[list[str]] = None,
    location_hint: Optional[str] = None,
    bbox: Optional[list[float]] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> dict:
    try:
        req = WebIntelligenceRequest(
            query=query,
            max_results=max_results,
            search_depth=search_depth,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            location_hint=location_hint,
            bbox=bbox,
            latitude=latitude,
            longitude=longitude,
        )
        return fetch_web_intelligence(req)
    except ValueError as e:
        return {"status": "error", "error": {"type": "validation_error", "message": str(e)}}
    except Exception as e:
        return {"status": "error", "error": {"type": "service_error", "message": str(e)}}


# =============================================================================
# Tool 10: Spatial Geocoding & POI Discovery Engine
# =============================================================================
@mcp.tool(
    name="spatial_geocoding_poi",
    description="Forward & reverse geocoding, scene identity resolution, and in-AOI POI discovery -- mode is inferred automatically from whichever of query/latitude+longitude/bbox is supplied, or set explicitly."
)
def mcp_spatial_geocoding_poi(
    mode: Literal["forward", "reverse", "scene_identity", "poi_discovery", "auto"] = "auto",
    query: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    bbox: Optional[list[float]] = None,
    geotiff_path: Optional[str] = None,
    poi_categories: Optional[list[str]] = None,
    max_results: int = 15,
    zoom: Optional[int] = None,
    viewbox_clamping: bool = True,
) -> dict:
    try:
        req = SpatialGeocodingRequest(
            mode=mode,
            query=query,
            latitude=latitude,
            longitude=longitude,
            bbox=bbox,
            geotiff_path=geotiff_path,
            poi_categories=poi_categories,
            max_results=max_results,
            zoom=zoom,
            viewbox_clamping=viewbox_clamping,
        )
        return fetch_spatial_geocoding_poi(req)
    except ValueError as e:
        return {"status": "error", "error": {"type": "validation_error", "message": str(e)}}
    except Exception as e:
        return {"status": "error", "error": {"type": "service_error", "message": str(e)}}


# =============================================================================
# Tool 11: Deterministic Affine Projector & Markup Engine
# =============================================================================
@mcp.tool(
    name="deterministic_affine_markup",
    description="Deterministic inverse affine coordinate projection and high-contrast visual badge markup -- projects known lat/long features onto a GeoTIFF's exact pixel grid with zero hallucination probability."
)
def mcp_deterministic_affine_markup(
    geotiff_path: str,
    features: list[dict[str, Any]],
    base_image_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    draw_pill_badges: bool = True,
    draw_bounding_boxes: bool = True,
) -> dict:
    try:
        feature_objects = [FeatureItem(**f) for f in features]
        req = AffineMarkupRequest(
            geotiff_path=geotiff_path,
            features=feature_objects,
            base_image_path=base_image_path,
            output_dir=output_dir,
            draw_pill_badges=draw_pill_badges,
            draw_bounding_boxes=draw_bounding_boxes,
        )
        return project_and_markup_raster(req)
    except ValueError as e:
        return {"status": "error", "error": {"type": "validation_error", "message": str(e)}}
    except Exception as e:
        return {"status": "error", "error": {"type": "service_error", "message": str(e)}}


if __name__ == "__main__":
    print("=== SatQuery Unified FastMCP Server Initialized ===")
    print("Available Tools Registered: 11/11")
    print("1. fetch_optical_imagery")
    print("2. fetch_multispectral_imagery")
    print("3. fetch_sar_imagery")
    print("4. fetch_weather_environment")
    print("5. compute_vegetation_indices")
    print("6. inspect_geotiff_metadata")
    print("7. analyze_temporal_change")
    print("8. analyze_spatial_landcover_terrain")
    print("9. fetch_web_intelligence")
    print("10. spatial_geocoding_poi")
    print("11. deterministic_affine_markup")
    mcp.run()
