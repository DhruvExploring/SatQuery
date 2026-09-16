# Tool 10: spatial_geocoding_poi (Spatial Geocoding & POI Discovery Engine)

## 1. Overview & Architectural Role

**`spatial_geocoding_poi`** is a high-precision geospatial ground truth and spatial intelligence engine built for Model Context Protocol (MCP) clients and LangGraph autonomous agents. It bridges the critical divide between raw GeoTIFF spatial bounding boxes ($[X_{\min}, Y_{\min}, X_{\max}, Y_{\max}]$) and human-readable regional identity, named places, and in-AOI landmarks.

By coupling authoritative commercial and open-source geocoders with OpenStreetMap's minutely synchronized vector database, Tool 10 enables SatQuery to ground any satellite observation in verified geographic reality without visual guessing or LLM hallucinations.

```text
                        ┌────────────────────────────────────────────────────────┐
                        │        TOOL 10: SPATIAL GEOCODING & POI ENGINE         │
                        └───────────────────────────┬────────────────────────────┘
                                                    │
             ┌──────────────────────────────────────┼──────────────────────────────────────┐
             ▼                                      ▼                                      ▼
┌─────────────────────────────┐        ┌─────────────────────────────┐        ┌─────────────────────────────┐
│ 1. Forward & Reverse        │        │ 2. Scene Identity           │        │ 3. In-AOI POI Discovery     │
│    Geocoding Engine         │        │    Resolver (BBox)          │        │    (Overpass QL Engine)     │
│                             │        │                             │        │                             │
│ • Place Name ──▶ Lat/Lon    │        │ • Computes Centroid         │        │ • Filters features strictly │
│ • Lat/Lon ──▶ Full Address  │        │ • Multi-Zoom Level Reverse  │        │   inside GeoTIFF bounds     │
│ • Viewbox Clamping Support  │        │   Lookup (zoom 8, 10, 14)   │        │ • Tourism, Heritage, Infra  │
└─────────────────────────────┘        └─────────────────────────────┘        └─────────────────────────────┘
```

---

## 2. Core Functional Capabilities

### 1. Forward Geocoding (Place Name $\to$ Geographic Coordinates)
- Resolves human place names (e.g. `"Red Fort"`, `"Indira Gandhi International Airport"`) to WGS84 coordinates $(\text{Lat}, \text{Lon})$ and bounding boxes.
- **Viewbox Clamping:** When an uploaded GeoTIFF bounding box is present, the search can be strictly bounded to prioritize candidate locations physically inside the scene footprint.

### 2. Reverse Geocoding (Coordinates $\to$ Structured Address)
- Resolves any point $(\text{Lat}, \text{Lon})$ to a clean structured hierarchy:
  - `road`, `neighbourhood`, `suburb`, `city`, `district`, `state`, `country`, and `postcode`.

### 3. Scene Identity Resolver (BBox $\to$ Regional Intelligence)
- Given a GeoTIFF bounding box $[Lon_{\min}, Lat_{\min}, Lon_{\max}, Lat_{\max}]$:
  1. Computes the geometric centroid:
     $$\text{Lat}_{\text{center}} = \frac{Lat_{\min} + Lat_{\max}}{2}, \quad \text{Lon}_{\text{center}} = \frac{Lon_{\min} + Lon_{\max}}{2}$$
  2. Executes hierarchical stepped reverse geocoding:
     - $\text{zoom}=8$: State / Regional territory (e.g. `Delhi NCR`).
     - $\text{zoom}=10$: Metropolitan / District administrative level (e.g. `Central Delhi`).
     - $\text{zoom}=14$: Locality / Suburb level (e.g. `Civil Lines / Yamuna River Corridor`).
  3. Synthesizes a factual, natural description:
     `"This scene covers Central Delhi and Civil Lines along the Yamuna River Corridor, Delhi, India."`

### 4. In-AOI POI Discovery (Overpass Spatial Engine)
- Extracts real-world Points of Interest (POIs) that physically lie within the raster bounds $(South, West, North, East)$.
- Supports targeted category filtering:
  - `tourism`: Attractions, museums, viewpoints, monuments, zoos, theme parks.
  - `historic`: Castles, forts, ruins, memorials, archaeological sites, heritage tags.
  - `amenity`: Hospitals, universities, places of worship, civic buildings.
  - `natural`: Water bodies, peaks, wetlands, beaches.
  - `infrastructure`: Airports, railway junctions, major bridges.
