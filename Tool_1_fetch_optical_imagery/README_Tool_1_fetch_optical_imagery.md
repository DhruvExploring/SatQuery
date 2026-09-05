# Tool 1: fetch_optical_imagery (Sentinel-2 L2A Optical RGB)

## 1. Overview & Purpose

**`fetch_optical_imagery`** is a dedicated satellite data ingestion tool built for Model Context Protocol (MCP) clients and LangGraph autonomous agents. Its primary responsibility is to discover, retrieve, validate, and package **True-Color RGB optical satellite imagery** from the **European Space Agency (ESA) Sentinel-2 constellation** (Level-2A Bottom-Of-Atmosphere reflectance) over any global Area of Interest (AOI) and temporal window.

### Key Distinction: AOI-Level Quality Validation
Unlike naive satellite query tools that only rely on global catalog cloud metadata (which covers an entire $100\text{ km} \times 100\text{ km}$ tile), this tool includes an **AOI-level Scene Classification Layer (SCL) Quality Validation stage**. It inspects cloud and shadow contamination specifically inside the user's requested AOI, ensuring that the selected scene is truly unobstructed over the area of interest.

---

## 2. Satellite & Provider Specifications

- **Data Provider:** [Sentinel Hub](https://www.sentinel-hub.com/) / [Copernicus Data Space Ecosystem (CDSE)](https://dataspace.copernicus.eu/)
- **Provider Console / Dashboard:** [Sentinel Hub Dashboard](https://apps.sentinel-hub.com/dashboard/)
- **Satellite Constellation:** Sentinel-2 (Sentinel-2A, Sentinel-2B, Sentinel-2C)
- **Product Collection:** `sentinel-2-l2a` (Level-2A Bottom-Of-Atmosphere / Surface Reflectance)
- **Native Spatial Resolution:** 10 meters per pixel for visible RGB bands (`B04`, `B03`, `B02`)
- **Quality Validation Layer:** Sentinel-2 `SCL` (Scene Classification Layer, 20m)
- **Radiometric Output:** 3-Band GeoTIFF (`UINT16`, surface reflectance scaled by factor of $10,000$)

### Remote APIs Used:
1. **OAuth2 OpenID Connect Authentication:**
   `https://services.sentinel-hub.com/auth/realms/main/protocol/openid-connect/token`
2. **SpatioTemporal Asset Catalog (STAC) Search API v1.0:**
   `https://services.sentinel-hub.com/catalog/v1/search`
3. **Sentinel Hub Processing API v1.0:**
   `https://services.sentinel-hub.com/process/v1`

---

## 3. Environment & Dependencies

### Python Runtime:
- Python 3.10, 3.11, 3.12, or 3.13

### Required Libraries:
```bash
pip install requests rasterio numpy pydantic fastmcp
```

| Package | Purpose in Tool |
| :--- | :--- |
| `requests` | High-performance HTTP communication with Sentinel Hub APIs |
| `rasterio` | Geospatial raster inspection (CRS, affine transform, dimensions, dtypes) |
| `numpy` | High-speed pixel array histogram calculations for SCL AOI quality scoring |
| `pydantic` | Strict type checking, boundary enforcement, and validation of agent inputs |
| `fastmcp` | Standardized Model Context Protocol (MCP) server integration |

---

## 4. End-to-End Architectural Flow Diagram

```mermaid
flowchart TD
    A[Agent / LangGraph Client] -->|Invokes fetch_optical_imagery| B[OpticalSatelliteRequest Validation]
    
    B -->|Check Coordinates, Dates, Bounds| C{Is Input Valid?}
    C -- No --> E1[Return Structured validation_error JSON]
    
    C -- Yes --> D[SentinelHubAuth: Token Manager]
    D -->|Check Cache| D1{Token in Memory & Valid?}
    D1 -- Yes --> F[SentinelHubHTTPClient]
    D1 -- No --> D2[POST OAuth /token & Cache with 60s Safety Margin]
    D2 --> F
    
    F --> G[Search STAC Catalog API: collections=['sentinel-2-l2a']]
    G --> H[Retrieve Top Candidate STAC Observations]
    H --> I[Normalize Candidate Scenes]
    
    I --> J{Candidate Scenes Found?}
    J -- No --> E2[Return Structured no_suitable_scene JSON]
    
    J -- Yes --> K[AOI-Level SCL Quality Stage]
    K --> K1[Evaluate Top 5 Candidates via SCL Layer over exact AOI]
    K1 --> K2[Compute aoi_cloud_cover, aoi_cloud_shadow, aoi_obstruction]
    
    K2 --> L[Deterministic Selection: Lowest aoi_obstruction + Lowest global cloud]
    L --> M[Generate Optical Evalscript B04/B03/B02 -> UINT16]
    M --> N[Execute Processing API with Exact Selected Acquisition Instant]
    
    N --> O[Download Full-Resolution GeoTIFF Raster Bytes]
    O --> P[Rasterio Inspection: Validate Dimensions, Bounds, CRS, Band Count]
    
    P --> Q{Is GeoTIFF Valid?}
    Q -- No --> E3[Return Structured service_error JSON]
    
    Q -- Yes --> R[Evaluate Quality Flags: optical_quality_poor / sar_recommended based on AOI]
    R --> S[Return Success Envelope: Raster Path + AOI Quality Metadata JSON]
    S --> T[LangGraph / Downstream AI Processing]
```

---

## 5. AOI-Level SCL Quality Inspection Logic

### Why Global Metadata is Insufficient:
A single Sentinel-2 granule spans $100\text{ km} \times 100\text{ km}$ ($10,000\text{ km}^2$). A scene with only $10\%$ global cloud cover might have clouds concentrated directly over the user's $5\text{ km} \times 5\text{ km}$ AOI (100% blocked). Conversely, a scene with $35\%$ global cloud cover might be crystal clear over the AOI.

### SCL Classification Matrix:
The tool queries the Sentinel-2 **`SCL`** layer specifically over the requested AOI bounds:
- **Cloud Shadows (`SCL == 3`):** Accounted in `aoi_cloud_shadow`
- **Cloud Medium / High Probability & Thin Cirrus (`SCL in [8, 9, 10]`):** Accounted in `aoi_cloud_cover`
- **Snow / Ice (`SCL == 11`):** Accounted in `aoi_snow_ice`
- **Total AOI Obstruction:**
  $$\text{aoi\_obstruction} = \text{aoi\_cloud\_cover} + \text{aoi\_cloud\_shadow}$$

### Deterministic Multi-Candidate Ranking:
Candidate scenes from the catalog are evaluated, and the tool selects the scene that minimizes:
$$\text{Rank Key} = (\text{aoi\_obstruction}, \text{catalog\_cloud\_cover}, \text{acquisition\_time})$$

---

## 6. Input Schema & Parameter Specifications

| Field | Type | Required | Default | Valid Range / Constraints | Description |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `bbox` | `list[float]` | **Yes** | — | Exactly 4 floats: `[min_lon, min_lat, max_lon, max_lat]` | Longitude: `[-180, 180]`, Latitude: `[-90, 90]`. Must satisfy `min_lon < max_lon` and `min_lat < max_lat`. |
| `start_date` | `str` | **Yes** | — | `YYYY-MM-DD` | Start of temporal search window. |
| `end_date` | `str` | **Yes** | — | `YYYY-MM-DD` | End of temporal search window. Must satisfy `start_date <= end_date`. |
| `max_cloud_cover`| `float` | No | `30.0` | `0.0` to `100.0` | Maximum catalog cloud-cover percentage threshold. |
| `width` | `int` | No | `512` | `1` to `4096` | Output GeoTIFF raster pixel width. |
| `height` | `int` | No | `512` | `1` to `4096` | Output GeoTIFF raster pixel height. |
| `crs` | `str` | No | `"EPSG:4326"` | `"EPSG:4326"` | Coordinate reference system for spatial bounds. |

---

## 7. Token Optimization, Quota Protection & Cost Controls

1. **OAuth2 Token Caching (`SentinelHubAuth`):** In-memory token reuse with a 60-second safety margin.
2. **Micro-SCL Inspection:** The AOI quality inspection uses an optimized $64 \times 64$ single-band query, consuming negligible Processing Units (~$0.001\text{ PU}$).
3. **Deterministic Instant Processing:** Full raster generation only queries the single best acquisition instant, preventing redundant mosaicking charges.
4. **Resolution Safety Cap (`1` to `4096` px):** Enforces safe memory and quota limits at the validation layer.
5. **Transient Retries:** Automatic exponential backoff on HTTP `429` (Rate Limit) and server errors.

---

## 8. Output Contract & Data Structure

### 1. Physical GeoTIFF Properties:
- **File Format:** GeoTIFF (`.tif`)
- **Bands:** 3 Bands — Band 1: `B04` (Red), Band 2: `B03` (Green), Band 3: `B02` (Blue)
- **Data Type (`dtype`):** `uint16` (scaled by $10,000$)
- **Embedded Metadata:** GeoTransform matrix, CRS (`EPSG:4326`).

### 2. Output JSON Schema:
```json
{
  "status": "success",
  "data": {
    "file_path": "c:/Users/User/Desktop/Tools/Tool_1_fetch_optical_imagery/test_runs/sample_optical_output.tif",
    "file_name": "sample_optical_output.tif",
    "format": "GeoTIFF"
  },
  "source": {
    "provider": "Sentinel Hub",
    "collection": "sentinel-2-l2a",
    "scene_id": "S2C_MSIL2A_20250128T053131_N0511_R105_T43RGM_20250128T084454",
    "acquisition_time": "2025-01-28T05:41:31Z"
  },
  "request": {
    "bbox": [77.1, 28.5, 77.3, 28.7],
    "start_date": "2025-01-01",
    "end_date": "2025-01-31",
    "modality": "optical",
    "bands": ["B04", "B03", "B02"],
    "max_cloud_cover": 30.0
  },
  "raster": {
    "width": 512,
    "height": 512,
    "band_count": 3,
    "dtype": "uint16",
    "crs": "EPSG:4326",
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
    "catalog_cloud_cover": 0.0,
    "aoi_cloud_cover": 0.0,
    "aoi_cloud_shadow": 0.0,
    "aoi_obstruction": 0.0,
    "aoi_snow_ice": 0.0,
    "valid": true
  },
  "flags": {
    "optical_quality_poor": false,
    "sar_recommended": false
  }
}
```

---

## 9. Quality Flags & Agent Decision Hooks

The downstream LangGraph agent evaluates the true AOI quality flags:
- `flags.optical_quality_poor`: Set to `true` if `aoi_obstruction > 50.0%`.
- `flags.sar_recommended`: Set to `true` when optical imagery is heavily obstructed over the AOI, triggering **Tool 3 (SAR)** radar fallback.

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
