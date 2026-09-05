"""SatQuery Unified FastMCP Production Server.

Exposes the complete 8-Tool Earth Observation & Spatial Intelligence Suite
under a single unified FastMCP interface with comprehensive validation and error trapping.
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Literal, Optional, Union, Any

from fastmcp import FastMCP

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

# Initialize Master FastMCP Server
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


if __name__ == "__main__":
    print("=== SatQuery Unified FastMCP Server Initialized ===")
    print("Available Tools Registered: 8/8")
    print("1. fetch_optical_imagery")
    print("2. fetch_multispectral_imagery")
    print("3. fetch_sar_imagery")
    print("4. fetch_weather_environment")
    print("5. compute_vegetation_indices")
    print("6. inspect_geotiff_metadata")
    print("7. analyze_temporal_change")
    print("8. analyze_spatial_landcover_terrain")
    mcp.run()
