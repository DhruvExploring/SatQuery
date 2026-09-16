"""Tool 6: inspect_geotiff_metadata (Universal Deep Raster QA & Inspector)

Provides universal pre-flight raster inspection and deep geospatial metadata extraction
for any incoming GeoTIFF (from internal tools or external user uploads).
Verifies georeferencing, data types, NoData/NaN integrity, radiometric distributions,
and cross-raster grid alignment compatibility for downstream ML/LLM analysis.
"""

import io
import json
import logging
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Literal, Optional, List, Dict, Any, Tuple

import numpy as np
import rasterio
from rasterio.warp import transform_bounds

logger = logging.getLogger("satquery.tool6_inspect_geotiff_metadata")
from pydantic import BaseModel, Field, field_validator, model_validator
try:
    from fastmcp import FastMCP
except (ImportError, Exception):
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        FastMCP = None


# =============================================================================
# 1. Request Validation Model
# =============================================================================

class GeoTIFFInspectionRequest(BaseModel):
    file_path: str = Field(..., description="Absolute path to the GeoTIFF file to inspect")
    compare_with: Optional[str] = Field(default=None, description="Optional second GeoTIFF path to verify grid compatibility")
    calculate_statistics: bool = Field(default=True, description="Calculate per-band statistical percentiles and distributions")
    calculate_histogram: bool = Field(default=True, description="Generate compact histogram bins for spectral reasoning")

    @field_validator("file_path")
    @classmethod
    def validate_file_exists(cls, value):
        p = Path(value)
        if not p.exists() or not p.is_file():
            raise ValueError(f"Target GeoTIFF file does not exist at '{value}'.")
        return str(p.resolve())

    @field_validator("compare_with")
    @classmethod
    def validate_compare_file_exists(cls, value):
        if value is not None:
            p = Path(value)
            if not p.exists() or not p.is_file():
                raise ValueError(f"Comparison GeoTIFF file does not exist at '{value}'.")
            return str(p.resolve())
        return None


# =============================================================================
# 2. Core Deep Raster Inspection Engine
# =============================================================================

