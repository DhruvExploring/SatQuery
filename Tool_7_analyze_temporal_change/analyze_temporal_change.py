"""Tool 7: analyze_temporal_change (Grid-Aligned Multi-Temporal Differential Analysis Engine)

Performs rigorous pixel-wise temporal change detection on aligned GeoTIFF rasters
(e.g., NDVI, NDWI, SAR backscatter dB, or single-band index products).
Calculates absolute delta (T2 - T1), relative percentage shift, statistical significance,
noise thresholding, change severity zoning, and produces continuous delta & discrete change mask GeoTIFFs.
"""

import io
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional, Tuple, Union, Any

import numpy as np
import rasterio
from rasterio.transform import Affine
from pydantic import BaseModel, Field, field_validator, model_validator
try:
    from fastmcp import FastMCP
except (ImportError, Exception):
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        FastMCP = None


# =============================================================================
# 1. Pydantic Request & Configuration Models
# =============================================================================

class TemporalChangeRequest(BaseModel):
    raster_before_path: str = Field(
        ...,
        description="Absolute or relative path to the baseline/pre-event GeoTIFF (T1)"
    )
    raster_after_path: str = Field(
        ...,
        description="Absolute or relative path to the target/post-event GeoTIFF (T2)"
    )
    band_selection: Union[int, str] = Field(
        default=1,
        description="Band to compare: 1-based integer index or band name string (e.g. 'NDVI', 'VV_dB')"
    )
    threshold_type: Literal["absolute", "statistical"] = Field(
        default="absolute",
        description="Thresholding method: 'absolute' (fixed numeric delta) or 'statistical' (mean +/- k * std)"
    )
    threshold_value: float = Field(
        default=0.15,
        description="Threshold magnitude: delta value for 'absolute' (e.g., 0.15 for NDVI), or sigma multiplier k for 'statistical' (e.g., 2.0)"
    )
    relative_change_threshold_percent: Optional[float] = Field(
        default=None,
        description=(
            "Optional relative percentage shift threshold (e.g. 20.0 for +/- 20% relative change). "
            "Note: relative_change_threshold_percent is intended for linear index products (e.g. NDVI, NDWI). "
            "It should NOT be applied to logarithmic SAR backscatter (dB), where differences are already power ratios."
        )
    )
    mask_encoding: Literal["bipolar_3class", "severity_5class"] = Field(
        default="bipolar_3class",
        description="Classification encoding: 'bipolar_3class' (-1=loss, 0=stable, 1=gain) or 'severity_5class' (-2=major loss, -1=mod loss, 0=stable, 1=mod gain, 2=major gain)"
    )
    output_dir: Optional[str] = Field(
        default=None,
        description="Directory to save generated difference and change mask GeoTIFFs. Defaults to 'output_dir' alongside inputs or test_runs."
    )
    generate_difference_raster: bool = Field(
        default=True,
        description="Whether to write continuous delta (T2 - T1) Float32 GeoTIFF to disk"
    )
    generate_change_mask: bool = Field(
        default=True,
        description="Whether to write discrete classified change mask Int8 GeoTIFF to disk"
    )

    @field_validator("raster_before_path")
    @classmethod
    def validate_before_path(cls, value: str) -> str:
        p = Path(value)
        if not p.exists() or not p.is_file():
            raise ValueError(f"Baseline raster file does not exist: '{value}'")
        return str(p.resolve())

    @field_validator("raster_after_path")
    @classmethod
    def validate_after_path(cls, value: str) -> str:
        p = Path(value)
        if not p.exists() or not p.is_file():
            raise ValueError(f"Target raster file does not exist: '{value}'")
        return str(p.resolve())

    @field_validator("threshold_value")
    @classmethod
    def validate_threshold_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("threshold_value must be strictly positive (> 0.0)")
        return float(value)


# =============================================================================
# 2. Mathematical & Spatial Utilities
# =============================================================================

