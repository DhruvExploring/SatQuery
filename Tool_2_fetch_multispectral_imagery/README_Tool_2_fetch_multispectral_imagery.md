# Tool 2: fetch_multispectral_imagery (Sentinel-2 L2A Surface Reflectance)

## 1. Overview & Purpose

**`fetch_multispectral_imagery`** is a dedicated scientific Earth Observation (EO) data ingestion tool built for Model Context Protocol (MCP) clients and LangGraph autonomous agents. Its primary responsibility is to discover, retrieve, validate, and package **multi-channel Bottom-Of-Atmosphere (BOA) Surface Reflectance satellite imagery** across arbitrary spectral bands (e.g. Coastal, Blue, Green, Red, Red Edge, NIR, Narrow NIR, Water Vapour, SWIR, and auxiliary scene classification layers) from the **ESA Sentinel-2 constellation**.

### Key Distinction: AOI-Level Quality Validation
Unlike naive satellite query tools that only rely on global catalog cloud metadata (which covers an entire $100\text{ km} \times 100\text{ km}$ tile), this tool includes an **AOI-level Scene Classification Layer (SCL) Quality Validation stage**. It inspects cloud and shadow contamination specifically inside the user's requested AOI, ensuring that the selected scene is truly unobstructed over the area of interest before retrieving full multi-spectral data.

---

## 2. Satellite & Provider Specifications

