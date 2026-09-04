# Tool 5: compute_vegetation_indices (Scientific Multi-Index Spectral Engine)

## 1. Overview & Purpose

**`compute_vegetation_indices`** is a dedicated Earth Observation (EO) spectral index computation engine built for Model Context Protocol (MCP) clients and LangGraph autonomous agents. Its primary responsibility is to transform **calibrated Bottom-Of-Atmosphere (BOA) Surface Reflectance multispectral GeoTIFF rasters (from Tool 2 or external EO assets)** into **calibrated multi-band scientific spectral index GeoTIFFs** and comprehensive statistical distributions.

### Primary Workflow: Chained Pipeline
```text
Tool 2 (fetch_multispectral_imagery)
  │ (Outputs 8-band BOA Reflectance GeoTIFF)
  ▼
Tool 5 (compute_vegetation_indices)
  │ (Applies zero-division safe array math)
  ▼
Index GeoTIFF (10 Bands: NDVI, EVI, SAVI, GNDVI, NDRE_B5, NDRE_B7, NDMI, NDWI, MSAVI, NBR) + Statistical JSON
  │
  ▼
Tool 7 (Production Geospatial Analysis & Change Detection Engine)
```

---

## 2. Security & API Credential Configuration

> [!NOTE]
> **This tool operates entirely locally on local GeoTIFF files and does NOT require an API key or remote service credentials.**

## 3. Environment & Dependencies

### Python Runtime:
- Python 3.10, 3.11, 3.12, or 3.13

### Required Libraries:
```bash
pip install rasterio numpy pydantic fastmcp
```

| Package | Purpose in Tool |
| :--- | :--- |
| `rasterio` | Local GeoTIFF reading, affine coordinate transformations, NoData masking, and multi-band index writing |
| `numpy` | High-performance, vectorized floating-point array mathematics and statistical percentiles |
| `pydantic` | Strict input validation of file existence, band mapping, and index selection |
| `fastmcp` | Standardized Model Context Protocol (MCP) server integration |

---

## 3. End-to-End Architectural Flow Diagram

```mermaid
flowchart TD
    A[Agent / LangGraph Client] -->|Invokes compute_vegetation_indices| B[VegetationIndicesRequest Validation]
    
    B -->|Check File Exists, Validate Requested Indices| C{Is Input Valid?}
    C -- No --> E1[Return Structured validation_error JSON]
    
    C -- Yes --> D[Rasterio Input Inspection]
    D -->|Read Dimensions, CRS, Transform, NoData| F[Extract Spectral Bands via band_mapping]
    
    F --> G[Reflectance Scaling: Auto-scale [0, 10000] to Physical [0.0, 1.0]]
    G --> H[Vectorized Safe Mathematical Formula Processor]
    
    H --> H1[NDVI = NIR - Red / NIR + Red]
    H --> H2[EVI = 2.5 * NIR - Red / NIR + 6Red - 7.5Blue + 1]
    H --> H3[SAVI = NIR - Red / NIR + Red + 0.5 * 1.5]
    H --> H4[GNDVI = NIR - Green / NIR + Green]
    H --> H5[NDRE_B5 = NIR - B05 / NIR + B05]
    H --> H6[NDRE_B7 = NIR - B07 / NIR + B07]
    H --> H7[NDMI = NIR - SWIR1 / NIR + SWIR1]
    H --> H8[NDWI = Green - NIR / Green + NIR]
    H --> H9[MSAVI = Modified Soil Adjusted Formulation]
    H --> H10[NBR = NIR - SWIR2 / NIR + SWIR2]
    
    H1 & H2 & H3 & H4 & H5 & H6 & H7 & H8 & H9 & H10 --> I[Zero-Division & NaN/Inf Masking to NoData -9999.0]
    
    I --> J[Write Multi-Band FLOAT32 Index GeoTIFF to Disk (band_count == len(indices))]
    J --> K[Compute Statistical Metrics per Index: Min, Max, Mean, Median, Std, P10, P90]
    K --> L[Calculate Heuristic Canopy Area Coverage in km2 & % using Exact Physical Pixel Area]
    
    L --> M[Assemble Structured JSON Output Envelope with Exact GSD & Resampling Provenance]
    M --> N[Tool 7 / Agricultural Health & Forestry Models]
```

---

## 4. Scientific Index Formulas & Biophysical Interpretations

All 10 indices are computed with strict numerical stability (handling zero-division and invalid pixel masks):