def resolve_band_index(src: rasterio.io.DatasetReader, selection: Union[int, str]) -> Tuple[int, str]:
    """Resolves a 1-based band index and description from integer or band name."""
    if isinstance(selection, int):
        if 1 <= selection <= src.count:
            desc = src.descriptions[selection - 1] or f"Band_{selection}"
            return selection, desc
        raise ValueError(f"Band index {selection} out of range (raster has {src.count} bands)")

    # String matching against band descriptions
    desc_list = [d or "" for d in src.descriptions]
    sel_clean = str(selection).strip().upper()
    for idx, d in enumerate(desc_list, start=1):
        if d and d.strip().upper() == sel_clean:
            return idx, d

    # Also check tags or fallback to digit parse
    if sel_clean.isdigit():
        idx = int(sel_clean)
        if 1 <= idx <= src.count:
            return idx, src.descriptions[idx - 1] or f"Band_{idx}"

    raise ValueError(f"Band '{selection}' not found in raster descriptions: {desc_list}")


def calculate_pixel_area_m2(crs: rasterio.crs.CRS, res_x: float, res_y: float, bounds: rasterio.coords.BoundingBox) -> float:
    """Computes exact metric ground area per pixel in m^2."""
    if crs and crs.is_geographic:
        # WGS84 Geographic Degrees: scale longitude by cosine of midpoint latitude
        lat_mid = (bounds.bottom + bounds.top) / 2.0
        deg_to_m_lat = 111132.954 - 559.822 * np.cos(2 * np.radians(lat_mid)) + 1.175 * np.cos(4 * np.radians(lat_mid))
        deg_to_m_lon = 111412.84 * np.cos(np.radians(lat_mid)) - 93.5 * np.cos(3 * np.radians(lat_mid))
        pixel_width_m = abs(res_x) * deg_to_m_lon
        pixel_height_m = abs(res_y) * deg_to_m_lat
        return float(pixel_width_m * pixel_height_m)
    elif crs and crs.is_projected:
        # Projected meters (UTM, etc.)
        return float(abs(res_x * res_y))
    else:
        # Fallback approximation assuming degrees
        lat_mid = (bounds.bottom + bounds.top) / 2.0 if bounds else 0.0
        km_lon = 111.320 * np.cos(np.radians(lat_mid)) * abs(res_x)
        km_lat = 110.574 * abs(res_y)
        return float(km_lon * km_lat * 1e6)


def verify_grid_alignment(
    src1: rasterio.io.DatasetReader,
    src2: rasterio.io.DatasetReader,
    tolerance: float = 1e-5
) -> Tuple[bool, Dict[str, Any]]:
    """Performs rigorous Tool 6 grid-alignment verification with tolerance."""
    same_crs = bool(src1.crs == src2.crs)
    same_dims = bool(src1.width == src2.width and src1.height == src2.height)

    # Affine transform comparison
    t1 = np.array(src1.transform[:6])
    t2 = np.array(src2.transform[:6])
    max_transform_diff = float(np.max(np.abs(t1 - t2)))
    same_transform = bool(max_transform_diff < tolerance)

    # Bounds comparison
    b1 = np.array([src1.bounds.left, src1.bounds.bottom, src1.bounds.right, src1.bounds.top])
    b2 = np.array([src2.bounds.left, src2.bounds.bottom, src2.bounds.right, src2.bounds.top])
    max_bounds_diff = float(np.max(np.abs(b1 - b2)))
    same_bounds = bool(max_bounds_diff < tolerance)

    is_aligned = bool(same_crs and same_dims and same_transform and same_bounds)

    details = {
        "is_aligned": is_aligned,
        "crs_match": same_crs,
        "dimensions_match": same_dims,
        "transform_match": same_transform,
        "bounds_match": same_bounds,
        "max_transform_difference": round(max_transform_diff, 8),
        "max_bounds_difference": round(max_bounds_diff, 8),
        "t1_dimensions": {"width": src1.width, "height": src1.height},
        "t2_dimensions": {"width": src2.width, "height": src2.height},
        "t1_crs": str(src1.crs) if src1.crs else "UNREFERENCED",
        "t2_crs": str(src2.crs) if src2.crs else "UNREFERENCED"
    }
    return is_aligned, details


