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

## 5. Research & Literature Foundation

The mathematical transformations and georeferencing standards implemented in Tool 11 are directly grounded in authoritative cartographic and photogrammetric literature:

1. **John P. Snyder (1987)**, *"Map Projections—A Working Manual"*, USGS Professional Paper 1395, U.S. Government Printing Office, Washington, D.C.
   *Defines the foundational mathematical equations for affine coordinate spaces, datum coordinate transformations, and ellipsoid georeferencing.*
2. **Open Geospatial Consortium (OGC)**, *"OGC GeoTIFF Standard (OGC 19-008r4)"*, Sections 6 & 7:
   *Formally standardizes `ModelTiepointTag`, `ModelPixelScaleTag`, `ModelTransformationTag`, and the inverse coordinate conversion equations for 2D affine raster grids.*
3. **Mikhail, E. M., Bethel, J. S., & McGlone, J. C. (2001)**, *"Introduction to Modern Photogrammetry"*, John Wiley & Sons, Chapter 3: Sensor Coordinate Systems & Projective Transformations.
   *Validates sub-pixel coordinate mapping accuracy and raster grid reprojection error bounds.*
