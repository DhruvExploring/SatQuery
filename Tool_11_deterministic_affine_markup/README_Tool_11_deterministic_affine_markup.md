# Tool 11: deterministic_affine_markup (Deterministic Affine Projector & Markup Engine)

## 1. Overview & Mathematical Purpose

**`deterministic_affine_markup`** is a high-precision, mathematical coordinate transformation and cartographic visual annotation engine built for Model Context Protocol (MCP) clients and LangGraph autonomous agents.

While Vision-Language Models (VLMs) guess pixel locations qualitatively from visual appearance (often with bounding box errors of $\pm 20-50$ pixels or hallucinations), **Tool 11 executes rigorous, closed-form inverse affine matrix equations** directly from the GeoTIFF raster metadata. It maps real-world geographic coordinates (Lat/Lon or Easting/Northing) directly to exact integer and sub-pixel image coordinates $(C, R)$ with **zero hallucination probability**.

```text
[Landmark Lat/Lon from Tool 10] + [GeoTIFF Transform from Tool 6]
                             │
                             ▼
              CRS Validation & Reprojection
            (WGS84 EPSG:4326 ──▶ Raster Native CRS)
                             │
                             ▼
               Inverse Affine Transformation
                  (World Coordinates ──▶ Pixels)
                             │
                             ▼
             Pixel Clamping & Boundary Validation
            (Check if point falls inside image dimensions)
                             │
                             ▼
              High-Precision Markup Generator
      (Draws High-Contrast Pill Badges & Outlines on Visual PNG)
```

---

## 2. Mathematical Formulations & Derivations

### 1. Forward Affine Transformation Matrix (Raster to World)
The standard 6-parameter affine coordinate transformation model (OGC GeoTIFF 19-008r4 & Snyder 1987) relates pixel column $C$ and row $R$ to projected world coordinates $(X, Y)$:

$$\begin{bmatrix} X \\ Y \\ 1 \end{bmatrix} = \begin{bmatrix} a & b & c \\ d & e & f \\ 0 & 0 & 1 \end{bmatrix} \begin{bmatrix} C \\ R \\ 1 \end{bmatrix}$$

Expanding the linear system:
$$X = a \cdot C + b \cdot R + c$$
$$Y = d \cdot C + e \cdot R + f$$

Where:
- $a = \text{pixel width (E-W scale)}$
- $b = \text{rotation / shearing row parameter}$
- $c = X_{\text{origin}} \text{ (Easting/Longitude of top-left pixel)}$
- $d = \text{rotation / shearing column parameter}$
- $e = \text{pixel height (N-S scale, typically negative for north-up imagery)}$
- $f = Y_{\text{origin}} \text{ (Northing/Latitude of top-left pixel)}$

---

### 2. Closed-Form 2D Inverse Affine Matrix Derivation (World to Pixel)
To compute pixel coordinates $(C, R)$ from any world point $(X, Y)$, Tool 11 solves the inverse 2D linear equation:

$$\begin{bmatrix} a & b \\ d & e \end{bmatrix} \begin{bmatrix} C \\ R \end{bmatrix} = \begin{bmatrix} X - c \\ Y - f \end{bmatrix}$$

The matrix determinant $\det(A)$ is:
$$\det(A) = a \cdot e - b \cdot d$$

Applying Cramer's rule or direct matrix inversion:

$$\begin{bmatrix} C \\ R \end{bmatrix} = \frac{1}{a \cdot e - b \cdot d} \begin{bmatrix} e & -b \\ -d & a \end{bmatrix} \begin{bmatrix} X - c \\ Y - f \end{bmatrix}$$

Yielding the fundamental closed-form inverse equations:

$$C = \text{round}\left( \frac{(X - c) \cdot e - (Y - f) \cdot b}{a \cdot e - b \cdot d} \right)$$

$$R = \text{round}\left( \frac{(Y - f) \cdot a - (X - c) \cdot d}{a \cdot e - b \cdot d} \right)$$

---

### 3. CRS Reprojection & Datum Harmonization
If the GeoTIFF raster uses a Projected Coordinate System (e.g. UTM Zone 43N / `EPSG:32643`), input coordinates $(Lon_{\text{deg}}, Lat_{\text{deg}})$ from WGS84 (`EPSG:4326`) are reprojected using `pyproj.Transformer(always_xy=True)`:

$$(Lon, Lat)_{\text{WGS84}} \xrightarrow{\text{pyproj}} (X, Y)_{\text{Native Meters}}$$

---