# =============================================================================
# 3. Core Temporal Change Detection Engine
# =============================================================================

def analyze_temporal_change(req: TemporalChangeRequest) -> Dict[str, Any]:
    """Main execution function for Tool 7."""
    path_t1 = Path(req.raster_before_path)
    path_t2 = Path(req.raster_after_path)

    with rasterio.open(path_t1) as src1, rasterio.open(path_t2) as src2:
        # 1. Pre-flight Grid Alignment QA
        is_aligned, align_details = verify_grid_alignment(src1, src2)
        if not is_aligned:
            return {
                "status": "error",
                "error_code": "GRID_MISALIGNMENT",
                "message": (
                    "Temporal change detection aborted: input rasters are geometrically misaligned. "
                    "Pre-flight inspection failed matching CRS, dimensions, or affine transforms."
                ),
                "alignment_diagnostics": align_details,
                "remediation": "Re-align or re-project both rasters to a matching coordinate grid and bounding extent before diffing."
            }

        # 2. Band Selection Resolution
        try:
            band_idx_t1, band_name_t1 = resolve_band_index(src1, req.band_selection)
            band_idx_t2, band_name_t2 = resolve_band_index(src2, req.band_selection)
        except ValueError as e:
            return {
                "status": "error",
                "error_code": "BAND_RESOLUTION_ERROR",
                "message": str(e),
                "t1_available_bands": [d or f"Band_{i}" for i, d in enumerate(src1.descriptions, 1)],
                "t2_available_bands": [d or f"Band_{i}" for i, d in enumerate(src2.descriptions, 1)]
            }

        # 3. Read Raster Data as Float32
        arr_t1 = src1.read(band_idx_t1).astype(np.float32)
        arr_t2 = src2.read(band_idx_t2).astype(np.float32)

        nodata_t1 = src1.nodatavals[band_idx_t1 - 1]
        nodata_t2 = src2.nodatavals[band_idx_t2 - 1]

        # 4. Symmetric NoData & NaN Masking
        valid_mask_t1 = np.isfinite(arr_t1)
        if nodata_t1 is not None and not np.isnan(nodata_t1):
            valid_mask_t1 &= (arr_t1 != nodata_t1)

        valid_mask_t2 = np.isfinite(arr_t2)
        if nodata_t2 is not None and not np.isnan(nodata_t2):
            valid_mask_t2 &= (arr_t2 != nodata_t2)

        valid_mask = valid_mask_t1 & valid_mask_t2
        valid_pixel_count = int(np.sum(valid_mask))
        total_pixel_count = int(src1.width * src1.height)

        if valid_pixel_count == 0:
            return {
                "status": "error",
                "error_code": "NO_VALID_PIXELS",
                "message": "Both input rasters contain zero overlapping valid (non-NaN / non-NoData) pixels.",
                "total_pixels": total_pixel_count,
                "valid_pixels": 0
            }

        # 5. Continuous Differential Calculation (Delta = T2 - T1)
        delta = np.full_like(arr_t1, np.nan, dtype=np.float32)
        delta[valid_mask] = arr_t2[valid_mask] - arr_t1[valid_mask]
        valid_deltas = delta[valid_mask]

        # 6. Statistical Threshold Resolution
        mean_delta = float(np.mean(valid_deltas))
        std_delta = float(np.std(valid_deltas))
        median_delta = float(np.median(valid_deltas))
        min_delta = float(np.min(valid_deltas))
        max_delta = float(np.max(valid_deltas))

        if req.threshold_type == "absolute":
            threshold_loss = -abs(req.threshold_value)
            threshold_gain = abs(req.threshold_value)
            active_threshold_desc = f"Absolute Delta >= +/-{req.threshold_value:.4f}"
        else:
            k = req.threshold_value
            threshold_loss = mean_delta - (k * std_delta)
            threshold_gain = mean_delta + (k * std_delta)
            active_threshold_desc = f"Statistical Mean ({mean_delta:+.4f}) +/- {k:.2f}*Sigma ({std_delta:.4f})"

        # 7. Relative Percentage Shift
        rel_shift = np.full_like(arr_t1, np.nan, dtype=np.float32)
        safe_base_mask = valid_mask & (np.abs(arr_t1) > 1e-4)
        if np.any(safe_base_mask):
            rel_shift[safe_base_mask] = ((arr_t2[safe_base_mask] - arr_t1[safe_base_mask]) / np.abs(arr_t1[safe_base_mask])) * 100.0
            valid_rel_shifts = rel_shift[safe_base_mask]
            mean_rel_shift = float(np.mean(valid_rel_shifts))
            median_rel_shift = float(np.median(valid_rel_shifts))
        else:
            mean_rel_shift = None
            median_rel_shift = None

        # 8. Discrete Change Mask & Severity Classification
        # 3-Class Encoding: -1=Loss/Decrease, 0=Stable, 1=Gain/Increase, -128=NoData
        # 5-Class Encoding: -2=Major Loss, -1=Moderate Loss, 0=Stable, 1=Moderate Gain, 2=Major Gain, -128=NoData
        NODATA_MASK_VAL = -128
        change_mask_arr = np.full(arr_t1.shape, NODATA_MASK_VAL, dtype=np.int8)

        # Boolean masks on valid data
        loss_condition = valid_mask & (delta <= threshold_loss)
        gain_condition = valid_mask & (delta >= threshold_gain)

        if req.relative_change_threshold_percent is not None and np.any(safe_base_mask):
            rel_thresh = abs(req.relative_change_threshold_percent)
            loss_condition &= (rel_shift <= -rel_thresh)
            gain_condition &= (rel_shift >= rel_thresh)

        stable_condition = valid_mask & (~loss_condition) & (~gain_condition)

        # Severity sub-thresholds
        major_loss_thresh = threshold_loss * 2.0 if req.threshold_type == "absolute" else mean_delta - (2.0 * req.threshold_value * std_delta)
        major_gain_thresh = threshold_gain * 2.0 if req.threshold_type == "absolute" else mean_delta + (2.0 * req.threshold_value * std_delta)

        major_loss_cond = loss_condition & (delta <= major_loss_thresh)
        mod_loss_cond = loss_condition & (~major_loss_cond)
        major_gain_cond = gain_condition & (delta >= major_gain_thresh)
        mod_gain_cond = gain_condition & (~major_gain_cond)

        if req.mask_encoding == "bipolar_3class":
            change_mask_arr[stable_condition] = 0
            change_mask_arr[loss_condition] = -1
            change_mask_arr[gain_condition] = 1
        else:
            change_mask_arr[stable_condition] = 0
            change_mask_arr[mod_loss_cond] = -1
            change_mask_arr[major_loss_cond] = -2
            change_mask_arr[mod_gain_cond] = 1
            change_mask_arr[major_gain_cond] = 2

        # 9. Spatial Surface Area Accounting
        pixel_area_m2 = calculate_pixel_area_m2(src1.crs, src1.res[0], src1.res[1], src1.bounds)
        pixel_area_km2 = pixel_area_m2 / 1e6
        pixel_area_ha = pixel_area_m2 / 1e4

        def compute_class_metrics(count: int) -> Dict[str, Any]:
            area_km2 = round(count * pixel_area_km2, 4)
            area_ha = round(count * pixel_area_ha, 2)
            pct_valid = round((count / valid_pixel_count) * 100.0, 2) if valid_pixel_count > 0 else 0.0
            return {
                "pixel_count": int(count),
                "area_km2": area_km2,
                "area_hectares": area_ha,
                "percentage_of_valid_aoi": pct_valid
            }

        loss_pixels = int(np.sum(loss_condition))
        gain_pixels = int(np.sum(gain_condition))
        stable_pixels = int(np.sum(stable_condition))
        invalid_pixels = total_pixel_count - valid_pixel_count

        severity_breakdown = {
            "major_decrease": compute_class_metrics(int(np.sum(major_loss_cond))),
            "moderate_decrease": compute_class_metrics(int(np.sum(mod_loss_cond))),
            "stable": compute_class_metrics(stable_pixels),
            "moderate_increase": compute_class_metrics(int(np.sum(mod_gain_cond))),
            "major_increase": compute_class_metrics(int(np.sum(major_gain_cond)))
        }

        # 10. Statistical Percentiles & Histogram of Delta
        p01, p05, p25, p50, p75, p95, p99 = np.percentile(valid_deltas, [1, 5, 25, 50, 75, 95, 99])
        hist_counts, bin_edges = np.histogram(valid_deltas, bins=10)
        histogram = []
        for i in range(len(hist_counts)):
            histogram.append({
                "bin_start": round(float(bin_edges[i]), 4),
                "bin_end": round(float(bin_edges[i + 1]), 4),
                "count": int(hist_counts[i]),
                "frequency_percent": round(float(hist_counts[i] / valid_pixel_count) * 100.0, 2)
            })

        # 11. Write Output GeoTIFFs (if enabled)
        out_dir = Path(req.output_dir) if req.output_dir else (path_t2.parent)
        out_dir.mkdir(parents=True, exist_ok=True)

        diff_raster_path = None
        change_mask_path = None

        base_stem = f"{path_t1.stem}_vs_{path_t2.stem}_{band_name_t1}"

        if req.generate_difference_raster:
            diff_file = out_dir / f"{base_stem}_difference.tif"
            diff_meta = src1.meta.copy()
            diff_meta.update({
                "count": 1,
                "dtype": "float32",
                "nodata": -9999.0,
                "compress": "deflate",
                "predictor": 3
            })
            # Prepare write array with -9999.0 nodata
            diff_write = np.full(arr_t1.shape, -9999.0, dtype=np.float32)
            diff_write[valid_mask] = valid_deltas

            with rasterio.open(diff_file, "w", **diff_meta) as dst:
                dst.write(diff_write, 1)
                dst.set_band_description(1, f"Delta ({band_name_t2} T2 - {band_name_t1} T1)")
            diff_raster_path = str(diff_file.resolve())

        if req.generate_change_mask:
            mask_file = out_dir / f"{base_stem}_change_mask.tif"
            mask_meta = src1.meta.copy()
            mask_meta.update({
                "count": 1,
                "dtype": "int8",
                "nodata": NODATA_MASK_VAL,
                "compress": "deflate"
            })
            with rasterio.open(mask_file, "w", **mask_meta) as dst:
                dst.write(change_mask_arr, 1)
                dst.set_band_description(1, f"Change Mask ({req.mask_encoding})")
            change_mask_path = str(mask_file.resolve())

        # 12. Build Final Structured JSON Output
        total_aoi_km2 = round(total_pixel_count * pixel_area_km2, 4)
        valid_aoi_km2 = round(valid_pixel_count * pixel_area_km2, 4)

        result_payload = {
            "status": "success",
            "tool": "Tool_7_analyze_temporal_change",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "band_evaluated": {
                "band_name": band_name_t1,
                "t1_band_index": band_idx_t1,
                "t2_band_index": band_idx_t2
            },
            "provenance": {
                "raster_before": str(path_t1.resolve()),
                "raster_after": str(path_t2.resolve()),
                "crs": str(src1.crs) if src1.crs else "UNREFERENCED",
                "grid_dimensions": {"width": src1.width, "height": src1.height},
                "spatial_bounds": {
                    "left": round(src1.bounds.left, 6),
                    "bottom": round(src1.bounds.bottom, 6),
                    "right": round(src1.bounds.right, 6),
                    "top": round(src1.bounds.top, 6)
                },
                "pixel_ground_resolution_m2": round(pixel_area_m2, 2)
            },
            "threshold_parameters": {
                "threshold_type": req.threshold_type,
                "threshold_value": req.threshold_value,
                "threshold_description": active_threshold_desc,
                "effective_loss_threshold": round(threshold_loss, 4),
                "effective_gain_threshold": round(threshold_gain, 4),
                "relative_change_filter_percent": req.relative_change_threshold_percent
            },
            "spatial_coverage": {
                "total_raster_area_km2": total_aoi_km2,
                "valid_aoi_area_km2": valid_aoi_km2,
                "valid_fraction_percent": round((valid_pixel_count / total_pixel_count) * 100.0, 2),
                "total_pixels": total_pixel_count,
                "valid_pixels": valid_pixel_count,
                "masked_nodata_pixels": invalid_pixels
            },
            "change_summary": {
                "significant_decrease": compute_class_metrics(loss_pixels),
                "stable_unaltered": compute_class_metrics(stable_pixels),
                "significant_increase": compute_class_metrics(gain_pixels),
                "net_change_area_km2": round((gain_pixels - loss_pixels) * pixel_area_km2, 4)
            },
            "severity_distribution": severity_breakdown,
            "delta_statistics": {
                "mean_delta": round(mean_delta, 4),
                "median_delta": round(median_delta, 4),
                "std_delta": round(std_delta, 4),
                "min_delta": round(min_delta, 4),
                "max_delta": round(max_delta, 4),
                "percentiles": {
                    "p01": round(float(p01), 4),
                    "p05": round(float(p05), 4),
                    "p25": round(float(p25), 4),
                    "p50": round(float(p50), 4),
                    "p75": round(float(p75), 4),
                    "p95": round(float(p95), 4),
                    "p99": round(float(p99), 4)
                },
                "mean_relative_shift_percent": round(mean_rel_shift, 2) if mean_rel_shift is not None else None,
                "median_relative_shift_percent": round(median_rel_shift, 2) if median_rel_shift is not None else None
            },
            "delta_histogram": histogram,
            "generated_products": {
                "difference_raster_path": diff_raster_path,
                "change_mask_path": change_mask_path,
                "mask_encoding": req.mask_encoding,
                "mask_legend": {
                    "-2": "Major Loss / Severe Decrease" if req.mask_encoding == "severity_5class" else "N/A",
                    "-1": "Significant Loss / Decrease",
                    "0": "Stable / Insignificant Change",
                    "1": "Significant Gain / Increase",
                    "2": "Major Gain / Rapid Increase" if req.mask_encoding == "severity_5class" else "N/A",
                    "-128": "NoData / Masked Out"
                }
            }
        }
        return result_payload


# =============================================================================
# 4. FastMCP Tool Registration & CLI Adapter
# =============================================================================

if FastMCP is None:
    class _DummyMCP:
        def tool(self, *args, **kwargs):
            return lambda fn: fn
    mcp = _DummyMCP()
else:
    mcp = FastMCP("Tool 7: Grid-Aligned Temporal Change Detection Engine")

@mcp.tool(
    name="analyze_temporal_change",
    description="Perform pixel-wise temporal change detection between two aligned GeoTIFF rasters with thresholding and area accounting."
)
def analyze_temporal_change_mcp(
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
    """FastMCP entry point for Tool 7 temporal change detection."""
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


if __name__ == "__main__":
    if len(sys.argv) > 1:
        input_file = Path(sys.argv[1])
        if input_file.exists():
            with open(input_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            req = TemporalChangeRequest(**data)
            res = analyze_temporal_change(req)
            print(json.dumps(res, indent=2))
        else:
            print(f"Error: input file {input_file} not found.", file=sys.stderr)
            sys.exit(1)
    else:
        print("Tool 7: analyze_temporal_change ready. Pass a JSON configuration file or run via FastMCP.")