- **Data Provider:** [Sentinel Hub](https://www.sentinel-hub.com/) / [Copernicus Data Space Ecosystem (CDSE)](https://dataspace.copernicus.eu/)
- **Provider Console / Dashboard:** [Sentinel Hub Dashboard](https://apps.sentinel-hub.com/dashboard/)
- **Satellite Constellation:** Sentinel-2 (Sentinel-2A, Sentinel-2B, Sentinel-2C)
- **Product Collection:** `sentinel-2-l2a` (Level-2A Surface Reflectance)
- **Quality Validation Layer:** Sentinel-2 `SCL` (Scene Classification Layer, 20m)
- **Native Resolutions:**
  - 10 meters: `B02` (Blue), `B03` (Green), `B04` (Red), `B08` (NIR)
  - 20 meters: `B05`, `B06`, `B07` (Red Edge), `B8A` (Narrow NIR), `B11`, `B12` (SWIR), `SCL` (Scene Classification)
  - 60 meters: `B01` (Coastal Aerosol), `B09` (Water Vapour)
- **Radiometric Output:** $N$-Band GeoTIFF (`FLOAT32`, physical surface reflectance $[0.0, 1.0]$)

### Remote APIs Used:
1. **OAuth2 OpenID Connect Authentication:**
   `https://services.sentinel-hub.com/auth/realms/main/protocol/openid-connect/token`
2. **STAC Catalog Search API v1.0:**
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
| `rasterio` | Multichannel GeoTIFF verification, CRS, affine resolution, and band-channel inspection |
| `numpy` | High-speed pixel array histogram calculations for SCL AOI quality scoring |
| `pydantic` | Strict spectral band validation, date checking, and spatial coordinate boundary enforcement |
| `fastmcp` | Standardized Model Context Protocol (MCP) server integration |

---

## 4. End-to-End Architectural Flow Diagram

```mermaid
flowchart TD
    A[Agent / LangGraph Client] -->|Invokes fetch_multispectral_imagery| B[MultispectralSatelliteRequest Validation]
    
    B -->|Validate Bands, BBox, Dates| C{Is Input Valid?}
    C -- No --> E1[Return Structured validation_error JSON]
    
    C -- Yes --> D[SentinelHubAuth: Token Manager]
    D -->|Check Memory Cache| D1{Valid Token Cached?}
    D1 -- Yes --> F[SentinelHubHTTPClient]
    D1 -- No --> D2[POST OAuth /token & Cache with 60s Buffer]
    D2 --> F
    
    F --> G[Search STAC Catalog: collections=['sentinel-2-l2a']]
    G --> H[Retrieve Candidate STAC Observations]
    H --> I[Normalize Scene Metadata & Cloud Coverage]
    
    I --> J{Candidate Observations Found?}
    J -- No --> E2[Return Structured no_suitable_scene JSON]
    
    J -- Yes --> K[AOI-Level SCL Quality Stage]
    K --> K1[Evaluate Top 5 Candidates via SCL Layer over exact AOI]
    K1 --> K2[Compute aoi_cloud_cover, aoi_cloud_shadow, aoi_obstruction]
    
    K2 --> L[Deterministic Selection: Lowest aoi_obstruction + Lowest global cloud]
    L --> M[Generate Dynamic Multispectral Evalscript for requested bands]
    M --> N[Execute Processing API with Exact Acquisition Instant]
    
    N --> O[Stream Multi-Band GeoTIFF FLOAT32 Bytes to Disk]
    O --> P[Rasterio Inspection: Validate Dimensions, Bands Count, CRS, Bounds]
    
    P --> Q{Is GeoTIFF Valid & Non-Empty?}
    Q -- No --> E3[Return Structured service_error JSON]
    
    P -- Yes --> R[Build Band Mapping: Band_1 -> B02, Band_2 -> B03...]
    R --> S[Return Success Envelope: Raster Path + AOI Quality + Band Mapping JSON]
    S --> T[Tool 5 / Tool 7 / Downstream ML Models]
```

---

## 5. AOI-Level SCL Quality Inspection Logic

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
| `bands` | `list[str]` | No | `["B02", "B03", "B04", "B08"]` | Any subset of valid Sentinel-2 L2A bands. | Case-insensitive list of requested spectral bands. |
| `max_cloud_cover`| `float` | No | `30.0` | `0.0` to `100.0` | Maximum catalog cloud-cover percentage threshold. |
| `width` | `int` | No | `512` | `1` to `4096` | Output GeoTIFF raster pixel width. |
| `height` | `int` | No | `512` | `1` to `4096` | Output GeoTIFF raster pixel height. |
| `crs` | `str` | No | `"EPSG:4326"` | `"EPSG:4326"` | Coordinate reference system for spatial bounds. |

---

## 7. Supported Sentinel-2 L2A Bands Reference

| Band Code | Spectral Region | Central Wavelength ($\text{nm}$) | Native Resolution | Primary Applications |
| :--- | :--- | :---: | :---: | :--- |
| **`B01`** | Coastal Aerosol | 443 | 60 m | Coastal bathymetry, aerosol detection |
| **`B02`** | Blue | 490 | 10 m | Soil/vegetation differentiation, true color |
| **`B03`** | Green | 560 | 10 m | Green peak reflectance, water mapping (NDWI) |
| **`B04`** | Red | 665 | 10 m | Chlorophyll absorption, vegetation health (NDVI) |
| **`B05`** | Vegetation Red Edge 1 | 705 | 20 m | Chlorophyll content, leaf structure |
| **`B06`** | Vegetation Red Edge 2 | 740 | 20 m | Crop phenology, canopy status |
| **`B07`** | Vegetation Red Edge 3 | 783 | 20 m | Biomass estimation, stress detection (NDRE) |
| **`B08`** | Broad NIR | 842 | 10 m | High-resolution vegetation biomass & water body mapping |
| **`B8A`** | Narrow NIR | 865 | 20 m | Atmospheric water vapour absorption reference |
| **`B09`** | Water Vapour | 945 | 60 m | Atmospheric moisture correction |
| **`B11`** | SWIR-1 | 1610 | 20 m | Soil moisture, snow/ice separation, MNDWI, fire scars |
| **`B12`** | SWIR-2 | 2190 | 20 m | Geological mapping, burn severity (NBR), canopy water |
| **`SCL`** | Scene Classification | — | 20 m | Cloud, shadow, water, bare soil, vegetation mask |
| **`AOT`** | Aerosol Optical Thickness| — | 10 m | Atmospheric aerosol quantification |

---

## 8. Output Contract & Data Structure

### 1. Physical GeoTIFF Properties:
- **File Format:** GeoTIFF (`.tif`)
- **Band Count:** Equal to `len(bands)` requested.
- **Data Type (`dtype`):** `float32` (calibrated physical reflectance $[0.0, 1.0]$).
- **Embedded Metadata:** CRS (`EPSG:4326`), Affine transform, spatial bounding box.

### 2. Output JSON Schema:
```json
{
  "status": "success",
  "data": {
    "file_path": "c:/Users/User/Desktop/Tools/Tool_2_fetch_multispectral_imagery/test_runs/sample_multispectral_output.tif",
    "file_name": "sample_multispectral_output.tif",
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
    "modality": "multispectral",
    "bands": ["B02", "B03", "B04", "B08", "B11", "B12"],
    "max_cloud_cover": 30.0
  },
  "raster": {
    "width": 512,
    "height": 512,
    "band_count": 6,
    "dtype": "float32",
    "crs": "EPSG:4326",
    "band_mapping": {
      "Band_1": "B02",
      "Band_2": "B03",
      "Band_3": "B04",
      "Band_4": "B08",
      "Band_5": "B11",
      "Band_6": "B12"
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

## 9. Downstream AI & Tool Integration Hooks

- **Tool 5 (Vegetation Indices):** Consumes the output file and uses `band_mapping` to extract `B04` (Red), `B08` (NIR), `B03` (Green), `B05-B07` (Red Edge), and `B11` (SWIR) for computing NDVI, EVI, SAVI, NDRE, and NDWI.
- **Tool 7 (Geo Analysis Engine):** Uses multi-temporal surface reflectance pairs to detect land degradation, water expansion, and agricultural changes.
- **LangGraph Fallback Hook:** When `flags.optical_quality_poor` is `true` (due to `aoi_obstruction > 50.0%`), LangGraph triggers **Tool 3 (SAR)** for cloud-penetrating radar observation.

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
