# SatQuery Tool Catalog

Every tool the orchestrator's LLM planner can select (`backend/orchestrator/registry.py::TOOL_REGISTRY`), what each one actually computes under the hood, and five worked multi-hop query examples that together exercise all of them.

See [README.md](README.md) for the planner's JSON I/O schema (`Plan`, `ToolResult`, `SatQueryState`). This file documents the *tools themselves*, not the planner protocol.

The LLM never supplies real arguments — it only picks a `tool` name. `trusted_args_for_tool()` in `registry.py` rebuilds the actual call arguments from graph state and prior tool outputs. Implementation code for numbered tools lives in `Tool_1_…` … `Tool_11_…` directories at the repo root; `backend/tools/executor.py` dispatches by name.

---

## 0. Tools that run automatically (not planner-selected)

Two things happen before the LLM planner is ever consulted:

**A. Upload time** (`backend/orchestrator/ingest_graph.py`, runs once per uploaded file):
1. `inspect_geotiff_metadata` — validates the file is a real GeoTIFF and extracts its bands/CRS/bounds.
2. `get_place_name_from coordinates` (reverse geocode) — resolves the raster's centroid to a place name.
3. Both results are cached into a per-image `knowledge_base` (`<file>.kb.json`): `{file_path, bands, latitude, longitude, bbox, pixel_size_wgs84_degrees, place_name}`.

**B. Per query, before the tool-loop** (`backend/orchestrator/graph.py`: `validate → load_knowledge_base → vlm_initial_description → describe_region_auto → tool_loop → respond`):
1. `vlm_initial_description` — if an image is attached, calls `analyze_imagery_vlm` once automatically, grounding the prompt in the upload-time `knowledge_base` JSON, before any planner hop.
2. `describe_region_auto` — if `region_bbox` is present (the user drew/marked a sub-region), calls `describe_marked_region` automatically, exactly once, regardless of what the planner would have chosen.

Both results are appended to `tool_results`, so the planner's *first* consultation already sees them as "already gathered evidence" and is told (via the system prompt) not to repeat them.

---

## 1. Fetch tools (Sentinel-1/2 imagery + weather)

### `fetch_optical_imagery`
**Purpose:** Sentinel-2 true-color (B04/B03/B02) GeoTIFF for a bbox + date range.
**Math:**
- Two-stage scene selection: (1) catalog pre-sort by `(cloud_cover ↑, acquisition_time ↓)`; (2) for the top 5 candidates, sample a 64×64 Scene Classification Layer (SCL) grid over the AOI and compute
  `aoi_cloud% = cloud_px/total_px`, `aoi_shadow% = shadow_px/total_px`, `aoi_obstruction = aoi_cloud% + aoi_shadow%`, then pick `min(candidates, key=(aoi_obstruction, catalog_cloud_cover, -acquisition_epoch))`.
- Fetch via Sentinel Hub Processing API, `mosaickingOrder: "leastCC"`, bands scaled ×10000, UINT16.
- Quality flag: `optical_quality_poor = aoi_obstruction > 50.0` → sets `sar_recommended` (the planner is told to fall back to `fetch_sar_imagery` when this fires).
**Requires:** `bbox`, `start_date`, `end_date`. **Defaults:** `max_cloud_cover=30.0`, `width=height=512`, `crs=EPSG:4326`, dates default to `2025-01-01`–`2025-01-31`.

### `fetch_multispectral_imagery`
**Purpose:** Same fetch/scoring pipeline as above, but a wider analytical band set (default `B02,B03,B04,B05,B07,B08,B11,B12`) at FLOAT32 surface reflectance (not ×10000 scaled) — the input `compute_vegetation_indices` and the mission workflows expect.
**Math:** Identical scene-selection/AOI-obstruction math to `fetch_optical_imagery`.
**Requires:** `bbox`, `start_date`, `end_date`.

### `fetch_sar_imagery`
**Purpose:** Sentinel-1 SAR/radar backscatter GeoTIFF (works through cloud cover — used for flood/all-weather change detection).
**Math:**
- dB conversion per polarization: `10 * log10(max(sample, 1e-5))`; `backCoeff: GAMMA0_TERRAIN`, `orthorectify: true`.
- Scene filter: IW mode, requested polarizations must be a subset of the scene's, exact orbit match (`ASCENDING`/`DESCENDING`/`BOTH`, no substitution).
- Scene pick: `most_recent` (default) = `max(key=acquisition_time)`; `closest_to_start_date`/`closest_to_end_date` = `min(key=|acquisition_time − target|)`.
- Radar geometry QA via a 64×64 sample of `shadowMask`/`localIncidenceAngle`: `shadow_frac = shadow_px/total_px`; `radar_geometry_poor = shadow_frac > 0.08 OR mean_incidence_angle < 15° OR > 65°`.
**Requires:** `bbox`, `start_date`, `end_date`. **Defaults:** `polarization=[VV,VH]`, `orbit_direction=BOTH`.

