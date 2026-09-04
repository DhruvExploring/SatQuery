# SIH Geospatial Intelligence Tool Suite — Agent & LangGraph Integration Spec

## 1. System Overview

This document specifies the architecture, inter-tool workflows, decision trees, and integration contracts for the **7-Tool Geospatial Intelligence Suite**.

The system is designed with a strict **Separation of Concerns**:
- **Tools 1 to 5 (Data & Index Providers):** Autonomous micro-services that connect to satellite APIs (Sentinel Hub, Planetary Computer STAC, Open-Meteo), retrieve observations, execute server/local processing, validate rasters with `rasterio`, and return standard GeoTIFF rasters + structured metadata with **AOI-Level SCL Quality Validation**.
- **Tool 6 (Quality Assurance & Raster Inspector):** Universal pre-flight raster inspection and deep geospatial metadata extraction for both pipeline rasters and external user-provided GeoTIFFs.
- **Tool 7 (Geospatial Analysis & Feature Extraction Engine):** High-level production analytics engine that accepts single or multi-temporal rasters with optional auxiliary layers (LULC, DEM, Weather) and produces deterministic, unit-aware, ML/LLM-ready JSON features.
- **LangGraph / Agent Layer:** Governs the execution graph, decides which tools to invoke based on user intent, checks quality flags, triggers fallbacks (e.g. SAR when cloudy), and orchestrates data flow into Tool 7.

---

## 2. Tool Registry Matrix

| Tool ID | Directory | MCP Tool Name | Primary Provider / Tech | Primary Input | Primary Output |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Tool 1** | `Tool_1_fetch_optical_imagery` | `fetch_optical_imagery` | Sentinel-2 L2A (`B04, B03, B02`) | AOI BBox, Date range, Max cloud % | True-Color 3-Band GeoTIFF (UINT16) + AOI Quality JSON |
| **Tool 2** | `Tool_2_fetch_multispectral_imagery` | `fetch_multispectral_imagery` | Sentinel-2 L2A (`B02-B12`) | AOI BBox, Date range, Selected bands | Multi-Band Surface Reflectance GeoTIFF (FLOAT32) + Band Mapping JSON |
| **Tool 3** | `Tool_3_fetch_sar_imagery` | `fetch_sar_imagery` | Sentinel-1 GRD (SAR C-Band) | AOI BBox, Date range, Polarization, Strategy | Cloud-penetrating Backscatter GeoTIFF (FLOAT32 in dB) + Geometry Quality JSON |
| **Tool 4** | `Tool_4_fetch_weather_environment` | `fetch_weather_environment` | Open-Meteo / ECMWF ERA5 | AOI BBox or Point, Date range | Weather & Moisture Balance JSON + Stress Indicators |
| **Tool 5** | `Tool_5_compute_vegetation_indices` | `compute_vegetation_indices` | Local Vectorized NumPy / Rasterio | Input GeoTIFF, Requested indices | Multi-Band Index GeoTIFF (FLOAT32) + Summary Stats & Canopy Area JSON |
| **Tool 6** | `Tool_6_inspect_geotiff_metadata` | `inspect_geotiff_metadata` | Universal Local Rasterio QA Engine | Input GeoTIFF path, Optional compare path | Structural, Georeferencing, NoData Integrity & Compatibility JSON |
| **Tool 7** | `Tool_7_geo_analysis_tool` | `geo_analysis_tool` | Planetary STAC (WorldCover) + DEM | GeoTIFF(s) + Optional Auxiliary Rasters | ML/LLM-ready Geospatial Analytics JSON |

---

## 3. Global Geospatial Standards & Quality Contracts

All tools strictly adhere to these common formats to ensure zero-friction chaining:

1. **Bounding Box (`bbox`):** Always standard WGS84 coordinates in exact order:
   `[min_lon, min_lat, max_lon, max_lat]` (e.g. `[77.10, 28.50, 77.30, 28.70]`).