### 4. Viewport Clamping & Out-of-Bounds Detection
For raster dimensions $\text{width} \times \text{height}$:
- If $0 \le C < \text{width}$ and $0 \le R < \text{height}$, the feature is classified as `inside_aoi = true`.
- If $C < 0$, $C \ge \text{width}$, $R < 0$, or $R \ge \text{height}$, the feature is classified as `inside_aoi = false`, and an explicit factual warning is emitted (*"Taj Mahal lies outside the bounds of this GeoTIFF raster"*).

---

## 3. High-Contrast Cartographic Markup Specifications

Tool 11 produces crisp, anti-aliased visual annotations with dark rounded pill badges:
- **Numbered Pill Badges:** `#1: Red Fort`, `#2: Jama Masjid` rendered with dark slate background (`#111827`), glowing neon outline, and subtle drop shadow.
- **Neon Color Palette:**
  - Neon Cyan (`#00E5FF`)
  - Neon Lime (`#00E676`)
  - Neon Amber (`#FFD600`)
  - Neon Coral (`#FF1744`)
  - Neon Magenta (`#D500F9`)
  - Neon Orange (`#FF9100`)
- **Marker Box / Crosshair:** Proportional bounding box with center crosshair alignment.

---

## 4. Input & Output Schema Specification

### Input Schema (`AffineMarkupRequest`):

| Field | Type | Required | Default | Description |
| :--- | :--- | :---: | :---: | :--- |
| `geotiff_path` | `str` | **Yes** | — | Path to GeoTIFF raster file. |
| `features` | `list[FeatureItem]` | **Yes** | — | List of features with `name`, `latitude`, `longitude`, `category`. |
| `base_image_path` | `str` | No | `None` | Path to RGB preview PNG. If omitted, auto-rendered from GeoTIFF. |
| `output_dir` | `str` | No | `None` | Output directory for marked visual PNG. |
| `draw_pill_badges`| `bool` | No | `True` | Whether to draw numbered pill labels. |
| `draw_bounding_boxes`| `bool` | No | `True` | Whether to draw marker boxes / crosshairs. |

### Sample Output:
```json
{
  "status": "success",
  "geotiff_path": "/path/to/delhi_scene.tif",
  "marked_image_path": "/path/to/delhi_scene_marked.png",
  "raster_grid": {
    "width": 512,
    "height": 512,
    "crs": "EPSG:4326",
    "affine_transform": [0.000156, 0.0, 77.20, 0.0, -0.000117, 28.68]
  },
  "features_total": 2,
  "features_inside_aoi": 2,
  "features_outside_aoi": 0,
  "features": [
    {
      "badge_number": 1,
      "name": "Red Fort",
      "latitude": 28.6562,
      "longitude": 77.2410,
      "pixel_c": 262,
      "pixel_r": 203,
      "subpixel_c": 262.4,
      "subpixel_r": 202.9,
      "inside_aoi": true,
      "marker_color": "#00E5FF"
    }
  ]
}
```

---

## 5. Reverse Direction: Pixel → WGS84 (`fractional_bbox_to_wgs84`)

Section 2's inverse transform goes world → pixel, for placing a badge at an
*already-known* coordinate. The same module also exposes the other direction,
pixel → world, used by a different caller: `mark_region_in_image` (the vision
tool, `backend/vision/`), which does the opposite job — a VLM visually
estimates *where* something is as a fractional image-space box, and the
backend needs that box's real-world coordinates.

```text
[Vision model's fractional bbox, 0-1 of width/height]
                             │
                             ▼
              Per-corner pixel coordinates
        (all four corners, not just two — see below)
                             │
                             ▼
             Forward Affine Transformation
                (Pixels ──▶ Native World X, Y)
                             │
                             ▼
              CRS Reprojection (if needed)
             (Native CRS ──▶ WGS84 EPSG:4326)
                             │
                             ▼
        min/max across the four corners = region_bbox
```

- **`compute_forward_affine_coords(c_pixel, r_pixel, affine_params)`** — the forward
  half of Section 2's matrix: $X = a \cdot C + b \cdot R + c$, $Y = d \cdot C + e \cdot
  R + f$. Exact for any affine transform, including a rotated/skewed one.
- **`reproject_native_to_wgs84(x_native, y_native, native_crs)`** — the inverse of
  Section 2.3's WGS84 → native reprojection, via the same `pyproj.Transformer`
  machinery.
- **`fractional_bbox_to_wgs84(geotiff_path, fractional_bbox)`** — the entry point
  `backend/tools/executor.py::_geometry_to_region_fields` calls for a plain box.
  Converts a `[x_min, y_min, x_max, y_max]` fractional box into pixel coordinates for
  **all four corners** individually (top-left, top-right, bottom-left, bottom-right —
  not just two opposite corners), runs each through the two functions above, then takes
  the min/max lon/lat across all four. Projecting all four corners, rather than
  assuming the box's edges stay axis-aligned in world space, is what keeps this exact
  even when the raster's affine transform has a rotation/shear term ($b \ne 0$ or
  $d \ne 0$), not only the common north-up case. Raises `ValueError` if the file has no
  CRS (an ordinary rendered PNG/JPEG, not a georeferenced raster) — the caller treats
  that as "no geo bbox available for this image," not a request failure.

