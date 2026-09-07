"""Tool 5: compute_vegetation_indices (Scientific Multi-Index Spectral Engine)

Transforms multispectral surface reflectance GeoTIFF rasters (from Tool 2 or external EO assets)
into calibrated multi-band scientific spectral index GeoTIFFs (NDVI, EVI, SAVI, GNDVI, NDRE_B5, NDRE_B7, NDMI, NDWI, MSAVI, NBR)
and produces comprehensive statistical distributions, exact ground sampling distance (GSD) resolution provenance,
and heuristic canopy vigor area coverage.
"""

import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional, List, Dict, Any, Tuple

import numpy as np
import rasterio
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

ALL_10_INDICES = ["NDVI", "EVI", "SAVI", "GNDVI", "NDRE_B5", "NDRE_B7", "NDMI", "NDWI", "MSAVI", "NBR"]
VALID_INDICES = set(ALL_10_INDICES)

class VegetationIndicesRequest(BaseModel):
    file_path: str = Field(..., description="Path to local multispectral GeoTIFF raster")
    indices: list[str] = Field(default=ALL_10_INDICES, description="List of spectral indices to compute")
    band_mapping: Optional[dict[str, str]] = Field(default=None, description="Mapping of band index/name to Sentinel-2 band code, e.g. {'Band_1': 'B02'}")
    calculate_heuristic_classification: bool = Field(default=True, description="Calculate rule-based heuristic canopy vigor area coverage in km2 and %")
    output_dir: Optional[str] = Field(default=None, description="Custom output directory")

    @field_validator("indices")
    @classmethod
    def validate_indices_list(cls, values):
        if not values:
            raise ValueError("indices list cannot be empty.")
        normalized = []
        for v in values:
            idx = v.upper().strip()
            if idx not in VALID_INDICES:
                raise ValueError(f"Unsupported index '{v}'. Supported indices are: {sorted(list(VALID_INDICES))}")
            normalized.append(idx)
        return normalized

    @field_validator("file_path")
    @classmethod
    def validate_file_exists(cls, value):
        p = Path(value)
        if not p.exists() or not p.is_file():
            raise ValueError(f"Input GeoTIFF file does not exist at '{value}'.")
        return str(p.resolve())


# =============================================================================
# 2. Spectral Band Discovery & Extraction Engine
# =============================================================================

NATIVE_BAND_RESOLUTIONS = {
    "B02": 10, "B03": 10, "B04": 10, "B08": 10,
    "B05": 20, "B06": 20, "B07": 20, "B8A": 20,
    "B11": 20, "B12": 20, "SCL": 20,
    "B01": 60, "B09": 60
}


def extract_spectral_bands(src: rasterio.DatasetReader, custom_mapping: dict | None) -> dict[str, np.ndarray]:
    band_dict = {}
    band_count = src.count
    default_8band_map = {1: "B02", 2: "B03", 3: "B04", 4: "B05", 5: "B07", 6: "B08", 7: "B11", 8: "B12"}
    default_6band_map = {1: "B02", 2: "B03", 3: "B04", 4: "B08", 5: "B11", 6: "B12"}
    
    mapping = {}
    if custom_mapping:
        for k, v in custom_mapping.items():
            match = re.search(r'\d+', str(k))
            if match:
                mapping[int(match.group(0))] = v.upper().strip()
    else:
        for i in range(1, band_count + 1):
            desc = src.descriptions[i - 1]
            if desc and desc.upper().strip() in NATIVE_BAND_RESOLUTIONS:
                mapping[i] = desc.upper().strip()
            elif band_count == 8 and i in default_8band_map:
                mapping[i] = default_8band_map[i]
            elif band_count == 6 and i in default_6band_map:
                mapping[i] = default_6band_map[i]
            else:
                mapping[i] = f"BAND_{i}"
                
    for i in range(1, band_count + 1):
        band_code = mapping.get(i, f"BAND_{i}")
        raw_arr = src.read(i).astype(np.float32)
        if src.nodata is not None:
            raw_arr[raw_arr == src.nodata] = np.nan
            
        valid_vals = raw_arr[~np.isnan(raw_arr)]
        if valid_vals.size > 0 and np.nanmax(valid_vals) > 2.0:
            raw_arr /= 10000.0
        band_dict[band_code] = raw_arr
        
    return band_dict


# =============================================================================
# 3. Scientific Index Formulas
# =============================================================================