def inspect_geotiff_metadata(req: GeoTIFFInspectionRequest) -> dict:
    p = Path(req.file_path)
    
    with rasterio.open(p) as src:
        width = src.width
        height = src.height
        total_pixels = width * height
        band_count = src.count
        crs = src.crs
        crs_str = str(crs) if crs else "UNREFERENCED"
        is_geographic = crs.is_geographic if crs else False
        is_projected = crs.is_projected if crs else False
        
        bounds_native = {"left": src.bounds.left, "bottom": src.bounds.bottom, "right": src.bounds.right, "top": src.bounds.top}
        if crs:
            try:
                wgs84_bounds_tuple = transform_bounds(crs, "EPSG:4326", *src.bounds)
                bounds_wgs84 = {
                    "min_lon": round(wgs84_bounds_tuple[0], 6),
                    "min_lat": round(wgs84_bounds_tuple[1], 6),
                    "max_lon": round(wgs84_bounds_tuple[2], 6),
                    "max_lat": round(wgs84_bounds_tuple[3], 6),
                }
            except Exception:
                bounds_wgs84 = None
        else:
            bounds_wgs84 = None
            
        res_x, res_y = src.res
        unit_str = "degrees" if is_geographic else ("meters" if is_projected else "pixels")
        
        if bounds_wgs84:
            lat_mid = (bounds_wgs84["min_lat"] + bounds_wgs84["max_lat"]) / 2.0
            deg_to_m_lat = 111132.954 - 559.822 * np.cos(2 * np.radians(lat_mid)) + 1.175 * np.cos(4 * np.radians(lat_mid))
            deg_to_m_lon = 111412.84 * np.cos(np.radians(lat_mid)) - 93.5 * np.cos(3 * np.radians(lat_mid))
            width_m = abs(bounds_wgs84["max_lon"] - bounds_wgs84["min_lon"]) * deg_to_m_lon
            height_m = abs(bounds_wgs84["max_lat"] - bounds_wgs84["min_lat"]) * deg_to_m_lat
            approx_area_km2 = round((width_m * height_m) / 1e6, 2)
        else:
            approx_area_km2 = None

        # Per-pixel WGS84 resolution and the four scene corners -- lets a
        # caller convert any pixel-space region (e.g. a box a user drew on a
        # rendered preview, as a fraction of image width/height) into exact
        # real-world coordinates without re-deriving this math itself.
        # Exact for a north-up raster (every GeoTIFF this project's own
        # fetch/analysis tools produce); for a rotated/skewed raster this is
        # still the best available linear approximation from the bounding
        # envelope alone -- deterministic_affine_markup (Tool 11) is the
        # source of truth for a single point's exact pixel location via the
        # raster's real affine transform.
        if bounds_wgs84 and width > 0 and height > 0:
            pixel_size_wgs84_degrees = {
                "lon_per_pixel": round((bounds_wgs84["max_lon"] - bounds_wgs84["min_lon"]) / width, 10),
                "lat_per_pixel": round((bounds_wgs84["max_lat"] - bounds_wgs84["min_lat"]) / height, 10),
            }
            corners_wgs84 = {
                "top_left": {"latitude": bounds_wgs84["max_lat"], "longitude": bounds_wgs84["min_lon"]},
                "top_right": {"latitude": bounds_wgs84["max_lat"], "longitude": bounds_wgs84["max_lon"]},
                "bottom_left": {"latitude": bounds_wgs84["min_lat"], "longitude": bounds_wgs84["min_lon"]},
                "bottom_right": {"latitude": bounds_wgs84["min_lat"], "longitude": bounds_wgs84["max_lon"]},
            }
        else:
            pixel_size_wgs84_degrees = None
            corners_wgs84 = None
            
        bands_info = []
        band_stats = {}
        histograms = {}
        has_nan_global = False
        has_inf_global = False
        has_nodata_pixels_global = False
        has_nodata_holes_global = False
        empty_bands = []
        constant_bands = []
        
        for b_idx in range(1, band_count + 1):
            dtype_str = str(src.dtypes[b_idx - 1])
            desc = src.descriptions[b_idx - 1] or f"Band_{b_idx}"
            arr = src.read(b_idx)
            
            nodata_val = src.nodata
            if nodata_val is not None:
                nodata_mask = (arr == nodata_val)
            else:
                nodata_mask = np.zeros_like(arr, dtype=bool)
                
            nan_mask = np.isnan(arr) if np.issubdtype(arr.dtype, np.floating) else np.zeros_like(arr, dtype=bool)
            inf_mask = np.isinf(arr) if np.issubdtype(arr.dtype, np.floating) else np.zeros_like(arr, dtype=bool)
            
            invalid_mask = nodata_mask | nan_mask | inf_mask
            valid_arr = arr[~invalid_mask]
            
            nan_count = int(np.count_nonzero(nan_mask))
            inf_count = int(np.count_nonzero(inf_mask))
            nodata_count = int(np.count_nonzero(nodata_mask))
            valid_count = int(valid_arr.size)
            valid_frac = round(float(valid_count / total_pixels), 4)
            
            if nan_count > 0:
                has_nan_global = True
            if inf_count > 0:
                has_inf_global = True
            if nodata_count > 0:
                has_nodata_pixels_global = True
            if valid_count == 0:
                empty_bands.append(b_idx)
            
            if nodata_count > 0 and valid_count > 0:
                # Interior border-margin heuristic: checks for NoData pixels away from outer borders
                interior_mask = invalid_mask[1:-1, 1:-1]
                if np.any(interior_mask):
                    has_nodata_holes_global = True
            
            bands_info.append({
                "band_index": b_idx,
                "description": desc,
                "dtype": dtype_str,
                "valid_pixel_count": valid_count,
                "valid_pixel_fraction": valid_frac,
                "nodata_pixel_count": nodata_count,
                "nan_pixel_count": nan_count,
                "inf_pixel_count": inf_count,
            })
            
            if req.calculate_statistics and valid_count > 0:
                min_v = float(np.min(valid_arr))
                max_v = float(np.max(valid_arr))
                if min_v == max_v:
                    constant_bands.append(b_idx)
                
                band_stats[desc] = {
                    "min": round(min_v, 4),
                    "max": round(max_v, 4),
                    "mean": round(float(np.mean(valid_arr)), 4),
                    "median": round(float(np.median(valid_arr)), 4),
                    "std_dev": round(float(np.std(valid_arr)), 4),
                    "p01": round(float(np.percentile(valid_arr, 1)), 4),
                    "p05": round(float(np.percentile(valid_arr, 5)), 4),
                    "p25": round(float(np.percentile(valid_arr, 25)), 4),
                    "p50": round(float(np.percentile(valid_arr, 50)), 4),
                    "p75": round(float(np.percentile(valid_arr, 75)), 4),
                    "p95": round(float(np.percentile(valid_arr, 95)), 4),
                    "p99": round(float(np.percentile(valid_arr, 99)), 4),
                }
                
                if req.calculate_histogram:
                    try:
                        # range=(min_v, max_v) is passed explicitly (not left
                        # for numpy to recompute) as a defensive measure
                        # against a numpy internal edge case (floating-point
                        # rounding can push a value's computed bin index one
                        # past the last bin in numpy's fast uniform-binning
                        # path, which numpy's own out-of-range correction
                        # doesn't catch -- observed as "operands could not be
                        # broadcast together" from deep inside
                        # numpy.lib.histograms). Still wrapped in try/except
                        # since that class of bug isn't fully preventable from
                        # here -- a display-only histogram must never abort
                        # inspection of an otherwise valid raster.
                        counts, bin_edges = np.histogram(valid_arr, bins=10, range=(min_v, max_v))
                        histograms[desc] = {
                            "bin_edges": [round(float(e), 4) for e in bin_edges],
                            "counts": [int(c) for c in counts],
                        }
                    except Exception as exc:
                        logger.warning(
                            "Histogram computation failed for band %r (%s): %r",
                            desc, b_idx, exc,
                        )
                        histograms[desc] = None
                    
        is_georef = bool(crs is not None and src.transform != rasterio.Affine.identity())
        min_valid_fraction = min(b["valid_pixel_fraction"] for b in bands_info) if bands_info else 0.0
        is_num_usable = bool(not empty_bands and not has_inf_global and min_valid_fraction > 0.5)
        is_valid_ml = bool(is_georef and is_num_usable)
        
        recommendations = []
        recommendations.append(f"Raster is georeferenced in {crs_str} ({unit_str}).")
        recommendations.append(f"Contains {band_count} band(s) with dimensions {width}x{height} pixels.")
        if is_valid_ml:
            recommendations.append("Raster passes data integrity checks and is ready for numerical analysis and ML workflows.")
        else:
            recommendations.append("Warning: Raster has integrity issues (unreferenced, missing values, or empty bands).")
            
        compatibility = None
        if req.compare_with:
            p_comp = Path(req.compare_with)
            if p_comp.exists() and p_comp.is_file():
                with rasterio.open(p_comp) as src2:
                    same_crs = bool(src.crs == src2.crs)
                    same_dims = bool(src.width == src2.width and src.height == src2.height)
                    same_res = bool(np.allclose(src.res, src2.res, rtol=1e-5, atol=1e-8))
                    same_bounds = bool(np.allclose([src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top],
                                                   [src2.bounds.left, src2.bounds.bottom, src2.bounds.right, src2.bounds.top], rtol=1e-5, atol=1e-8))
                    same_transform = bool(np.allclose(list(src.transform), list(src2.transform), rtol=1e-5, atol=1e-8))
                    pixelwise_ready = bool(same_crs and same_dims and same_res and same_transform)
                    
                    compatibility = {
                        "compared_with_file": p_comp.name,
                        "same_crs": same_crs,
                        "same_dimensions": same_dims,
                        "same_resolution": same_res,
                        "same_bounds": same_bounds,
                        "same_grid_alignment": same_transform,
                        "pixelwise_operation_ready": pixelwise_ready,
                        "note": "pixelwise_operation_ready confirms spatial grid alignment; scientific compatibility must be verified by task requirements."
                    }
                    if pixelwise_ready:
                        recommendations.append(f"Geometric pixel-wise grid operations with '{p_comp.name}' are fully aligned and supported.")
                    else:
                        recommendations.append(f"Warning: Grid mismatch with '{p_comp.name}'; re-projection or re-gridding is required.")
                        
        return {
            "status": "success",
            "file": {
                "file_name": p.name,
                "file_path": str(p),
                "file_size_bytes": p.stat().st_size,
                "driver": src.driver,
            },
            "spatial": {
                "crs": crs_str,
                "is_geographic": is_geographic,
                "is_projected": is_projected,
                "coordinate_units": unit_str,
                "resolution": {"x": res_x, "y": res_y, "unit": unit_str},
                "pixel_size_wgs84_degrees": pixel_size_wgs84_degrees,
                "corners_wgs84": corners_wgs84,
                "bounds_native": bounds_native,
                "bounds_wgs84": bounds_wgs84,
                "approx_area_km2": approx_area_km2,
                "transform": [round(float(v), 8) for v in src.transform],
            },
            "raster": {
                "width": width,
                "height": height,
                "total_pixels": total_pixels,
                "band_count": band_count,
                "block_shapes": [list(b) for b in src.block_shapes],
                "compression": src.compression.name if src.compression else "NONE",
                "nodata_definition": src.nodata,
            },
            "bands": bands_info,
            "statistics": band_stats,
            "histograms": histograms,
            "integrity": {
                "has_nodata_definition": src.nodata is not None,
                "contains_nodata_pixels": has_nodata_pixels_global,
                "has_nodata_holes": has_nodata_holes_global,
                "has_nan": has_nan_global,
                "has_inf": has_inf_global,
                "empty_bands": empty_bands,
                "constant_bands": constant_bands,
            },
            "compatibility": compatibility,
            "quality": {
                "is_readable": True,
                "is_georeferenced": is_georef,
                "is_numerically_usable": is_num_usable,
                "is_valid_for_ml": is_valid_ml,
                "ml_readiness_scope": "general numerical/raster processing compatibility; task-specific model constraints must be validated separately."
            },
            "recommendations": recommendations,
        }


