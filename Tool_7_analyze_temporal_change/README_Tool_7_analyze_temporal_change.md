# Tool 7: analyze_temporal_change (Grid-Aligned Multi-Temporal Differential Analysis Engine)

## 1. Overview & Purpose

**`analyze_temporal_change`** is a high-precision, multi-temporal differential raster analysis engine designed for Model Context Protocol (MCP) clients and LangGraph autonomous agents. Its primary responsibility is to evaluate **pixel-level temporal dynamics** between two aligned satellite raster acquisitions ($T_1$ baseline vs. $T_2$ target), such as vegetation indices (NDVI, NDWI, EVI), SAR backscatter ($\gamma^0/\sigma^0$ VV/VH in dB), or multispectral reflectance products.

By operating strictly on continuous differential algebra ($T_2 - T_1$) and outputting both structured statistical telemetry and georeferenced GeoTIFF rasters (continuous delta and discrete change masks), Tool 7 serves as the primary detector of environmental change (e.g., deforestation, wildfire burn scars, flood inundation, agricultural harvesting, crop growth, or urban expansion).

```text
Pipeline Context:
Tool 1 / 2 / 3 / 5 (T1 & T2) ──► Tool 6 (Pre-flight Grid QA) ──► Tool 7 (Temporal Change) ──► change_mask.tif ──► Tool 8 (Zonal Landcover & Terrain)
```

---

## 2. Core Differential Capabilities

### 1. Mathematical Differential Operations:
- **Continuous Absolute Delta ($\Delta$):**
  $$\Delta = T_2 - T_1$$
  Direct difference indicating absolute physical change in index units or radar backscatter.
- **Relative Percentage Shift ($\Delta\%$):**
  $$\Delta\% = \left( \frac{T_2 - T_1}{|T_1| + \epsilon} \right) \times 100$$
  Evaluates proportional change while safely guarding against near-zero division asymptotes ($|T_1| > 10^{-4}$).
  > [!NOTE]
  > **Scientific Guardrail:** `relative_change_threshold_percent` is intended for linear index products (e.g. NDVI, NDWI, EVI). It should **NOT** be applied to logarithmic SAR backscatter (dB), where differences are already power ratios.

### 2. Dual Thresholding Strategies:
- **Absolute Delta Thresholding (`threshold_type = "absolute"`):**
  User-defined delta cutoff $\tau$ (e.g., $\Delta \le -0.15$ for NDVI vegetation loss, or $\Delta \ge +0.15$ for vegetation growth).
- **Statistical Standard Deviation Thresholding (`threshold_type = "statistical"`):**
  Dynamically adapts to the scene's empirical noise floor:
  $$\text{Loss Threshold} = \mu_{\Delta} - k \cdot \sigma_{\Delta}, \quad \text{Gain Threshold} = \mu_{\Delta} + k \cdot \sigma_{\Delta}$$
  where $k$ is the user-defined multiplier (e.g., $k=2.0$ for $2\sigma$ significance).

### 3. Change Mask Encoding & Severity Zoning:
- **Bipolar 3-Class (`mask_encoding = "bipolar_3class"`):**
  - `-1`: Significant Loss / Decrease ($\Delta \le \tau_{\text{loss}}$)
  - `0`: Stable / Insignificant Variation ($-\tau < \Delta < +\tau$)
  - `+1`: Significant Gain / Increase ($\Delta \ge \tau_{\text{gain}}$)
  - `-128`: Masked NoData
- **Severity 5-Class (`mask_encoding = "severity_5class"`):**
  - `-2`: Major Loss / Severe Disturbance ($\Delta \le 2 \cdot \tau_{\text{loss}}$)
  - `-1`: Moderate Loss / Mild Disturbance
  - `0`: Stable / Unaltered
  - `+1`: Moderate Gain / Regrowth
  - `+2`: Major Gain / Rapid Emergence ($\Delta \ge 2 \cdot \tau_{\text{gain}}$)
  - `-128`: Masked NoData

### 4. Rigorous Pre-Flight Alignment Safeguards:
Integrates the validation logic of Tool 6:
- Compares Coordinate Reference Systems (CRS).
- Verifies exact matching raster dimensions (Width, Height).
- Evaluates affine geotransform elements within a strict numerical tolerance ($10^{-5}$).
- If misaligned, fails fast with structured error diagnostics (`GRID_MISALIGNMENT`) rather than producing invalid subtraction artifacts.

### 5. Symmetric NoData & NaN Integrity:
- Extracts NoData tags from both $T_1$ and $T_2$ metadata.
- Evaluates IEEE 754 floating-point anomalies (NaN, Inf).
- Creates a symmetric composite valid mask:
  $$\text{Valid Mask} = \text{Valid}(T_1) \land \text{Valid}(T_2)$$
  Any pixel missing or corrupted in either observation is excluded from both the statistics and output rasters.

### 6. Geodesic Surface Area Accounting:
- Calculates exact metric ground area per pixel:
  - For Geographic CRS (`EPSG:4326`), scales longitude by $\cos(\text{latitude}_{\text{mid}})$.
  - For Projected CRS (UTM, State Plane), uses pixel resolution directly in meters ($|\text{res}_x \cdot \text{res}_y|$).