def safe_norm_diff(b_a: np.ndarray, b_b: np.ndarray) -> np.ndarray:
    denom = b_a + b_b
    with np.errstate(divide='ignore', invalid='ignore'):
        res = np.where((denom != 0) & (~np.isnan(denom)), (b_a - b_b) / denom, np.nan)
    return res


def compute_single_index(idx_name: str, bands: dict[str, np.ndarray]) -> np.ndarray:
    b_nir = bands.get("B08") if "B08" in bands else bands.get("B8A")
    b_red = bands.get("B04")
    b_green = bands.get("B03")
    b_blue = bands.get("B02")
    b_b5 = bands.get("B05")
    b_b7 = bands.get("B07")
    b_swir1 = bands.get("B11")
    b_swir2 = bands.get("B12")
    
    if idx_name == "NDVI":
        if b_nir is None or b_red is None:
            raise ValueError("NDVI requires NIR (B08) and Red (B04) bands.")
        return safe_norm_diff(b_nir, b_red)
        
    elif idx_name == "EVI":
        if b_nir is None or b_red is None or b_blue is None:
            raise ValueError("EVI requires NIR (B08), Red (B04), and Blue (B02) bands.")
        denom = b_nir + 6.0 * b_red - 7.5 * b_blue + 1.0
        with np.errstate(divide='ignore', invalid='ignore'):
            return np.where((denom != 0) & (~np.isnan(denom)), 2.5 * (b_nir - b_red) / denom, np.nan)
            
    elif idx_name == "SAVI":
        if b_nir is None or b_red is None:
            raise ValueError("SAVI requires NIR (B08) and Red (B04) bands.")
        denom = b_nir + b_red + 0.5
        with np.errstate(divide='ignore', invalid='ignore'):
            return np.where((denom != 0) & (~np.isnan(denom)), ((b_nir - b_red) / denom) * 1.5, np.nan)
            
    elif idx_name == "GNDVI":
        if b_nir is None or b_green is None:
            raise ValueError("GNDVI requires NIR (B08) and Green (B03) bands.")
        return safe_norm_diff(b_nir, b_green)
        
    elif idx_name == "NDRE_B5":
        if b_nir is None or b_b5 is None:
            raise ValueError("NDRE_B5 requires NIR (B08) and Red Edge 1 (B05) bands.")
        return safe_norm_diff(b_nir, b_b5)
        
    elif idx_name == "NDRE_B7":
        if b_nir is None or b_b7 is None:
            raise ValueError("NDRE_B7 requires NIR (B08) and Red Edge 3 (B07) bands.")
        return safe_norm_diff(b_nir, b_b7)
        
    elif idx_name == "NDMI":
        if b_nir is None or b_swir1 is None:
            raise ValueError("NDMI requires NIR (B08) and SWIR-1 (B11) bands.")
        return safe_norm_diff(b_nir, b_swir1)
        
    elif idx_name == "NDWI":
        if b_green is None or b_nir is None:
            raise ValueError("NDWI (McFeeters) requires Green (B03) and NIR (B08) bands.")
        return safe_norm_diff(b_green, b_nir)
        
    elif idx_name == "MSAVI":
        if b_nir is None or b_red is None:
            raise ValueError("MSAVI requires NIR (B08) and Red (B04) bands.")
        term = (2.0 * b_nir + 1.0) ** 2 - 8.0 * (b_nir - b_red)
        with np.errstate(divide='ignore', invalid='ignore'):
            return np.where((term >= 0) & (~np.isnan(term)), (2.0 * b_nir + 1.0 - np.sqrt(np.maximum(term, 0.0))) / 2.0, np.nan)
            
    elif idx_name == "NBR":
        if b_nir is None or b_swir2 is None:
            raise ValueError("NBR requires NIR (B08) and SWIR-2 (B12) bands.")
        return safe_norm_diff(b_nir, b_swir2)
        
    raise ValueError(f"Unhandled index calculation for '{idx_name}'.")


# =============================================================================
# 4. Core Execution & Statistics Generation Engine
# =============================================================================

DEFAULT_OUTPUT_DIR = Path("./output_indices")