- Guaranteed Spatial Guardrail: Drops any feature whose coordinates fall outside the bounding box.

---

## 3. Provider Architecture & Resiliency Fallback

| Provider / Engine | Primary Role | Free Tier / Limits | API Key Required? | Currency / Freshness |
| :--- | :--- | :--- | :--- | :--- |
| **LocationIQ** *(Commercial OSM Proxy)* | Forward & Reverse Geocoding, Nearby POIs | **5,000 requests/day** (2 req/sec) | **Yes** (`LOCATIONIQ_API_KEY`) | Weekly updates from global OpenStreetMap database. |
| **OpenStreetMap Nominatim** | Open-Source Fallback (Forward / Reverse) | **1 req/sec** (Fair Use Policy) | **No** (Polite `User-Agent` header) | Real-time to weekly community updates. |
| **Overpass API** *(OSM QL Query Engine)* | In-AOI POI Discovery (BBox-clamped) | **Unlimited / Free** (~2 concurrent queries) | **No** (Public REST Endpoints) | Minutely replication feeds from OpenStreetMap. |

### Resiliency Chain:
1. **Geocoding:** LocationIQ (Primary) $\to$ OSM Nominatim (Secondary polite fallback).
2. **POI Discovery:** Overpass Primary Mirror $\to$ Overpass Secondary Mirror $\to$ LocationIQ Category Search (Tertiary fallback).

---

## 4. Input & Output Schema Specification

### Input Schema (`SpatialGeocodingRequest`):

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :---: | :---: | :--- |
| `mode` | `str` | No | `"auto"` | `"forward"`, `"reverse"`, `"scene_identity"`, `"poi_discovery"`, or `"auto"`. |
| `query` | `str` | Conditional | `None` | Place name or search query (required for `forward`). |
| `latitude` | `float` | Conditional | `None` | WGS84 Latitude $[-90.0, 90.0]$ (required for `reverse`). |
| `longitude` | `float` | Conditional | `None` | WGS84 Longitude $[-180.0, 180.0]$ (required for `reverse`). |
| `bbox` | `list[float]` | Conditional | `None` | `[min_lon, min_lat, max_lon, max_lat]` in WGS84. |
| `geotiff_path` | `str` | No | `None` | Local GeoTIFF file path to auto-extract spatial bounds. |
| `poi_categories` | `list[str]` | No | `None` | Categories: `["tourism", "historic", "amenity", "natural", "infrastructure"]`. |
| `max_results` | `int` | No | `15` | Maximum number of candidate results or POIs. |
| `zoom` | `int` | No | `None` | Reverse geocoding zoom level ($1 \dots 18$). |
| `viewbox_clamping` | `bool` | No | `True` | Binds forward search within the specified BBox. |

### Sample Output (`scene_identity`):
```json
{
  "status": "success",
  "bbox": [77.20, 28.62, 77.28, 28.68],
  "centroid": {
    "latitude": 28.65,
    "longitude": 77.24
  },
  "geographic_identity": "Chandni Chowk, Central Delhi, Delhi, India",
  "narrative_summary": "This satellite raster covers Chandni Chowk, Central Delhi, Delhi, India centered at coordinates (28.65°N, 77.24°E).",
  "hierarchy": {
    "locality": "Chandni Chowk",
    "city": "Central Delhi",
    "state": "Delhi",
    "country": "India"
  }
}
```

---

## 5. Research & Literature Foundation

The spatial data structures and geocoding methodologies implemented in Tool 10 are grounded in authoritative geospatial literature:

1. **OpenStreetMap Foundation (OSMF)**, *OpenStreetMap Data Model & Tagging Ontology*:
   Defines the primitive spatial node, way, and relation hierarchies utilized by the Overpass QL parser.
2. **Haklay, M. & Weber, P. (2008)**, *"OpenStreetMap: User-Generated Street Maps"*, *IEEE Pervasive Computing*, Vol. 7, No. 4, pp. 12–18.
   Establishes the topological accuracy and completeness benchmarks for crowd-sourced OpenStreetMap features versus proprietary basemaps.
3. **Goodchild, M. F. (2007)**, *"Citizens as sensors: the world of volunteered geographic information"*, *GeoJournal*, Vol. 69, No. 4, pp. 211–221.
   Validates the currency and real-time reliability of VGI (Volunteered Geographic Information) in disaster response and infrastructure identification.