- Returns total raster area, valid AOI area, loss area, gain area, stable area, and severity distribution in both $\text{km}^2$ and hectares ($\text{ha}$).

---

## 3. Environment & Dependencies

### Python Runtime:
- Python 3.10, 3.11, 3.12, or 3.13

### Required Libraries:
```bash
pip install rasterio numpy pydantic fastmcp
```

| Package | Purpose |
| :--- | :--- |
| `rasterio` | Geospatial GeoTIFF I/O, geotransforms, and metadata management |
| `numpy` | High-performance vectorized array algebra and statistical percentiles |
| `pydantic` | Strict request validation, type enforcement, and schema generation |
| `fastmcp` | Model Context Protocol (MCP) tool server integration |

---

## 4. End-to-End Architectural Flow Diagram

```mermaid
flowchart TD
    A[Agent / LangGraph Client] -->|Invokes analyze_temporal_change| B[TemporalChangeRequest Validation]
    
    B -->|Check File Existence & Params| C{Files Exist & Valid?}
    C -- No --> E1[Return Structured validation_error JSON]
    
    C -- Yes --> D[Pre-Flight Grid Alignment QA: CRS, Dimensions, Transform]
    D --> E{Is Grid Aligned?}
    E -- No --> E2[Return GRID_MISALIGNMENT Error Diagnostics]
    
    E -- Yes --> F[Band Resolution: Index or Name Lookup e.g. NDVI, VV_dB]
    F --> G[Read T1 & T2 Arrays as Float32]
    
    G --> H[Symmetric NoData & NaN Filtering: Valid Mask = Valid T1 AND Valid T2]
    H --> I[Continuous Subtraction: Delta = T2 - T1]
    
    I --> J[Relative Shift Calculation: Delta % = Delta / |T1| * 100]
    I --> K[Statistical Distribution: Min, Max, Mean, Median, Std, Percentiles p01-p99, 10-Bin Histogram]
    
    K --> L[Threshold Evaluation: Absolute Delta vs Statistical Mean +/- k*Sigma]
    L --> M[Generate Discrete Classification Array: Loss, Stable, Gain, Severity]
    
    M --> N[Geodesic Area Accounting: km2, Hectares, % Valid AOI]
    
    N --> O1[Export continuous difference_raster.tif Float32]
    N --> O2[Export discrete change_mask.tif Int8]
    
    O1 & O2 --> P[Synthesize Comprehensive JSON Response]
    P --> Q[Downstream Tool 8 / AI Report Generator]
```

---

## 5. Input Schema & Parameter Specifications

| Field | Type | Required | Default | Description |
| :--- | :--- | :---: | :---: | :--- |
| `raster_before_path` | `str` | **Yes** | — | Absolute or relative path to the baseline/pre-event GeoTIFF ($T_1$). |
| `raster_after_path` | `str` | **Yes** | — | Absolute or relative path to the target/post-event GeoTIFF ($T_2$). |
| `band_selection` | `int \| str` | No | `1` | Band to compare: 1-based index or name string (e.g. `"NDVI"`, `"NDWI"`, `"VV_dB"`). |
| `threshold_type` | `"absolute" \| "statistical"` | No | `"absolute"` | Thresholding mode. `"absolute"` uses fixed numeric delta; `"statistical"` uses $\mu \pm k\sigma$. |
| `threshold_value` | `float` | No | `0.15` | Threshold magnitude (e.g., `0.15` for absolute NDVI shift, or `2.0` for $2\sigma$ significance). |
| `relative_change_threshold_percent` | `float` | No | `None` | Optional relative percentage cutoff (e.g. `20.0` for $\ge \pm 20\%$ relative shift). *(Linear products only; do not use with logarithmic SAR dB).* |
| `mask_encoding` | `"bipolar_3class" \| "severity_5class"` | No | `"bipolar_3class"` | Class encoding for `change_mask.tif` and JSON classification. |
| `output_dir` | `str` | No | `None` | Custom output directory for generated difference and mask GeoTIFFs. |
| `generate_difference_raster` | `bool` | No | `true` | Whether to write continuous delta ($T_2 - T_1$) Float32 GeoTIFF to disk. |
| `generate_change_mask` | `bool` | No | `true` | Whether to write discrete classified change mask Int8 GeoTIFF to disk. |

---

## 6. Output JSON Schema & Data Dictionary

A successful invocation returns a standardized JSON payload:

```json
{
  "status": "success",
  "tool": "Tool_7_analyze_temporal_change",
  "timestamp_utc": "2026-09-04T12:54:34.827050+00:00",
  "band_evaluated": {
    "band_name": "NDVI",
    "t1_band_index": 1,
    "t2_band_index": 1
  },
  "provenance": {
    "raster_before": "/path/to/sample_indices_t1.tif",
    "raster_after": "/path/to/sample_indices_t2.tif",
    "crs": "EPSG:4326",
    "grid_dimensions": { "width": 256, "height": 256 },
    "spatial_bounds": { "left": 77.1, "bottom": 28.5, "right": 77.3, "top": 28.7 },
    "pixel_ground_resolution_m2": 6616.45
  },
  "threshold_parameters": {
    "threshold_type": "absolute",
    "threshold_value": 0.15,
    "threshold_description": "Absolute Delta >= +/-0.1500",
    "effective_loss_threshold": -0.15,
    "effective_gain_threshold": 0.15,
    "relative_change_filter_percent": 20.0
  },
  "spatial_coverage": {
    "total_raster_area_km2": 433.6159,
    "valid_aoi_area_km2": 433.6159,
    "valid_fraction_percent": 100.0,
    "total_pixels": 65536,
    "valid_pixels": 65536,
    "masked_nodata_pixels": 0
  },
  "change_summary": {
    "significant_decrease": {
      "pixel_count": 6396,
      "area_km2": 42.3188,
      "area_hectares": 4231.88,
      "percentage_of_valid_aoi": 9.76
    },
    "stable_unaltered": {
      "pixel_count": 55560,
      "area_km2": 367.6101,
      "area_hectares": 36761.01,
      "percentage_of_valid_aoi": 84.78
    },
    "significant_increase": {
      "pixel_count": 3580,
      "area_km2": 23.6869,
      "area_hectares": 2368.69,
      "percentage_of_valid_aoi": 5.46
    },
    "net_change_area_km2": -18.6319
  },
  "severity_distribution": {
    "major_decrease": { "pixel_count": 6395, "area_km2": 42.3122, "area_hectares": 4231.22, "percentage_of_valid_aoi": 9.76 },
    "moderate_decrease": { "pixel_count": 1, "area_km2": 0.0066, "area_hectares": 0.66, "percentage_of_valid_aoi": 0.0 },
    "stable": { "pixel_count": 55560, "area_km2": 367.6101, "area_hectares": 36761.01, "percentage_of_valid_aoi": 84.78 },
    "moderate_increase": { "pixel_count": 3512, "area_km2": 23.237, "area_hectares": 2323.7, "percentage_of_valid_aoi": 5.36 },
    "major_increase": { "pixel_count": 68, "area_km2": 0.4499, "area_hectares": 44.99, "percentage_of_valid_aoi": 0.1 }
  },
  "delta_statistics": {
    "mean_delta": -0.0303,
    "median_delta": -0.0008,
    "std_delta": 0.1501,
    "min_delta": -0.5681,
    "max_delta": 0.3377,
    "percentiles": { "p01": -0.4921, "p05": -0.449, "p25": -0.0137, "p50": -0.0008, "p75": 0.0111, "p95": 0.2131, "p99": 0.2718 },
    "mean_relative_shift_percent": -20.1,
    "median_relative_shift_percent": -0.23
  },
  "delta_histogram": [ ... ],
  "generated_products": {
    "difference_raster_path": "/path/to/sample_indices_t1_vs_sample_indices_t2_NDVI_difference.tif",
    "change_mask_path": "/path/to/sample_indices_t1_vs_sample_indices_t2_NDVI_change_mask.tif",
    "mask_encoding": "bipolar_3class",
    "mask_legend": {
      "-1": "Significant Loss / Decrease",
      "0": "Stable / Insignificant Change",
      "1": "Significant Gain / Increase",
      "-128": "NoData / Masked Out"
    }
  }
}
```

---

## 7. The Downstream Handshake with Tool 8

The `change_mask_path` produced by Tool 7 serves as the primary zone mask for **Tool 8: `analyze_spatial_landcover_terrain`**:

```text
1. Tool 7 detects 42.32 km² of significant vegetation decrease and outputs `change_mask.tif`.
2. Tool 8 ingests `change_mask.tif` along with an ESA WorldCover / DEM raster.
3. Tool 8 cross-tabulates:
   - "82% of the detected loss occurred in Tree Cover (Class 10), and 18% in Cropland (Class 40)."
   - "The mean terrain slope of the impacted zone is 14.2° at an average elevation of 640 m."
```

---

## 8. Usage Examples

### Direct Python Execution:
```python
import json
from Tool_7_analyze_temporal_change.analyze_temporal_change import (
    TemporalChangeRequest,
    analyze_temporal_change
)

request = TemporalChangeRequest(
    raster_before_path="Tool_7_analyze_temporal_change/test_runs/sample_indices_t1.tif",
    raster_after_path="Tool_7_analyze_temporal_change/test_runs/sample_indices_t2.tif",
    band_selection="NDVI",
    threshold_type="absolute",
    threshold_value=0.15,
    relative_change_threshold_percent=20.0,
    mask_encoding="bipolar_3class"
)

result = analyze_temporal_change(request)
print(f"Detected {result['change_summary']['significant_decrease']['area_km2']} km2 of loss.")
```

### CLI Execution:
```bash
python Tool_7_analyze_temporal_change/analyze_temporal_change.py Tool_7_analyze_temporal_change/sample_input.json
```