### `fetch_weather_environment`
**Purpose:** Historical (ERA5/ERA5-Land via Open-Meteo archive), current, or short-range forecast (≤~16 days) weather — auto-selected by date.
**Math:**
- `ARCHIVE_LATENCY_DAYS = 5`; days ≤ `today − 5d` come from the archive API, the rest from the forecast API; series concatenated chronologically.
- Spatial sampling: bbox ≤ 0.5° in both dimensions → single centroid point; larger bbox → 5-point sample (centroid + 4 quartile-offset corners: `min + 0.25·span`, `max − 0.25·span`), averaged with `nanmean`.
- Derived metrics: `water_balance_mm = precip_total − ET0_total`; `heavy_rainfall = max_daily_precip ≥ 25mm OR total ≥ 100mm`; `heat_stress = any(Tmax ≥ 35°C) OR mean_T ≥ 32°C`; `cold_stress = any(Tmin ≤ 4°C)`; `deficit_intensity = "none" if balance≥0 else "moderate" if balance≥−50 else "severe"`.
- Rolling windows (default `[7, 30]` days): sum/mean over the trailing N days.
**Requires:** `bbox` OR `latitude`+`longitude`. **Default:** no dates given → last 7 days through today.

---

## 2. Analytical tools (operate on a GeoTIFF already on disk)

### `compute_vegetation_indices`
**Purpose:** Compute up to 10 spectral indices from a multispectral GeoTIFF.
**Math** (`safe_norm_diff(a,b) = (a−b)/(a+b)` where denominator ≠ 0):

| Index | Formula | Bands |
|---|---|---|
| NDVI | `(NIR−Red)/(NIR+Red)` | B08, B04 |
| EVI | `2.5·(NIR−Red)/(NIR+6·Red−7.5·Blue+1)` | B08,B04,B02 |
| SAVI | `1.5·(NIR−Red)/(NIR+Red+0.5)` | B08, B04 |
| GNDVI | `(NIR−Green)/(NIR+Green)` | B08, B03 |
| NDRE_B5 | `(NIR−B05)/(NIR+B05)` | B08, B05 |
| NDRE_B7 | `(NIR−B07)/(NIR+B07)` | B08, B07 |
| NDMI | `(NIR−SWIR1)/(NIR+SWIR1)` | B08, B11 |
| NDWI | `(Green−NIR)/(Green+NIR)` | B03, B08 |
| MSAVI | `(2·NIR+1 − sqrt(max((2·NIR+1)²−8·(NIR−Red), 0)))/2` | B08, B04 |
| NBR | `(NIR−SWIR2)/(NIR+SWIR2)` | B08, B12 |

- Auto-normalizes raw Sentinel-2 integer reflectance (`max valid > 2.0` → divide by 10000).
- Heuristic NDVI classification: `dense >0.6`, `moderate 0.3–0.6`, `sparse 0.1–0.3`, `non_veg/water <0.1`.
- Pixel-area math (geographic CRS) uses the shared WGS84 degrees→meters polynomial (see §5).
**Requires:** `input_file`. **Default indices:** all 10 above.

