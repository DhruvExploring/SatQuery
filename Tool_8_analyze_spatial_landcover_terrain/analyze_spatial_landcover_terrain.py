"""Tool 8: analyze_spatial_landcover_terrain (Categorical LULC & Topographic Landscape Engine)

Performs categorical land-use / land-cover (LULC) composition accounting,
landscape patch fragmentation metrics (8-connectivity), and continuous DEM terrain/slope profiling.
Provides seamless downstream zonal cross-tabulation with Tool 7 change masks
(e.g., cross-referencing deforestation/flood footprints against specific landcover classes and slope profiles).
"""

import io
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Tuple, Union, Any

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject, transform_bounds
from scipy import ndimage
from pydantic import BaseModel, Field, field_validator
from fastmcp import FastMCP


# =============================================================================
# 1. Standard Ontologies & Pydantic Request Model
# =============================================================================

DEFAULT_WORLDCOVER_LEGEND: Dict[int, str] = {
    10: "Tree cover",
    20: "Shrubland",
    30: "Grassland",
    40: "Cropland",
    50: "Built-up",
    60: "Bare / sparse vegetation",
    70: "Snow and ice",
    80: "Permanent water bodies",
    90: "Herbaceous wetland",
    95: "Mangroves",
    100: "Moss and lichen",
}

# Classes for which landscape fragmentation (patch geometry) is ecologically meaningful
DEFAULT_FRAGMENTATION_CLASSES = {10, 20, 30, 40, 90, 95}