def compute_vegetation_indices(req: VegetationIndicesRequest) -> dict:
    in_path = Path(req.file_path)
    out_dir = Path(req.output_dir) if req.output_dir else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    
    with rasterio.open(in_path) as src:
        meta = src.meta.copy()
        width, height = src.width, src.height
        crs = src.crs
        crs_str = str(crs) if crs else "UNREFERENCED"
        is_geographic = crs.is_geographic if crs else False
        bounds = src.bounds
        res_x, res_y = src.res
        bands = extract_spectral_bands(src, req.band_mapping)
        
    computed_arrays = []
    band_mapping = {}
    stats_dict = {}
    native_inputs_m = {}
    
    for i, idx_name in enumerate(req.indices):
        arr = compute_single_index(idx_name, bands)
        computed_arrays.append(arr)
        band_mapping[f"Band_{i+1}"] = idx_name
        
        valid_pixels = arr[~np.isnan(arr)]
        total_pixels = arr.size
        valid_count = int(valid_pixels.size)
        nodata_count = total_pixels - valid_count
        valid_pct = round(float(valid_count / total_pixels * 100.0), 2)
        
        if valid_count > 0:
            stats_dict[idx_name] = {
                "valid_pixel_count": valid_count,
                "nodata_pixel_count": nodata_count,
                "valid_pixel_percentage": valid_pct,
                "min": round(float(np.min(valid_pixels)), 3),
                "max": round(float(np.max(valid_pixels)), 3),
                "mean": round(float(np.mean(valid_pixels)), 3),
                "median": round(float(np.median(valid_pixels)), 3),
                "std_dev": round(float(np.std(valid_pixels)), 3),
                "p10": round(float(np.percentile(valid_pixels, 10)), 3),
                "p90": round(float(np.percentile(valid_pixels, 90)), 3),
            }
        else:
            stats_dict[idx_name] = {"valid_pixel_count": 0, "nodata_pixel_count": total_pixels, "valid_pixel_percentage": 0.0}
            
    for b_code in bands.keys():
        if b_code in NATIVE_BAND_RESOLUTIONS:
            native_inputs_m[b_code] = NATIVE_BAND_RESOLUTIONS[b_code]
            
    # Calculate physical Ground Sampling Distance (GSD) and accurate area in km2 using exact WGS84 geodesic polynomial
    if is_geographic:
        lat_mid = (bounds.bottom + bounds.top) / 2.0
        deg_to_m_lat = 111132.954 - 559.822 * np.cos(2 * np.radians(lat_mid)) + 1.175 * np.cos(4 * np.radians(lat_mid))
        deg_to_m_lon = 111412.84 * np.cos(np.radians(lat_mid)) - 93.5 * np.cos(3 * np.radians(lat_mid))
        gsd_x_m = round(float(abs(res_x) * deg_to_m_lon), 2)
        gsd_y_m = round(float(abs(res_y) * deg_to_m_lat), 2)
        mean_gsd_m = round(float((gsd_x_m + gsd_y_m) / 2.0), 2)
        pixel_area_m2 = (abs(res_x) * deg_to_m_lon) * (abs(res_y) * deg_to_m_lat)
        pixel_area_km2 = pixel_area_m2 / 1e6
        gsd_info = {"x_m": gsd_x_m, "y_m": gsd_y_m, "mean_gsd_m": mean_gsd_m}
    else:
        gsd_x_m = round(float(abs(res_x)), 2)
        gsd_y_m = round(float(abs(res_y)), 2)
        mean_gsd_m = round(float((gsd_x_m + gsd_y_m) / 2.0), 2)
        pixel_area_m2 = abs(res_x * res_y)
        pixel_area_km2 = pixel_area_m2 / 1e6
        gsd_info = {"x_m": gsd_x_m, "y_m": gsd_y_m, "mean_gsd_m": mean_gsd_m}
        
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_tif_name = f"{in_path.stem}_indices_{timestamp}.tif"
    out_tif_path = out_dir / out_tif_name
    
    meta.update({
        "count": len(computed_arrays),
        "dtype": "float32",
        "nodata": -9999.0,
    })
    
    with rasterio.open(out_tif_path, "w", **meta) as dst:
        for i, arr in enumerate(computed_arrays):
            write_arr = np.where(np.isnan(arr), -9999.0, arr).astype(np.float32)
            dst.write(write_arr, i + 1)
            dst.set_band_description(i + 1, req.indices[i])
            
    heuristic_classification = None
    if req.calculate_heuristic_classification and "NDVI" in req.indices:
        ndvi_idx = req.indices.index("NDVI")
        ndvi_arr = computed_arrays[ndvi_idx]
        valid_ndvi = ndvi_arr[~np.isnan(ndvi_arr)]
        
        if valid_ndvi.size > 0:
            total_valid = valid_ndvi.size
            dense_count = np.count_nonzero(valid_ndvi > 0.6)
            mod_count = np.count_nonzero((valid_ndvi >= 0.3) & (valid_ndvi <= 0.6))
            sparse_count = np.count_nonzero((valid_ndvi >= 0.1) & (valid_ndvi < 0.3))
            non_veg_count = np.count_nonzero(valid_ndvi < 0.1)
            
            heuristic_classification = {
                "method": "rule_based_heuristic",
                "qualifier": "Heuristic thresholds for general canopy vigor; not ground-truth land cover.",
                "dense_vegetation_pct": round(float(dense_count / total_valid * 100.0), 2),
                "dense_vegetation_km2": round(float(dense_count * pixel_area_km2), 2),
                "moderate_vegetation_pct": round(float(mod_count / total_valid * 100.0), 2),
                "moderate_vegetation_km2": round(float(mod_count * pixel_area_km2), 2),
                "sparse_vegetation_pct": round(float(sparse_count / total_valid * 100.0), 2),
                "sparse_vegetation_km2": round(float(sparse_count * pixel_area_km2), 2),
                "low_ndvi_non_vegetated_or_water_pct": round(float(non_veg_count / total_valid * 100.0), 2),
                "low_ndvi_non_vegetated_or_water_km2": round(float(non_veg_count * pixel_area_km2), 2),
            }
            
    return {
        "status": "success",
        "data": {
            "file_path": str(out_tif_path.resolve()),
            "file_name": out_tif_path.name,
            "format": "GeoTIFF",
        },
        "source_raster": {
            "input_file": in_path.name,
            "width": width,
            "height": height,
            "crs": crs_str,
        },
        "raster": {
            "width": width,
            "height": height,
            "band_count": len(computed_arrays),
            "dtype": "float32",
            "crs": crs_str,
            "nodata": -9999.0,
            "band_mapping": band_mapping,
        },
        "resolution": {
            "native_inputs_m": native_inputs_m,
            "output_resolution_deg": res_x if is_geographic else None,
            "output_resolution_m": res_x if not is_geographic else None,
            "approx_ground_sampling_distance_m": gsd_info,
            "resampling_stage": "Tool_2_provider_level",
            "resampling_method": "bilinear",
            "provenance_note": f"Output raster grid ({gsd_info['mean_gsd_m']}m/pixel) is directly inherited from Tool 2 without secondary resampling. Native 10m/20m Sentinel-2 bands were resampled during Tool 2 retrieval."
        },
        "statistics": stats_dict,
        "heuristic_classification": heuristic_classification,
    }