**What this does and doesn't fix.** The conversion above is exact — it introduces no
error of its own. What it converts is still only as accurate as the vision model's own
visual estimate of the box (Section 1's "±20-50 pixel" caveat applies here just as much
as it does to a human eyeballing the image). For a target whose real-world coordinates
should be resolved with zero tolerance for a visual guess — a specific named landmark,
for instance — resolve it by name first (Tool 10) and use this module's *forward*
direction (Section 2) via `deterministic_affine_markup` instead of relying on
`mark_region_in_image`'s visual localization.

---

## 6. A Bounding Box Isn't Always the Right Shape: `polygon_pixels_to_wgs84`

A rectangle is a poor fit for an elongated, curved, or linear feature — a river, a
road, a coastline. The smallest axis-aligned box that fully contains a diagonal path
necessarily includes a large amount of area the feature never actually touches, no
matter how accurate any one corner is; this is a limitation of the *shape*, not of
coordinate precision, and Section 5's exact math doesn't fix it (it makes an
inevitably-loose box's coordinates exact, not the box tighter).

`polygon_pixels_to_wgs84(geotiff_path, fractional_polygon)` is the shape-level answer:
it accepts an ordered list of `[x, y]` fractional vertices (`mark_region_in_image`'s
`polygon`, only returned for a target the vision model judges elongated/curved rather
than blob-shaped — see `backend/vision/openai_provider.py`'s system prompt) and, for
**each** vertex individually, runs the same pixel → world → WGS84 math Section 5 uses
per corner. It returns three things, not one:

| Field | What it is | Used for |
| :--- | :--- | :--- |
| `polygon_wgs84` | The projected vertices, in order | Masking a raster crop to the feature's own path (`backend/rendering/raster_preview.py::_mask_to_polygon`) and drawing a tight on-screen outline (frontend `<svg><polygon>`) instead of a loose rectangle |
| `bbox_wgs84` | The polygon's own axis-aligned envelope | Any caller that still needs a plain rectangle (e.g. a `rasterio` crop window, which is inherently rectangular even when the *content* inside it gets masked) |
| `centroid_wgs84` | The arithmetic mean of the projected vertices | A location-based tool's anchor point (weather, reverse geocode) — see below |

**Why `centroid_wgs84` matters on its own.** `region_bbox`'s plain midpoint (the
intersection of its two diagonals) is only a meaningful "center" for a feature that's
actually near the middle of its own bounding box — true for a compact blob, false for
almost any elongated path. A river running along one edge of its bounding rectangle has
a bbox midpoint that can land on dry ground nowhere near the water. The polygon's own
vertex mean stays close to wherever the path's points actually are, which is what
`backend/orchestrator/registry.py::_region_center` now prefers whenever a
`region_centroid` is available (see that file and `backend/orchestrator/README.md`).

This is a *path* centroid (appropriate for points sampled along a line), not a
filled-polygon area centroid (which would need a proper shoelace-formula calculation
over a closed, non-self-intersecting boundary) — the vision model is tracing a route,
not outlining a filled region, so the vertex mean is the semantically correct choice
here, not an approximation of the "wrong" formula.

Raises the same way Section 5's bbox version does: `ValueError` for no CRS, or for
fewer than 3 vertices (not a valid polygon).

---

## 7. Research & Literature Foundation

The mathematical transformations and georeferencing standards implemented in Tool 11 are directly grounded in authoritative cartographic and photogrammetric literature:

1. **John P. Snyder (1987)**, *"Map Projections—A Working Manual"*, USGS Professional Paper 1395, U.S. Government Printing Office, Washington, D.C.
   *Defines the foundational mathematical equations for affine coordinate spaces, datum coordinate transformations, and ellipsoid georeferencing.*
2. **Open Geospatial Consortium (OGC)**, *"OGC GeoTIFF Standard (OGC 19-008r4)"*, Sections 6 & 7:
   *Formally standardizes `ModelTiepointTag`, `ModelPixelScaleTag`, `ModelTransformationTag`, and the inverse coordinate conversion equations for 2D affine raster grids.*
3. **Mikhail, E. M., Bethel, J. S., & McGlone, J. C. (2001)**, *"Introduction to Modern Photogrammetry"*, John Wiley & Sons, Chapter 3: Sensor Coordinate Systems & Projective Transformations.
   *Validates sub-pixel coordinate mapping accuracy and raster grid reprojection error bounds.*
