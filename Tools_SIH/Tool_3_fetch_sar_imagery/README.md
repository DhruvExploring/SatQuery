# Tool 3: fetch_sar_imagery (Sentinel-1 Synthetic Aperture Radar)

## 1. Overview & Purpose

**`fetch_sar_imagery`** is a dedicated active microwave Earth Observation (EO) data ingestion tool built for Model Context Protocol (MCP) clients and LangGraph autonomous agents. Its primary responsibility is to discover, retrieve, orthorectify, and calibrate **Synthetic Aperture Radar (SAR) Ground Range Detected (GRD) imagery from the ESA Sentinel-1 constellation**.

### The Radar Superpower: All-Weather & Day/Night Vision
Optical sensors (Sentinel-2, Landsat) rely on solar illumination and are completely blinded by clouds, fog, heavy smoke, rainstorms, and darkness. **Sentinel-1 SAR transmits its own active C-band microwave pulses (~5.405 GHz, ~5.6 cm wavelength)** that penetrate atmospheric obstructions with zero attenuation. 

This tool serves as the **critical fallback and primary sensor** during:
- Monsoons, cyclones, severe storms, and continuous cloud cover.
- Rapid flood inundation and standing water mapping (water appears pitch black $\le -18\text{ dB}$ due to specular radar reflection).
- Oil spill and coastal coastline detection.
- Structural urban backscatter and soil moisture change monitoring.

---

## 2. Satellite Constellation Status & Radar Specifications

### Sentinel-1 Constellation Status:
- **Active Operational Satellites:** **Sentinel-1C** and **Sentinel-1D** are the primary active operational satellites delivering real-time SAR radar acquisitions.
- **Historical Archive Satellites:** 
  - **Sentinel-1A:** Operated from April 2014 until being formally retired from active operational service on 29 June 2026. Its complete 12-year historical global data archive remains permanently accessible via the collection.
  - **Sentinel-1B:** Operated from April 2016 until a power unit anomaly in December 2021 (mission formally concluded in August 2022; historical global archive 2016–2021 remains fully accessible).
- **Archive Compatibility:** The tool queries the unified `sentinel-1-grd` collection, ensuring full backward and forward compatibility — seamlessly retrieving historical Sentinel-1A/1B imagery for past dates and active Sentinel-1C/1D imagery for current/recent dates without any hardcoded satellite ID restrictions.
- **Product Collection:** `sentinel-1-grd` (Level-1 Ground Range Detected)
- **Sensor:** C-band Synthetic Aperture Radar (C-SAR)
- **Primary Acquisition Mode:** `IW` (Interferometric Wide Swath — 250 km swath, 10 m resolution)
- **Orthorectification:** `GAMMA0_TERRAIN` (Radiometrically terrain-corrected using Copernicus DEM)
- **Polarization Channels:**
  - **`VV` (Vertical transmit, Vertical receive):** Ideal for open surface roughness, calm water body mapping, soil moisture.
  - **`VH` (Vertical transmit, Horizontal receive):** Cross-polarization sensitive to volume scattering from vegetation canopies, agricultural crops, and forests.
- **Radiometric Output:** 2-Band GeoTIFF (`FLOAT32`, calibrated backscatter coefficient in **Decibels ($\text{dB}$)**).

### Remote APIs Used:
1. **OAuth2 OpenID Connect Authentication:**
   `https://services.sentinel-hub.com/auth/realms/main/protocol/openid-connect/token`
2. **STAC Catalog Search API v1.0:**
   `https://services.sentinel-hub.com/catalog/v1/search`
3. **Sentinel Hub Processing API v1.0:**
   `https://services.sentinel-hub.com/process/v1`

---

## 3. Security & API Credential Configuration

> [!IMPORTANT]
> **This public repository does NOT contain real API keys or OAuth secrets.**