| Index | Name & Formula | Input Bands | Primary Remote Sensing Purpose |
| :--- | :--- | :---: | :--- |
| **`NDVI`** | $\frac{\text{NIR} - \text{Red}}{\text{NIR} + \text{Red}}$ | `B08`, `B04` | General vegetation greenness, biomass quantity, and canopy photosynthetic activity. |
| **`EVI`** | $2.5 \times \frac{\text{NIR} - \text{Red}}{\text{NIR} + 6 \cdot \text{Red} - 7.5 \cdot \text{Blue} + 1}$ | `B08`, `B04`, `B02` | Enhanced vegetation index optimized for high-biomass regions with reduced atmospheric and canopy background noise. |
| **`SAVI`** | $\frac{\text{NIR} - \text{Red}}{\text{NIR} + \text{Red} + 0.5} \times 1.5$ | `B08`, `B04` | Soil-Adjusted Vegetation Index; suppresses soil reflectance interference in arid or sparse crop fields. |
| **`GNDVI`** | $\frac{\text{NIR} - \text{Green}}{\text{NIR} + \text{Green}}$ | `B08`, `B03` | Green NDVI; highly sensitive to chlorophyll concentration and late-season crop maturity. |
| **`NDRE_B5`** | $\frac{\text{NIR} - \text{B05}}{\text{NIR} + \text{B05}}$ | `B08`, `B05` | Red Edge 1 ($705\text{ nm}$); sensitive to early nitrogen deficiency and cellular stress before visible browning. |
| **`NDRE_B7`** | $\frac{\text{NIR} - \text{B07}}{\text{NIR} + \text{B07}}$ | `B08`, `B07` | Red Edge 3 ($783\text{ nm}$); deep canopy penetration for mature crop biomass estimation. |
| **`NDMI`** | $\frac{\text{NIR} - \text{SWIR1}}{\text{NIR} + \text{SWIR1}}$ | `B08`, `B11` | Normalized Difference Moisture Index; direct measurement of leaf canopy water content and plant drought stress. |
| **`NDWI`** | $\frac{\text{Green} - \text{NIR}}{\text{Green} + \text{NIR}}$ | `B03`, `B08` | McFeeters Surface Water Index; delineates open water bodies from terrestrial background. |
| **`MSAVI`** | $\frac{2 \cdot \text{NIR} + 1 - \sqrt{(2 \cdot \text{NIR} + 1)^2 - 8(\text{NIR} - \text{Red})}}{2}$ | `B08`, `B04` | Modified SAVI; self-adjusting soil brightness correction for early-stage crop emergence. |
| **`NBR`** | $\frac{\text{NIR} - \text{SWIR2}}{\text{NIR} + \text{SWIR2}}$ | `B08`, `B12` | Normalized Burn Ratio; wildfire burn scar delineation and post-fire ecological recovery monitoring. |

---

## 5. Input Schema & Parameter Specifications

| Field | Type | Required | Default | Valid Range / Constraints | Description |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `file_path` | `str` | **Yes** | — | Valid local path to `.tif` | Absolute path to the multispectral surface reflectance GeoTIFF. |
| `indices` | `list[str]` | No | All 10 | Subset of valid indices | List of spectral indices to compute. Output band count strictly matches `len(indices)`. |
| `band_mapping` | `dict[str, str]` | No | Auto/Tool 2 | e.g. `{"Band_1": "B02", ...}` | Explicit mapping of raster bands to Sentinel-2 spectral band codes. |
| `calculate_heuristic_classification` | `bool` | No | `true` | `true`, `false` | Computes rule-based canopy vigor area coverage in $\text{km}^2$ and $\%$. |
| `output_dir` | `str` | No | `null` | Valid directory path | Custom directory for generated index GeoTIFF. |

---

## 6. Spatial Resolution, GSD & Provenance Tracking

The tool strictly distinguishes between **source satellite sensor resolution** and the **actual physical output grid resolution**:
- **Source Sentinel-2 Band Resolutions:**
  - $10\text{ m}$ Native: `B02` (Blue), `B03` (Green), `B04` (Red), `B08` (NIR)
  - $20\text{ m}$ Native: `B05` (Red Edge 1), `B07` (Red Edge 3), `B11` (SWIR-1), `B12` (SWIR-2)
- **Output Raster Resolution:** $0.00078125^\circ \times 0.00078125^\circ$ ($\approx 81.4\text{ m/pixel}$ average GSD at mid-latitudes for a $256 \times 256$ grid over $0.2^\circ \times 0.2^\circ$).
- **Resampling Provenance:** Resampling occurs at `resampling_stage: "Tool_2_provider_level"` using `resampling_method: "bilinear"`. Tool 5 itself performs **no spatial resampling**, directly inheriting the spatial grid and transform of Tool 2.
- **Surface Area Calculations:** All area computations ($\text{km}^2$) use the exact geographic pixel area derived from the raster's affine transform rather than an idealized assumption of $10\text{ m}$ pixels.