# =============================================================================
# 3. FastMCP Tool Registration & CLI Entry Point
# =============================================================================

if FastMCP is None:
    class _DummyMCP:
        def tool(self, *args, **kwargs):
            return lambda fn: fn
    mcp = _DummyMCP()
else:
    mcp = FastMCP("Tool 6: Universal GeoTIFF QA & Metadata Inspector")

@mcp.tool(
    name="inspect_geotiff_metadata",
    description="Deeply inspect any incoming or existing GeoTIFF raster for spatial coordinate systems, data types, NoData/NaN integrity, radiometric distributions, and cross-raster grid compatibility.",
)
def mcp_inspect_geotiff_metadata(
    file_path: str,
    compare_with: Optional[str] = None,
    calculate_statistics: bool = True,
    calculate_histogram: bool = True,
) -> dict:
    try:
        req = GeoTIFFInspectionRequest(
            file_path=file_path,
            compare_with=compare_with,
            calculate_statistics=calculate_statistics,
            calculate_histogram=calculate_histogram,
        )
        return inspect_geotiff_metadata(req)
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
            req = GeoTIFFInspectionRequest(**data)
            res = inspect_geotiff_metadata(req)
            print(json.dumps(res, indent=2))
        else:
            print(f"Error: input file '{input_file}' not found.", file=sys.stderr)
            sys.exit(1)
    else:
        print("Tool 6: inspect_geotiff_metadata ready. Pass a JSON configuration file or run via FastMCP.")