class SpatialLandcoverTerrainRequest(BaseModel):
    lulc_raster_path: str = Field(
        ...,
        description="Path to classified land-cover GeoTIFF raster (e.g., ESA WorldCover 10m)"
    )
    dem_raster_path: Optional[str] = Field(
        default=None,
        description="Optional path to digital elevation model GeoTIFF (height in meters, e.g. Copernicus DEM 30m)"
    )
    zone_mask_path: Optional[str] = Field(
        default=None,
        description="Optional path to integer zone mask GeoTIFF (e.g. Tool 7 change_mask.tif with -1=Loss, 0=Stable, 1=Gain)"
    )
    class_legend: Optional[Dict[int, str]] = Field(
        default=None,
        description="Optional custom dictionary mapping integer pixel values to land-cover class names. Defaults to ESA WorldCover."
    )
    zone_legend: Optional[Dict[int, str]] = Field(
        default=None,
        description="Optional dictionary mapping zone mask integer IDs to descriptive labels (e.g. {-1: 'Significant Decrease', 0: 'Stable', 1: 'Significant Increase'})"
    )
    calculate_fragmentation: bool = Field(
        default=True,
        description="Whether to compute landscape patch metrics (patch count, mean patch size, largest patch index) for natural vegetation classes"
    )
    output_dir: Optional[str] = Field(
        default=None,
        description="Optional custom output directory for exported reports or products"
    )

    @field_validator("lulc_raster_path")
    @classmethod
    def validate_lulc_path(cls, value: str) -> str:
        p = Path(value)
        if not p.exists() or not p.is_file():
            raise ValueError(f"LULC raster file does not exist: '{value}'")
        return str(p.resolve())

    @field_validator("dem_raster_path", "zone_mask_path")
    @classmethod
    def validate_optional_paths(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            p = Path(value)
            if not p.exists() or not p.is_file():
                raise ValueError(f"Specified raster file does not exist: '{value}'")
            return str(p.resolve())
        return None


# =============================================================================
# 2. Geodesic & Spatial Harmonization Utilities
# =============================================================================

def calculate_pixel_dimensions_m(
    crs: rasterio.crs.CRS,
    res_x: float,
    res_y: float,
    bounds: rasterio.coords.BoundingBox
) -> Tuple[float, float, float]:
    """Calculates pixel width (m), pixel height (m), and pixel area (m^2)."""
    if crs and crs.is_geographic:
        lat_mid = (bounds.bottom + bounds.top) / 2.0
        deg_to_m_lat = 111132.954 - 559.822 * np.cos(2 * np.radians(lat_mid)) + 1.175 * np.cos(4 * np.radians(lat_mid))
        deg_to_m_lon = 111412.84 * np.cos(np.radians(lat_mid)) - 93.5 * np.cos(3 * np.radians(lat_mid))
        pixel_w_m = float(abs(res_x) * deg_to_m_lon)
        pixel_h_m = float(abs(res_y) * deg_to_m_lat)
        return pixel_w_m, pixel_h_m, float(pixel_w_m * pixel_h_m)
    elif crs and crs.is_projected:
        pixel_w_m = float(abs(res_x))
        pixel_h_m = float(abs(res_y))
        return pixel_w_m, pixel_h_m, float(pixel_w_m * pixel_h_m)
    else:
        lat_mid = (bounds.bottom + bounds.top) / 2.0 if bounds else 0.0
        km_lon = 111.320 * np.cos(np.radians(lat_mid)) * abs(res_x)
        km_lat = 110.574 * abs(res_y)
        pixel_w_m = km_lon * 1000.0
        pixel_h_m = km_lat * 1000.0
        return pixel_w_m, pixel_h_m, float(pixel_w_m * pixel_h_m)


def read_and_align_raster(
    target_path: str,
    ref_meta: dict,
    resampling_method: Resampling,
    dtype: np.dtype = np.float32,
    nodata_out: Optional[float] = None
) -> Tuple[np.ndarray, bool]:
    """Reads a raster and on-the-fly reprojects it to match the reference grid if needed."""
    with rasterio.open(target_path) as src:
        src_arr = src.read(1)
        src_nodata = src.nodata

        needs_reproject = bool(
            src.crs != ref_meta["crs"] or
            src.width != ref_meta["width"] or
            src.height != ref_meta["height"] or
            not np.allclose(list(src.transform), list(ref_meta["transform"]), rtol=1e-5, atol=1e-8)
        )

        if not needs_reproject:
            out_arr = src_arr.astype(dtype)
            if src_nodata is not None and nodata_out is not None:
                out_arr[src_arr == src_nodata] = nodata_out
            return out_arr, False

        # Prepare destination grid
        destination = np.full((ref_meta["height"], ref_meta["width"]), nodata_out if nodata_out is not None else 0, dtype=dtype)
        
        reproject(
            source=src_arr,
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src_nodata,
            dst_transform=ref_meta["transform"],
            dst_crs=ref_meta["crs"],
            dst_nodata=nodata_out,
            resampling=resampling_method
        )
        return destination, True


# =============================================================================
# 3. Terrain Slope & Geomorphometry Engine
# =============================================================================

def compute_terrain_slope(
    dem_arr: np.ndarray,
    dx_m: float,
    dy_m: float,
    valid_mask: np.ndarray
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Calculates terrain slope in degrees using 2D spatial gradients."""
    # Compute central difference spatial gradients
    dz_dy, dz_dx = np.gradient(dem_arr, dy_m, dx_m)
    
    # Slope angle in radians: theta = arctan(sqrt( (dz/dx)^2 + (dz/dy)^2 ))
    slope_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
    slope_deg = np.degrees(slope_rad).astype(np.float32)
    slope_deg[~valid_mask] = np.nan

    finite_slope_mask = valid_mask & np.isfinite(slope_deg)
    valid_slopes = slope_deg[finite_slope_mask]
    if valid_slopes.size == 0:
        return slope_deg, {}

    # Slope classification breakdown (FAO / USGS standard)
    total_valid = valid_slopes.size
    flat_gentle = int(np.count_nonzero(valid_slopes < 5.0))
    moderate = int(np.count_nonzero((valid_slopes >= 5.0) & (valid_slopes < 15.0)))
    steep = int(np.count_nonzero((valid_slopes >= 15.0) & (valid_slopes < 30.0)))
    very_steep = int(np.count_nonzero(valid_slopes >= 30.0))

    slope_stats = {
        "mean_slope_deg": round(float(np.mean(valid_slopes)), 2),
        "median_slope_deg": round(float(np.median(valid_slopes)), 2),
        "min_slope_deg": round(float(np.min(valid_slopes)), 2),
        "max_slope_deg": round(float(np.max(valid_slopes)), 2),
        "std_slope_deg": round(float(np.std(valid_slopes)), 2),
        "slope_classes": {
            "flat_to_gentle_0_to_5_deg": {
                "pixel_count": flat_gentle,
                "percentage": round(float(flat_gentle / total_valid * 100.0), 2)
            },
            "moderate_5_to_15_deg": {
                "pixel_count": moderate,
                "percentage": round(float(moderate / total_valid * 100.0), 2)
            },
            "steep_15_to_30_deg": {
                "pixel_count": steep,
                "percentage": round(float(steep / total_valid * 100.0), 2)
            },
            "very_steep_above_30_deg": {
                "pixel_count": very_steep,
                "percentage": round(float(very_steep / total_valid * 100.0), 2)
            }
        }
    }
    return slope_deg, slope_stats


# =============================================================================
# 4. Landscape Patch Fragmentation Engine
# =============================================================================

def compute_patch_fragmentation(
    class_mask: np.ndarray,
    pixel_area_km2: float,
    pixel_area_ha: float
) -> Dict[str, Any]:
    """Computes landscape fragmentation metrics using 8-connectivity contiguous labeling."""
    # 8-connectivity structuring element
    structure = np.ones((3, 3), dtype=int)
    labeled_array, num_features = ndimage.label(class_mask, structure=structure)
    
    total_class_pixels = int(np.sum(class_mask))
    if num_features == 0 or total_class_pixels == 0:
        return {
            "patch_count": 0,
            "mean_patch_size_km2": 0.0,
            "mean_patch_size_hectares": 0.0,
            "largest_patch_index_percent": 0.0,
            "fragmentation_level": "None"
        }

    # Measure patch sizes
    patch_sizes = ndimage.sum(class_mask, labeled_array, range(1, num_features + 1))
    max_patch_pixels = float(np.max(patch_sizes)) if len(patch_sizes) > 0 else 0.0
    
    mean_patch_km2 = round((total_class_pixels * pixel_area_km2) / num_features, 4)
    mean_patch_ha = round((total_class_pixels * pixel_area_ha) / num_features, 2)
    lpi_percent = round((max_patch_pixels / total_class_pixels) * 100.0, 2)

    # Heuristic fragmentation classification
    if num_features == 1 or lpi_percent > 75.0:
        frag_level = "Continuous / Low Fragmentation"
    elif lpi_percent > 35.0:
        frag_level = "Moderately Fragmented"
    else:
        frag_level = "Highly Fragmented / Dispersed"

    return {
        "patch_count": int(num_features),
        "mean_patch_size_km2": mean_patch_km2,
        "mean_patch_size_hectares": mean_patch_ha,
        "largest_patch_index_percent": lpi_percent,
        "fragmentation_level": frag_level
    }


# =============================================================================
# 5. Core Execution Engine: analyze_spatial_landcover_terrain
# =============================================================================

def analyze_spatial_landcover_terrain(req: SpatialLandcoverTerrainRequest) -> Dict[str, Any]:
    """Main execution function for Tool 8."""
    lulc_path = Path(req.lulc_raster_path)
    legend = req.class_legend if req.class_legend is not None else DEFAULT_WORLDCOVER_LEGEND
    
    # 1. Establish Master Reference Grid
    # If zone_mask is provided, prefer zone_mask grid; otherwise use LULC grid
    resampling_actions = []
    
    ref_path = Path(req.zone_mask_path) if req.zone_mask_path else lulc_path
    with rasterio.open(ref_path) as ref_src:
        ref_meta = {
            "crs": ref_src.crs,
            "width": ref_src.width,
            "height": ref_src.height,
            "transform": ref_src.transform,
            "bounds": ref_src.bounds,
            "res": ref_src.res
        }

    # 2. Read and Align LULC Raster (Nearest Neighbor)
    lulc_arr, lulc_resampled = read_and_align_raster(
        str(lulc_path),
        ref_meta,
        resampling_method=Resampling.nearest,
        dtype=np.int32,
        nodata_out=-1
    )
    if lulc_resampled:
        resampling_actions.append({
            "raster": "lulc_raster",
            "source_file": lulc_path.name,
            "method": "nearest_neighbor",
            "reason": "Harmonized to master reference grid"
        })

    valid_lulc_mask = (lulc_arr >= 0)
    total_pixels = int(ref_meta["width"] * ref_meta["height"])
    valid_pixels = int(np.sum(valid_lulc_mask))

    if valid_pixels == 0:
        return {
            "status": "error",
            "error_code": "NO_VALID_LULC_DATA",
            "message": f"The LULC raster at '{lulc_path.name}' contains zero valid land-cover pixels.",
            "total_pixels": total_pixels
        }

    # 3. Ground Resolution & Geodesic Surface Accounting
    pixel_w_m, pixel_h_m, pixel_area_m2 = calculate_pixel_dimensions_m(
        ref_meta["crs"],
        ref_meta["res"][0],
        ref_meta["res"][1],
        ref_meta["bounds"]
    )
    pixel_area_km2 = pixel_area_m2 / 1e6
    pixel_area_ha = pixel_area_m2 / 1e4

    total_aoi_km2 = round(total_pixels * pixel_area_km2, 4)
    valid_aoi_km2 = round(valid_pixels * pixel_area_km2, 4)

    # 4. Global LULC Composition & Patch Fragmentation
    unique_classes, counts = np.unique(lulc_arr[valid_lulc_mask], return_counts=True)
    
    lulc_composition = {}
    fragmentation_metrics = {}
    dominant_class = {"code": None, "name": "None", "area_km2": 0.0, "percentage": 0.0}

    for code, cnt in zip(unique_classes, counts):
        code_int = int(code)
        c_name = legend.get(code_int, f"Class_{code_int}")
        c_km2 = round(cnt * pixel_area_km2, 4)
        c_ha = round(cnt * pixel_area_ha, 2)
        c_pct = round((cnt / valid_pixels) * 100.0, 2)

        lulc_composition[str(code_int)] = {
            "class_name": c_name,
            "pixel_count": int(cnt),
            "area_km2": c_km2,
            "area_hectares": c_ha,
            "percentage_of_valid_aoi": c_pct
        }

        if c_km2 > dominant_class["area_km2"]:
            dominant_class = {
                "code": code_int,
                "name": c_name,
                "area_km2": c_km2,
                "percentage": c_pct
            }

        # Fragmentation for natural vegetation classes
        if req.calculate_fragmentation and (code_int in DEFAULT_FRAGMENTATION_CLASSES or "tree" in c_name.lower() or "crop" in c_name.lower()):
            binary_class_mask = (lulc_arr == code_int)
            frag_res = compute_patch_fragmentation(binary_class_mask, pixel_area_km2, pixel_area_ha)
            fragmentation_metrics[c_name] = frag_res

    # 5. Topographic & DEM Terrain Profiling (if DEM provided)
    dem_profile = None
    slope_array = None
    if req.dem_raster_path:
        dem_path = Path(req.dem_raster_path)
        dem_arr, dem_resampled = read_and_align_raster(
            str(dem_path),
            ref_meta,
            resampling_method=Resampling.bilinear,
            dtype=np.float32,
            nodata_out=np.nan
        )
        if dem_resampled:
            resampling_actions.append({
                "raster": "dem_raster",
                "source_file": dem_path.name,
                "method": "bilinear",
                "reason": "Resampled to master reference grid"
            })

        valid_dem_mask = valid_lulc_mask & np.isfinite(dem_arr)
        if np.any(valid_dem_mask):
            valid_elevations = dem_arr[valid_dem_mask]
            
            # Slope calculation
            slope_array, slope_summary = compute_terrain_slope(
                dem_arr,
                dx_m=pixel_w_m,
                dy_m=pixel_h_m,
                valid_mask=valid_dem_mask
            )

            p05_elev, p25_elev, p75_elev, p95_elev = np.percentile(valid_elevations, [5, 25, 75, 95])
            
            dem_profile = {
                "source_dem_file": dem_path.name,
                "elevation_meters": {
                    "mean_elevation_m": round(float(np.mean(valid_elevations)), 2),
                    "median_elevation_m": round(float(np.median(valid_elevations)), 2),
                    "min_elevation_m": round(float(np.min(valid_elevations)), 2),
                    "max_elevation_m": round(float(np.max(valid_elevations)), 2),
                    "std_elevation_m": round(float(np.std(valid_elevations)), 2),
                    "percentiles_m": {
                        "p05": round(float(p05_elev), 2),
                        "p25": round(float(p25_elev), 2),
                        "p75": round(float(p75_elev), 2),
                        "p95": round(float(p95_elev), 2)
                    }
                },
                "slope_profile": slope_summary
            }

    # 6. Zonal Cross-Tabulation Engine (The Tool 7 Handshake)
    zonal_cross_tabulation = None
    if req.zone_mask_path:
        mask_path = Path(req.zone_mask_path)
        zone_arr, mask_resampled = read_and_align_raster(
            str(mask_path),
            ref_meta,
            resampling_method=Resampling.nearest,
            dtype=np.int32,
            nodata_out=-128
        )
        if mask_resampled:
            resampling_actions.append({
                "raster": "zone_mask",
                "source_file": mask_path.name,
                "method": "nearest_neighbor",
                "reason": "Harmonized to master reference grid"
            })

        # Default Zone Labels (Handshake with Tool 7 change_mask.tif)
        default_zone_legend = {
            -2: "Major Loss / Severe Disturbance",
            -1: "Significant Decrease / Loss",
            0: "Stable / Unaltered",
            1: "Significant Increase / Gain",
            2: "Major Gain / Rapid Emergence"
        }
        active_zone_legend = req.zone_legend if req.zone_legend else default_zone_legend

        valid_zone_mask = valid_lulc_mask & (zone_arr != -128)
        unique_zones, zone_counts = np.unique(zone_arr[valid_zone_mask], return_counts=True)

        zonal_cross_tabulation = {}
        for z_code, z_count in zip(unique_zones, zone_counts):
            z_int = int(z_code)
            z_label = active_zone_legend.get(z_int, f"Zone_{z_int}")
            z_mask_bool = valid_zone_mask & (zone_arr == z_int)
            
            z_area_km2 = round(z_count * pixel_area_km2, 4)
            z_area_ha = round(z_count * pixel_area_ha, 2)
            z_pct_aoi = round((z_count / valid_pixels) * 100.0, 2)

            # LULC breakdown inside this zone
            zone_lulc_classes, zone_lulc_counts = np.unique(lulc_arr[z_mask_bool], return_counts=True)
            zone_class_breakdown = {}
            for z_c_code, z_c_count in zip(zone_lulc_classes, zone_lulc_counts):
                zc_int = int(z_c_code)
                zc_name = legend.get(zc_int, f"Class_{zc_int}")
                zc_km2 = round(z_c_count * pixel_area_km2, 4)
                zc_ha = round(z_c_count * pixel_area_ha, 2)
                zc_pct_zone = round((z_c_count / z_count) * 100.0, 2)
                
                zone_class_breakdown[zc_name] = {
                    "class_code": zc_int,
                    "pixel_count": int(z_c_count),
                    "area_km2": zc_km2,
                    "area_hectares": zc_ha,
                    "percentage_of_zone": zc_pct_zone
                }

            # Optional Topographic Profile per Zone
            zone_topo = {}
            if req.dem_raster_path and dem_profile is not None:
                zone_dem_mask = z_mask_bool & np.isfinite(dem_arr)
                if np.any(zone_dem_mask):
                    zone_elevs = dem_arr[zone_dem_mask]
                    zone_topo["mean_elevation_m"] = round(float(np.mean(zone_elevs)), 2)
                    zone_topo["min_elevation_m"] = round(float(np.min(zone_elevs)), 2)
                    zone_topo["max_elevation_m"] = round(float(np.max(zone_elevs)), 2)
                
                if slope_array is not None:
                    zone_slopes = slope_array[zone_dem_mask]
                    valid_zone_slopes = zone_slopes[np.isfinite(zone_slopes)]
                    if valid_zone_slopes.size > 0:
                        zone_topo["mean_slope_deg"] = round(float(np.mean(valid_zone_slopes)), 2)

            zonal_cross_tabulation[str(z_int)] = {
                "zone_label": z_label,
                "total_pixel_count": int(z_count),
                "total_area_km2": z_area_km2,
                "total_area_hectares": z_area_ha,
                "percentage_of_aoi": z_pct_aoi,
                "landcover_impact_breakdown": zone_class_breakdown,
                "topography": zone_topo if zone_topo else None
            }

    # 7. Construct Final Standardized JSON Payload
    result_payload = {
        "status": "success",
        "tool": "Tool_8_analyze_spatial_landcover_terrain",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "lulc_raster_file": lulc_path.name,
            "dem_raster_file": Path(req.dem_raster_path).name if req.dem_raster_path else None,
            "zone_mask_file": Path(req.zone_mask_path).name if req.zone_mask_path else None,
            "crs": str(ref_meta["crs"]) if ref_meta["crs"] else "UNREFERENCED",
            "grid_dimensions": {"width": ref_meta["width"], "height": ref_meta["height"]},
            "spatial_bounds": {
                "left": round(ref_meta["bounds"].left, 6),
                "bottom": round(ref_meta["bounds"].bottom, 6),
                "right": round(ref_meta["bounds"].right, 6),
                "top": round(ref_meta["bounds"].top, 6)
            },
            "pixel_ground_resolution_m": {
                "width_m": round(pixel_w_m, 2),
                "height_m": round(pixel_h_m, 2),
                "area_m2": round(pixel_area_m2, 2)
            },
            "resampling_actions": resampling_actions
        },
        "spatial_coverage": {
            "total_raster_area_km2": total_aoi_km2,
            "valid_aoi_area_km2": valid_aoi_km2,
            "valid_fraction_percent": round((valid_pixels / total_pixels) * 100.0, 2),
            "total_pixels": total_pixels,
            "valid_pixels": valid_pixels,
            "nodata_pixels": total_pixels - valid_pixels
        },
        "dominant_landcover": dominant_class,
        "landcover_composition": lulc_composition,
        "landscape_fragmentation": fragmentation_metrics if fragmentation_metrics else None,
        "terrain_profile": dem_profile,
        "zonal_cross_tabulation": zonal_cross_tabulation
    }
    return result_payload


# =============================================================================
# 6. FastMCP Tool Registration & CLI Adapter
# =============================================================================

mcp = FastMCP("Tool 8: Spatial Landcover & Terrain Analysis Server")

@mcp.tool(
    name="analyze_spatial_landcover_terrain",
    description="Analyze categorical LULC land cover composition, patch fragmentation metrics, DEM elevation and terrain slope profiles, with zonal cross-tabulation against Tool 7 change masks.",
)
def analyze_spatial_landcover_terrain_mcp(
    lulc_raster_path: str,
    dem_raster_path: Optional[str] = None,
    zone_mask_path: Optional[str] = None,
    calculate_fragmentation: bool = True,
    output_dir: Optional[str] = None,
) -> dict:
    try:
        req = SpatialLandcoverTerrainRequest(
            lulc_raster_path=lulc_raster_path,
            dem_raster_path=dem_raster_path,
            zone_mask_path=zone_mask_path,
            calculate_fragmentation=calculate_fragmentation,
            output_dir=output_dir,
        )
        return analyze_spatial_landcover_terrain(req)
    except ValueError as e:
        return {"status": "error", "error": {"type": "validation_error", "message": str(e)}}
    except Exception as e:
        return {"status": "error", "error": {"type": "service_error", "message": str(e)}}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        input_file = Path(sys.argv[1])
        if input_file.exists():
            with open(input_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            req = SpatialLandcoverTerrainRequest(**data)
            res = analyze_spatial_landcover_terrain(req)
            print(json.dumps(res, indent=2))
        else:
            print(f"Error: input file '{input_file}' not found.", file=sys.stderr)
            sys.exit(1)
    else:
        print("Tool 8: analyze_spatial_landcover_terrain ready. Pass a JSON configuration file or run via FastMCP.")