---

## 7. Heuristic Vegetation Area Classification

When `calculate_heuristic_classification` is enabled and `NDVI` is computed, the tool calculates rule-based canopy vigor categories:
- **Dense Vegetation ($NDVI > 0.6$):** High biomass forest or healthy dense crop canopy.
- **Moderate Vegetation ($0.3 \le NDVI \le 0.6$):** Typical grassland, shrubland, or developing crops.
- **Sparse Vegetation ($0.1 \le NDVI < 0.3$):** Semi-arid scrubland or early planting.
- **Low NDVI / Non-Vegetated or Water ($NDVI < 0.1$):** Bare soil, built-up surfaces, shadows, or open water.

*(Note: These categories are explicitly flagged as **heuristic indicators**, not universal ground-truth land cover).*

---

## 8. Output Contract & Data Structure

```json
{
  "status": "success",
  "data": {
    "file_path": "c:/Users/User/Desktop/Tools/Tool_5_compute_vegetation_indices/test_runs/sample_indices_output.tif",
    "file_name": "sample_indices_output.tif",
    "format": "GeoTIFF"
  },
  "source_raster": {
    "input_file": "sample_multispectral_output.tif",
    "width": 256,
    "height": 256,
    "crs": "EPSG:4326"
  },
  "raster": {
    "width": 256,
    "height": 256,
    "band_count": 10,
    "dtype": "float32",
    "crs": "EPSG:4326",
    "nodata": -9999.0,
    "band_mapping": {
      "Band_1": "NDVI",
      "Band_2": "EVI",
      "Band_3": "SAVI",
      "Band_4": "GNDVI",
      "Band_5": "NDRE_B5",
      "Band_6": "NDRE_B7",
      "Band_7": "NDMI",
      "Band_8": "NDWI",
      "Band_9": "MSAVI",
      "Band_10": "NBR"
    }
  },
  "resolution": {
    "native_inputs_m": {
      "B02": 10,
      "B03": 10,
      "B04": 10,
      "B05": 20,
      "B07": 20,
      "B08": 10,
      "B11": 20,
      "B12": 20
    },
    "output_resolution_deg": 0.00078125,
    "output_resolution_m": null,
    "approx_ground_sampling_distance_m": {
      "x_m": 76.36,
      "y_m": 86.39,
      "mean_gsd_m": 81.38
    },
    "resampling_stage": "Tool_2_provider_level",
    "resampling_method": "bilinear",
    "provenance_note": "Output raster grid (81.38m/pixel) is directly inherited from Tool 2 without secondary resampling. Native 10m/20m Sentinel-2 bands were resampled during Tool 2 retrieval."
  },
  "statistics": {
    "NDVI": {
      "valid_pixel_count": 65536,
      "nodata_pixel_count": 0,
      "valid_pixel_percentage": 100.0,
      "min": -1.0,
      "max": 0.924,
      "mean": 0.358,
      "median": 0.367,
      "std_dev": 0.222,
      "p10": 0.087,
      "p90": 0.636
    }
  },
  "heuristic_classification": {
    "method": "rule_based_heuristic",
    "qualifier": "Heuristic thresholds for general canopy vigor; not ground-truth land cover.",
    "dense_vegetation_pct": 14.3,
    "dense_vegetation_km2": 61.81,
    "moderate_vegetation_pct": 46.0,
    "moderate_vegetation_km2": 198.84,
    "sparse_vegetation_pct": 27.87,
    "sparse_vegetation_km2": 120.49,
    "low_ndvi_non_vegetated_or_water_pct": 11.83,
    "low_ndvi_non_vegetated_or_water_km2": 51.15
  }
}
```

---

## 9. Downstream AI & Tool 7 Integration Hooks

- **Tool 7 (Land Degradation & Change Detection):** Ingests multi-temporal index GeoTIFFs (e.g., $NDVI_{T1}$ vs $NDVI_{T2}$) to quantify deforestation, desertification, or crop growth in absolute $\text{km}^2$.
- **Agricultural Stress Fusion:** Combines NDMI (leaf water) and NDRE (chlorophyll stress) with Tool 4's `water_balance_mm` to isolate crop irrigation deficiencies from regional meteorological moisture deficits.

---

## 10. Error Output Schema

```json
{
  "status": "error",
  "error": {
    "type": "validation_error | service_error",
    "message": "Detailed actionable error message."
  }
}
```