### Credential Requirements:
- **Provider:** [Sentinel Hub / Copernicus Data Space Ecosystem](https://apps.sentinel-hub.com/dashboard/#/account/settings)
- **Required Credentials:** OAuth 2.0 Client ID and Client Secret.
- **Official Console URL:** [https://apps.sentinel-hub.com/dashboard/#/account/settings](https://apps.sentinel-hub.com/dashboard/#/account/settings)
- **Environment Variables:**
  - `SENTINEL_CLIENT_ID` (or `SENTINELHUB_CLIENT_ID`)
  - `SENTINEL_CLIENT_SECRET` (or `SENTINELHUB_CLIENT_SECRET`)
- **Code Location:** `fetch_sar_imagery.ipynb` (Section 3: Configuration / `CONFIG = ToolConfig(...)`).
- **Configuration Instructions:**
  Create a `.env` file in the project root or export variables in your shell:
  ```bash
  export SENTINEL_CLIENT_ID="your_client_id_here"
  export SENTINEL_CLIENT_SECRET="your_client_secret_here"
  ```
  *(Never commit your `.env` file or credentials to GitHub).*

## 4. Environment & Dependencies

### Python Runtime:
- Python 3.10, 3.11, 3.12, or 3.13

### Required Libraries:
```bash
pip install requests rasterio numpy pydantic fastmcp
```

| Package | Purpose in Tool |
| :--- | :--- |
| `requests` | High-performance HTTP communication with Sentinel Hub APIs |
| `rasterio` | Multichannel radar GeoTIFF verification, CRS, affine bounds, and dB distribution inspection |
| `numpy` | Array statistics, dB range checks, and radar shadow/incidence angle scoring |
| `pydantic` | Strict input validation (selection strategy, polarizations, orbit states, coordinates, dates) |
| `fastmcp` | Standardized Model Context Protocol (MCP) server integration |

---

## 4. End-to-End Architectural Flow Diagram

```mermaid
flowchart TD
    A[Agent / LangGraph Client] -->|Invokes fetch_sar_imagery| B[SARSatelliteRequest Validation]
    
    B -->|Validate Selection Strategy, Polarization, Orbit, BBox, Dates| C{Is Input Valid?}
    C -- No --> E1[Return Structured validation_error JSON]
    
    C -- Yes --> D[SentinelHubAuth: Token Manager]
    D -->|Check Cache| D1{Valid Token in Memory?}
    D1 -- Yes --> F[SentinelHubHTTPClient]
    D1 -- No --> D2[POST OAuth /token & Cache with 60s Buffer]
    D2 --> F
    
    F --> G[Search STAC Catalog: collections=['sentinel-1-grd']]
    G --> H[Retrieve Candidate SAR Acquisitions]
    H --> I[Filter by Orbit Direction ASCENDING/DESCENDING/BOTH]
    
    I --> J{SAR Observations Found?}
    J -- No --> E2[Return Structured no_suitable_scene JSON]
    
    J -- Yes --> K[Intent-Aware Scene Selection: most_recent / closest_to_start / closest_to_end]
    K --> L[Evaluate Radar Geometry Quality: shadowMask + localIncidenceAngle]
    
    L --> M[Generate SAR Evalscript: Linear -> Decibels dB]
    M --> N[Build Process Payload with GAMMA0_TERRAIN Orthorectification]
    N --> O[Execute Processing API with Exact Acquisition Instant]
    
    O --> P[Stream Dual-Polarization GeoTIFF FLOAT32 Bytes to Disk]
    P --> Q[Rasterio Inspection: Validate Dimensions, Band Count, CRS, Bounds]
    
    Q --> R{Is GeoTIFF Valid & Non-Empty?}
    R -- No --> E3[Return Structured service_error JSON]
    
    R -- Yes --> S[Extract Band Mappings: Band_1 -> VV_dB, Band_2 -> VH_dB]
    S --> T[Evaluate Geometry Flags: radar_geometry_poor / water_mapping_ready]
    T --> U[Return Success Envelope: Raster Path + Selection Strategy + Radar Quality JSON]
    U --> V[Tool 7 / Flood Inundation Analysis / Downstream AI]
```

---

## 5. Input Schema & Parameter Specifications

### Input Parameter Table:

| Field | Type | Required | Default | Valid Range / Constraints | Description |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `bbox` | `list[float]` | **Yes** | — | Exactly 4 floats: `[min_lon, min_lat, max_lon, max_lat]` | Longitude: `[-180, 180]`, Latitude: `[-90, 90]`. Must satisfy `min_lon < max_lon` and `min_lat < max_lat`. |
| `start_date` | `str` | **Yes** | — | `YYYY-MM-DD` | Start of temporal search window. |
| `end_date` | `str` | **Yes** | — | `YYYY-MM-DD` | End of temporal search window. Must satisfy `start_date <= end_date`. |
| `scene_selection` | `str` | No | `"most_recent"` | `"most_recent"`, `"closest_to_start_date"`, `"closest_to_end_date"` | **Intent-aware selection strategy**. Crucial for before/after temporal matching. |
| `polarization` | `list[str]` | No | `["VV", "VH"]` | `["VV"]`, `["VH"]`, `["VV", "VH"]`, `["HH"]`, `["HV"]` | Radar transmit/receive polarizations to extract. |
| `orbit_direction`| `str` | No | `"BOTH"` | `"ASCENDING"`, `"DESCENDING"`, `"BOTH"` | Pass direction of the satellite orbit. |
| `width` | `int` | No | `512` | `1` to `4096` | Output GeoTIFF raster pixel width. |
| `height` | `int` | No | `512` | `1` to `4096` | Output GeoTIFF raster pixel height. |
| `crs` | `str` | No | `"EPSG:4326"` | `"EPSG:4326"` | Coordinate reference system for spatial bounds. |

---

## 6. Intent-Aware Scene Selection Logic

Rather than blindly selecting the newest scene, the tool supports explicit acquisition preferences:
1. **`most_recent` (Default):** Best for real-time monitoring and latest situation assessment.
2. **`closest_to_start_date`:** In a multi-temporal change detection task (e.g. Pre-Flood Baseline), selects the SAR observation closest to the beginning of the temporal window.
3. **`closest_to_end_date`:** In a post-disaster evaluation, selects the observation closest to the peak/end event date.

The selection strategy used is explicitly returned in `metadata.selection.strategy`.

---

## 7. Radar Geometry & Terrain Shadow Quality

In mountainous or rugged terrain, radar signals suffer from **radar shadow** (areas hidden from radar illumination) and **foreshortening/layover**. Because radar shadow pixels exhibit low backscatter (similar to water), downstream flood tools could generate false-positive water detections if geometry quality is unverified.

The tool inspects the auxiliary geometry layers:
- **`shadowMask`:** Quantifies the fraction of pixels obscured by terrain shadow (`radar_shadow_fraction`).
- **`localIncidenceAngle`:** Checks if the local radar angle is within reliable bounds ($15^\circ$ to $65^\circ$).
- **`geometry_quality`:** Classified as `"good"` or `"degraded"`.
- **`flags.radar_geometry_poor`:** Triggered when `radar_shadow_fraction > 0.08`, alerting Tool 7 that terrain masking is required for water classification.

---

## 8. Output Contract & Data Structure

### 1. Physical GeoTIFF Properties:
- **File Format:** GeoTIFF (`.tif`)
- **Band Count:** Equal to `len(polarization)` requested (typically 2).
- **Data Type (`dtype`):** `float32` (calibrated backscatter in $\text{dB}$).
- **Band 1:** `VV_dB`
- **Band 2:** `VH_dB`
- **Embedded Metadata:** CRS (`EPSG:4326`), Affine transform, spatial bounding box.

### 2. Output JSON Schema:
```json
{
  "status": "success",
  "data": {
    "file_path": "c:/Users/User/Desktop/Tools/Tool_3_fetch_sar_imagery/test_runs/sample_sar_output.tif",
    "file_name": "sample_sar_output.tif",
    "format": "GeoTIFF"
  },
  "source": {
    "provider": "Sentinel Hub",
    "collection": "sentinel-1-grd",
    "scene_id": "S1A_IW_GRDH_1SDV_20250130T125514_057674_071BA5_E687",
    "acquisition_time": "2025-01-30T12:55:14Z",
    "instrument_mode": "IW",
    "orbit_direction": "ASCENDING",
    "polarization": [
      "VV",
      "VH"
    ]
  },
  "selection": {
    "strategy": "most_recent",
    "orbit_direction": "BOTH"
  },
  "request": {
    "bbox": [
      77.1,
      28.5,
      77.3,
      28.7
    ],
    "start_date": "2025-01-01",
    "end_date": "2025-01-31",
    "scene_selection": "most_recent",
    "polarization": [
      "VV",
      "VH"
    ],
    "orbit_direction": "BOTH"
  },
  "raster": {
    "width": 512,
    "height": 512,
    "band_count": 2,
    "dtype": "float32",
    "crs": "EPSG:4326",
    "unit": "dB (Decibels)",
    "band_mapping": {
      "Band_1": "VV_dB",
      "Band_2": "VH_dB"
    },
    "bounds": {
      "left": 77.1,
      "bottom": 28.5,
      "right": 77.3,
      "top": 28.7
    },
    "resolution": {
      "x": 0.000390625,
      "y": 0.000390625
    },
    "nodata": null
  },
  "quality": {
    "cloud_penetrating": true,
    "weather_independent": true,
    "day_night_capability": true,
    "radar_shadow_fraction": 0.0,
    "mean_incidence_angle_deg": 39.99,
    "geometry_quality": "good",
    "valid": true
  },
  "flags": {
    "radar_valid": true,
    "radar_geometry_poor": false,
    "water_mapping_ready": true
  }
}
```

---

## 9. Downstream AI & Tool Integration Hooks

- **Optical Fallback Hook:** When Tool 1 or Tool 2 returns `flags.sar_recommended: true`, LangGraph invokes `fetch_sar_imagery` to obtain an unclouded radar view.
- **Tool 7 (Flood & Disaster Analysis):** Ingests the `VV_dB` and `VH_dB` channels to perform threshold-based water extraction ($VV \le -16\text{ dB}$) and calculate flooded area in $\text{km}^2$.

---

## 10. Error Output Schema

```json
{
  "status": "error",
  "error": {
    "type": "validation_error | no_suitable_scene | service_error",
    "message": "Detailed actionable error message."
  }
}
```