# =============================================================================
# 5. FastMCP Tool Registration & CLI Entry Point
# =============================================================================

if FastMCP is None:
    class _DummyMCP:
        def tool(self, *args, **kwargs):
            return lambda fn: fn
    mcp = _DummyMCP()
else:
    mcp = FastMCP("Tool 5: Vegetation & Spectral Indices Server")

@mcp.tool(
    name="compute_vegetation_indices",
    description="Compute multi-band scientific spectral indices (NDVI, EVI, SAVI, GNDVI, NDRE_B5, NDRE_B7, NDMI, NDWI, MSAVI, NBR) from a multispectral GeoTIFF raster with statistical distributions and heuristic canopy area estimates.",
)
def mcp_compute_vegetation_indices(
    file_path: str,
    indices: list[str] = ALL_10_INDICES,
    band_mapping: Optional[dict[str, str]] = None,
    calculate_heuristic_classification: bool = True,
) -> dict:
    try:
        req = VegetationIndicesRequest(
            file_path=file_path,
            indices=indices,
            band_mapping=band_mapping,
            calculate_heuristic_classification=calculate_heuristic_classification,
        )
        return compute_vegetation_indices(req)
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
            req = VegetationIndicesRequest(**data)
            res = compute_vegetation_indices(req)
            print(json.dumps(res, indent=2))
        else:
            print(f"Error: input file '{input_file}' not found.", file=sys.stderr)
            sys.exit(1)
    else:
        print("Tool 5: compute_vegetation_indices ready. Pass a JSON configuration file or run via FastMCP.")