### `inspect_geotiff_metadata`
**Purpose:** Deep QA of a GeoTIFF — CRS, bounds, band stats, ML-readiness, optional grid-compatibility check against another raster.
**Math:**
- Same WGS84 deg→m polynomial for `approx_area_km2`.
- Per-pixel WGS84 resolution/corners via linear interpolation across the bbox (exact for north-up rasters; documented as an approximation for skewed ones — Tool 11's affine math is the exact single-point alternative).
- `np.histogram(valid, bins=10)` per band; percentiles p01/p05/p25/p50/p75/p95/p99.
- Grid-alignment check (`compare_with`): `same_crs`, `same_dims`, `same_res` (`np.allclose(rtol=1e-5, atol=1e-8)`), `same_bounds`, `same_transform` → `pixelwise_ready = all(...)`.
- ML-readiness: `is_georef = crs is not None and transform != identity`; `is_num_usable = no empty bands, no inf, valid_fraction > 0.5`; `is_valid_for_ml = both`.
**Requires:** `input_file`.

### `analyze_temporal_change`
**Purpose:** Pixel-wise diff between two grid-aligned rasters (same CRS/dims/transform) → difference raster + classified change mask.
**Math:**
- `delta = T2 − T1` on valid pixels.
- Threshold modes: `absolute` → `threshold_loss = −|v|, threshold_gain = +|v|`; `statistical` → `threshold_loss = mean(delta) − k·std(delta)`, `threshold_gain = mean(delta) + k·std(delta)` (k = `threshold_value`).
- Optional relative shift (skipped for SAR/dB rasters): `((T2−T1)/|T1|)·100` where `|T1| > 1e-4`.
- `bipolar_3class` mask: `-1` loss / `0` stable / `1` gain / `-128` NoData. `severity_5class`: `-2` major loss … `2` major gain, using `2×` the base threshold as the "major" cutoff.
- Backend auto-picks `threshold_value = 3.0` (dB) if either raster path looks like a SAR product, else `0.15` (bounded index).
**Requires:** `raster_before_path`, `raster_after_path` (must already be grid-aligned — use `compare_images_visually` instead if they might not be).

### `analyze_spatial_landcover_terrain`
**Purpose:** LULC composition + fragmentation + DEM slope + zonal cross-tab against a change mask.
**Math:**
- Slope: `dz_dy, dz_dx = np.gradient(dem, dy_m, dx_m)`; `slope_deg = degrees(arctan(sqrt(dz_dx²+dz_dy²)))`. Classes: `<5° flat_to_gentle`, `5–15° moderate`, `15–30° steep`, `≥30° very_steep`.
- Fragmentation (8-connectivity, `scipy.ndimage.label`, structure=3×3 ones): `mean_patch_km2 = total_class_px · pixel_area_km2 / num_patches`; `LPI% = max(patch_sizes)/total_class_px × 100`. Heuristic: `LPI>75% → Continuous/Low Fragmentation`, `>35% → Moderately Fragmented`, else `Highly Fragmented/Dispersed`. Applied to tree/shrub/grass/crop/wetland/mangrove classes (ESA WorldCover codes 10,20,30,40,90,95).
- Default ESA WorldCover legend: `10 Tree cover, 20 Shrubland, 30 Grassland, 40 Cropland, 50 Built-up, 60 Bare/sparse veg, 70 Snow/ice, 80 Permanent water, 90 Herbaceous wetland, 95 Mangroves, 100 Moss/lichen`.
- Zonal stats: reprojects/aligns a zone mask (e.g. Tool 7's `_change_mask.tif`) onto the LULC grid (nearest-neighbor for categorical, bilinear for DEM), then per-zone area/LULC-% and (if DEM given) mean/min/max elevation + mean slope.
**Requires:** `lulc_raster_path` (optionally `dem_raster_path`, `zone_mask_path`).

---

## 3. Mission workflows (composite pipelines over Tools 1–8, `satquery_workflows.py`)

### `workflow_wildfire_burn_severity`
**Purpose:** Pre/post-fire burn severity + slope risk + forest-loss accounting.
**Pipeline:** `compute_vegetation_indices` (NBR, pre & post) → `inspect_geotiff_metadata` QA → `analyze_temporal_change` (`threshold_type=absolute, threshold_value=0.10, mask_encoding=severity_5class`, i.e. dNBR = NBR_pre − NBR_post) → `analyze_spatial_landcover_terrain` zonal cross-tab.
**Legend:** `-2 High Severity Burn, -1 Moderate-Low Severity Burn, 0 Unburned/Stable, 1 Post-Fire Regrowth, 2 Rapid Emergence`.
**Summary math:** `total_burned_km2 = high_burn_area_km2 + moderate_burn_area_km2`.
**Requires:** `raster_before_path`, `raster_after_path` (multispectral pre/post), `lulc_raster_path`.

### `workflow_flood_inundation_impact`
**Purpose:** SAR-based flood inundation extent + LULC impact + rainfall context.
**Pipeline:** `inspect_geotiff_metadata` QA → `analyze_temporal_change` on the SAR VV dB band (`threshold_type=absolute, threshold_value=3.0`, i.e. a ≥3 dB backscatter drop = new water) → `fetch_weather_environment` (automatic, if bbox/lat-long available) → `analyze_spatial_landcover_terrain` zonal overlay.
**Legend:** `-1 New Water Inundation/Flood Footprint, 0 Unflooded/Stable, 1 Water Recession/Drydown`.
**Requires:** `raster_before_path`, `raster_after_path` (SAR pre/post), `lulc_raster_path`.

### `workflow_agricultural_drought_canopy_stress`
**Purpose:** Correlates canopy vegetation stress with soil-moisture/rainfall deficit.
**Pipeline:** `compute_vegetation_indices` (NDVI, NDMI, EVI) → `fetch_weather_environment` (soil moisture + ET0) → rule-based classification:
```
if mean_NDMI < 0.0 and soil_moisture < 0.18 and water_balance < -20.0:
    "High Crop Water Stress & Emerging Agricultural Drought"
elif mean_NDMI < 0.10 or water_balance < 0.0:
    "Moderate Soil Moisture Deficit"
else:
    "Optimal Hydrological Conditions"
```
**Requires:** `input_file` (multispectral) + `bbox`/`latitude`+`longitude` for weather.

---

## 4. Vision (VLM) tools

### `analyze_imagery_vlm`
**Purpose:** Free-form natural-language description/interpretation of a rendered image (GeoTIFFs are rendered to PNG first via a 2nd–98th percentile per-channel stretch).
**Math:** No numeric formula — delegates to a vision-language model (OpenAI vision model, or local InternVL-1B/EarthMind-4B sidecar). The OpenAI provider uses `with_structured_output` and only emits a `bbox` (fraction 0–1, top-left origin) when the query wording asks to locate/mark something.
**Requires:** `image_path` (accepts a rendered image or a GeoTIFF, which gets auto-rendered).

### `mark_region_in_image`
**Purpose:** Same underlying call as `analyze_imagery_vlm` (literally the same executor function) — a distinct planner-facing name for "locate/mark/circle X" requests, so the model returns an approximate fractional bounding box for where a described feature is.
**Math:** If the model returns a `bbox`, the backend converts it to an exact WGS84 `region_bbox` via `fractional_bbox_to_wgs84` (Tool 11): projects all 4 pixel corners (`x_frac·width, y_frac·height`) through the GeoTIFF's forward affine transform and reprojects to EPSG:4326, taking min/max — correct even for rotated/skewed rasters, not a linear approximation.
**Requires:** `image_path`.

### `compare_images_visually`
**Purpose:** Qualitative two-image comparison via the VLM — unlike `analyze_temporal_change`, never requires grid alignment, so it works across different sensors, resolutions, dates, or even different places (and will say so).
**Math:** None — pure vision-model text comparison; system prompt explicitly warns the model not to assume the two images show the same location.
**Requires:** `image_path_a`, `image_path_b`. Preferred over `analyze_temporal_change` whenever the two rasters might be misaligned, or after that tool has already failed on alignment.

### `describe_marked_region`
**Purpose:** Ground truth for a user-drawn/marked sub-region — crops the *source GeoTIFF's own pixels* to the exact `region_bbox` and runs the VLM only on that crop, plus reverse-geocodes the region's center.
**Math:** `region_bbox → native CRS (transform_bounds if needed) → rasterio.windows.from_bounds(...) → clamp/intersect with the full raster window → read only that window → re-transform the achieved window back to WGS84`. Also computes the geometric center `((min_lat+max_lat)/2, (min_lon+max_lon)/2)` and reverse-geocodes it for an authoritative `place_name` (overriding any place name the VLM's own text guesses).
**Requires:** `input_file`, `region_bbox`. Runs automatically once per request when `region_bbox` is set — the planner is instructed never to call it itself.

---

## 5. Geocoding / real-world-grounding tools

### `get_place_name_from_coordinates`
**Purpose:** Reverse geocode — lat/long → human place name. **Math:** LocationIQ (primary) → OSM Nominatim (fallback, rate-limited to 1 req/sec). No scoring math; passes through the provider's own resolved `display_name`. **Requires:** `latitude`, `longitude`.

### `geocode_place_to_coordinates`
**Purpose:** Forward geocode — a place/landmark name → WGS84 coordinates + bbox. **Math:** LocationIQ with `viewbox`+`bounded=1` clamping when a bbox is supplied, falling back to unbounded/Nominatim on failure; `_is_valid_landmark_candidate` filters low-importance commercial noise (`importance < 0.55` in classes `{amenity, shop, office, commercial, craft, leisure}`) unless it's a heritage type or the query explicitly wants a commercial place. **Requires:** `query` (the place name).

### `resolve_scene_identity`
**Purpose:** What region/locality/city a bbox covers, and whether any landmark named in the query actually falls inside it.
**Math:**
- Centroid = `((min_lat+max_lat)/2, (min_lon+max_lon)/2)`; hierarchical reverse geocode at zoom 8 (state), 10 (district/city), 14 (suburb).
- Containment: `min_lon ≤ lon ≤ max_lon AND min_lat ≤ lat ≤ max_lat`.
- Haversine distance: `a = sin²(Δlat/2) + cos(lat1)·cos(lat2)·sin²(Δlon/2)`; `distance_km = 6371.0 · 2·atan2(√a, √(1−a))`.
- Cardinal direction: `|Δlat|>0.05°` → N/S, `|Δlon|>0.05°` → E/W, combined for intercardinal (e.g. "North-East").
**Requires:** `bbox`.

### `discover_points_of_interest`
**Purpose:** Real-world POIs (tourism, historic, amenity, natural, infrastructure) strictly inside a bbox.
**Math:** Overpass QL bbox filter `(south,west,north,east) = (min_lat,min_lon,max_lat,max_lon)` against 3 mirror endpoints, with a fallback chain to LocationIQ `nearby.php` then Nominatim category search; results are re-checked for strict bbox containment even though Overpass already filters.
**Requires:** `bbox`.

### `deterministic_affine_markup`
**Purpose:** Exact pixel location of one or more known lat/long features on a GeoTIFF (zero VLM guessing), with badge markers drawn on the rendered preview.
**Math (inverse affine, Snyder 1987 / OGC 19-008r4):**
```
forward:  X = a·C + b·R + c ;  Y = d·C + e·R + f      (a..f = rasterio's native affine transform)
det = a·e − b·d
C = ((X−c)·e − (Y−f)·b) / det
R = ((Y−f)·a − (X−c)·d) / det
```
Raises on a degenerate matrix (`|det| < 1e-12`). WGS84 lat/long is reprojected to the raster's native CRS first (`pyproj`, skipped if already EPSG:4326). Marker placement uses an adaptive radius `max(7, min(18, 0.04·min(width,height)))` and picks the lowest-overlap-score candidate position to avoid badge collisions.
**Requires:** `geotiff_path`, `features` (each with `name`, `latitude`, `longitude` — typically fed by a prior `geocode_place_to_coordinates`/`resolve_scene_identity` call).

### `fetch_web_intelligence`
**Purpose:** Ground-truth real-world context a pixel can't contain — event causes, disaster reports, infrastructure project names, background on a place.
**Math:** No relevance scoring — Tavily's own `score` field (if used) is passed through verbatim. Primary: Tavily (`include_answer=True`); automatic fallback to DuckDuckGo on any error/missing key. A hardcoded guardrail blocks queries about the system's own internals (`"python"`, `"affine transform"`, `"numpy"`, `"rasterio"`, etc. as substrings). Summary falls back to the top-2 result snippets if Tavily returns no synthesized answer.
**Requires:** `query`.

---

## Shared math used across multiple tools

**WGS84 degrees→meters** (Tools 5, 6, 7, 8 — pixel-area / ground-sample-distance conversions on geographic-CRS rasters), a standard geodesic polynomial evaluated at the bbox's midpoint latitude (radians):
```
deg_to_m_lat = 111132.954 − 559.822·cos(2·lat) + 1.175·cos(4·lat)
deg_to_m_lon = 111412.84·cos(lat) − 93.5·cos(3·lat)
pixel_area_km2 = (res_x · deg_to_m_lon) · (res_y · deg_to_m_lat) / 1e6
```

---

# Five worked examples

Each example is a realistic multi-hop request: an image/context setup, the user's natural-language query, and the actual sequence of tool calls the orchestrator would make (auto nodes marked 🔒, planner-chosen hops numbered). Together the five cover every tool in the registry.

## Example 1 — Wildfire assessment with news context
**Setup:** User uploads a pre-fire multispectral GeoTIFF of a forested hillside (`before.tif`), then a second, post-fire multispectral GeoTIFF of the same area (`after.tif`).
**Query:** *"Assess the wildfire burn severity between these two images, tell me what land cover was affected and whether any nearby town was at risk, and find out what caused the fire."*

| Step | Tool | Why |
|---|---|---|
| 🔒 upload | `inspect_geotiff_metadata` ×2 + reverse `get_place_name_from_coordinates` | Ingest-time validation + knowledge base for each upload |
| 🔒 | `analyze_imagery_vlm` | Automatic first-pass description of `after.tif` |
| 1 | `workflow_wildfire_burn_severity` | Runs NBR (`compute_vegetation_indices`) pre/post → `analyze_temporal_change` (dNBR, severity_5class) → `analyze_spatial_landcover_terrain` zonal cross-tab internally |
| 2 | `discover_points_of_interest` | "nearby town at risk" — POIs inside the burn AOI bbox |
| 3 | `fetch_web_intelligence` | "what caused the fire" — real-world ground truth the pixels can't contain |

## Example 2 — Flood inundation over SAR with scene identity
**Setup:** No upload; the user names a place and date range.
**Query:** *"How much of Guwahati flooded between July 1 and July 15, and what area does that actually cover?"*

| Step | Tool | Why |
|---|---|---|
| 1 | `geocode_place_to_coordinates` | Resolve "Guwahati" → bbox |
| 2 | `fetch_sar_imagery` (pre) + `fetch_sar_imagery` (post) | SAR penetrates monsoon cloud cover; two date windows |
| 3 | `workflow_flood_inundation_impact` | SAR dB drop (≥3.0 dB) → flood mask → automatic `fetch_weather_environment` for rainfall context → LULC zonal overlay |
| 4 | `resolve_scene_identity` | Confirms/narrates which district/locality the AOI bbox actually falls in |

## Example 3 — Vegetation health, drought, and precise landmark marking
**Setup:** User uploads one multispectral GeoTIFF of farmland (`farm.tif`) covering a known reservoir.
**Query:** *"Compute vegetation indices for this field, tell me if it's under drought stress, and mark exactly where Sukhna Reservoir is on the image."*

| Step | Tool | Why |
|---|---|---|
| 🔒 upload | `inspect_geotiff_metadata` + reverse geocode | Ingest knowledge base |
| 🔒 | `analyze_imagery_vlm` | Automatic initial description |
| 1 | `compute_vegetation_indices` | NDVI/EVI/SAVI/… + heuristic classification |
| 2 | `workflow_agricultural_drought_canopy_stress` | NDMI/NDVI/EVI + ERA5 soil moisture/ET0 → rule-based stress ladder |
| 3 | `geocode_place_to_coordinates` | "Sukhna Reservoir" name → exact lat/long |
| 4 | `deterministic_affine_markup` | Projects that exact coordinate through the GeoTIFF's own affine transform → pixel-precise badge marker |

## Example 4 — Urban change near a landmark, with alignment fallback
**Setup:** No upload; two dates over the same named area.
**Query:** *"What's changed near the Red Fort between January and June this year, and what else is around there?"*

| Step | Tool | Why |
|---|---|---|
| 1 | `geocode_place_to_coordinates` | "Red Fort" → coordinates/bbox |
| 2 | `fetch_optical_imagery` (Jan) + `fetch_optical_imagery` (Jun) | Two RGB snapshots for the same AOI |
| 3 | `analyze_temporal_change` | Pixel-wise diff — used first since both come from the same fetch pipeline (grid-aligned) |
| 3b (fallback) | `compare_images_visually` | Only if step 3 refuses due to misalignment (different scenes/orbits) |
| 4 | `resolve_scene_identity` | Confirms Red Fort actually falls inside the fetched AOI |
| 5 | `discover_points_of_interest` | "what else is around there" |
| 6 | `analyze_spatial_landcover_terrain` | Land-cover context for the changed area (needs a LULC raster already on hand) |

## Example 5 — Interactive marked-region Q&A on an uploaded image
**Setup:** User uploads a single optical GeoTIFF of a coastal town (`coast.tif`), then draws/circles a rectangle over part of it in the UI (`region_bbox` set).
**Query (turn 1):** *"What does this image show, and mark the flooded-looking area."*
**Query (turn 2, after the user's drawn box arrives):** *"What's in the region I just selected, and what's the weather like there right now?"*

| Step | Tool | Why |
|---|---|---|
| 🔒 upload | `inspect_geotiff_metadata` + reverse `get_place_name_from_coordinates` | Ingest knowledge base |
| 🔒 turn 1 | `analyze_imagery_vlm` | Automatic whole-image description |
| 1 | `mark_region_in_image` | "mark the flooded-looking area" → fractional bbox → converted to exact `region_bbox` via `fractional_bbox_to_wgs84` |
| 🔒 turn 2 | `describe_marked_region` | Fires automatically because `region_bbox` is now set — crops the raster to that exact box, reverse-geocodes its center |
| 2 | `fetch_weather_environment` | "weather... there right now" — uses the marked region's center point (not the whole image's bbox), auto-selects current/forecast source since no dates were given |