2. **Date Format:** ISO 8601 Calendar Date: `YYYY-MM-DD` (e.g. `"2025-01-01"`).
3. **Coordinate Reference System (`crs`):** Default standard is `"EPSG:4326"`.
4. **Standard Output Envelope (with AOI-Level SCL Quality):**
   ```json
   {
     "status": "success | error",
     "data": { "file_path": "...", "file_name": "...", "format": "GeoTIFF" },
     "source": { "provider": "...", "collection": "...", "scene_id": "...", "acquisition_time": "..." },
     "raster": { "width": 512, "height": 512, "band_count": 3, "crs": "EPSG:4326", "bounds": {...} },
     "quality": {
       "catalog_cloud_cover": 12.4,
       "aoi_cloud_cover": 3.1,
       "aoi_cloud_shadow": 1.2,
       "aoi_obstruction": 4.3,
       "valid": true
     },
     "flags": {
       "optical_quality_poor": false,
       "sar_recommended": false
     }
   }
   ```

---

## 4. Primary Workflow Architectures

### Path A: End-to-End Automated Pipeline
```text
                    USER / AGENT / LANGGRAPH
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
          ▼                   ▼                   ▼
      Tool 1              Tool 2              Tool 3
      Optical           Multispectral           SAR
          │                   │                   │
          │                   ▼                   │
          │                Tool 5                │
          │          Spectral Indices            │
          │                   │                   │
          └───────────┬───────┴───────────────────┘
                      │
                      ▼
                   Tool 6
             Universal GeoTIFF QA
                      │
                      │
Tool 4 ───────────────┤
Weather/Environment   │
                      ▼
                   Tool 7
       Geospatial Analysis & Change Detection
```

### Path B: User-Provided External GeoTIFF
```text
User / External Asset
      │
      ▼
   Tool 6 (Universal Pre-Flight QA & Profiler)
      │ (Validates CRS, NoData, Dtypes, ML-readiness)
      ▼
Downstream AI Router / Tool 5 / Tool 7
```

---

## 5. Tool 7 Decoupling & Graceful Degradation Contract

Tool 7 is architected so that **no specific auxiliary tool is strictly mandatory**. The agent can supply whatever data is available:

| Supplied Inputs to Tool 7 | Computed Outputs Produced by Tool 7 |
| :--- | :--- |
| **Only Single Optical Raster** | Spectral reflectance distribution, texture features, basic water/vegetation mask approximation. |
| **Two Optical Rasters (Before & After)** | Grid-aligned pixel diff, absolute change ($km^2$), reflectance delta, change intensity index. |
| **Multispectral / Index Rasters (Tool 5)** | Canopy vigor shifts, NDMI water stress, burn severity classification (NBR). |
| **Optical Rasters + LULC (WorldCover)** | Exact land-cover transition matrix, built-up growth ($km^2$), deforestation area ($km^2$), crop shift ($km^2$). |
| **Optical / SAR Rasters + DEM** | Elevation profile, slope gradient categorization, flood risk zonal mapping, terrain-corrected metrics. |
| **Rasters + Weather Metadata (Tool 4)** | Environmental correlation analysis (e.g. Drought severity vs NDVI drop, Rainfall anomaly vs Flood extent). |

---

## 6. Error Handling & Recovery Protocols for LangGraph

1. **`type: "validation_error"`**: Input parameters (bbox out of range, invalid date, missing file) failed validation. Agent must re-format inputs and retry.
2. **`type: "no_suitable_scene"`**: No satellite observation found for date/cloud filter. Agent strategy:
   - Expand the temporal window (e.g. from 15 days to 45 days).
   - Increase `max_cloud_cover` threshold.
   - Switch to **Tool 3 (SAR)** if cloud persistence is the issue.
3. **`type: "service_error"`**: Remote provider rate limit or timeout. Tool handles exponential backoff automatically up to 3 retries.
