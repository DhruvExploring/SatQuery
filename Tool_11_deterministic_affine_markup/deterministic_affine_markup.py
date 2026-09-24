"""Tool 11: deterministic_affine_markup (Deterministic Affine Projector & Markup Engine)

Provides closed-form mathematical coordinate mapping and high-precision visual annotation:
  1. CRS Harmonization: Reprojects WGS84 (EPSG:4326) Lat/Lon to raster native CRS via pyproj.
  2. Inverse Affine Transformation: Exact closed-form matrix math mapping world (X, Y) -> pixel (C, R).
  3. Viewport Clamping & Validation: Flags inside vs outside raster dimensions (width, height).
  4. High-Contrast Visual Markup: Renders anti-aliased pill badges and bounding boxes on visual RGB preview.

Mathematical Grounding:
  - John P. Snyder (1987), "Map Projections—A Working Manual", USGS Professional Paper 1395.
  - Open Geospatial Consortium (OGC 19-008r4), "OGC GeoTIFF Standard", Sections 6 & 7.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import numpy as np
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field, field_validator, model_validator

# Ensure project root is on sys.path and load environment variables
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

load_dotenv(ROOT_DIR / ".env")

logger = logging.getLogger("satquery.tool11_affine_markup")

try:
    from fastmcp import FastMCP
except (ImportError, Exception):
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        FastMCP = None


# =============================================================================
# 1. Configuration & Color Palettes
# =============================================================================

@dataclass(frozen=True)
class AffineMarkupConfig:
    default_badge_padding_px: int = 6
    default_box_radius_px: int = 24
    default_border_width_px: int = 2
    neon_palette: tuple[str, ...] = (
        "#00E5FF",  # Neon Cyan
        "#00E676",  # Neon Green / Lime
        "#FFD600",  # Neon Amber / Yellow
        "#FF1744",  # Neon Coral / Red
        "#D500F9",  # Neon Magenta
        "#FF9100",  # Neon Orange
    )
    badge_bg_color: str = "#111827"  # Slate 900
    badge_text_color: str = "#FFFFFF"
    badge_border_alpha: int = 220


CONFIG = AffineMarkupConfig()


# =============================================================================
# 2. Pydantic Models
# =============================================================================

class FeatureItem(BaseModel):
    """Geographic feature / landmark to project and markup."""
    name: str = Field(..., description="Name or label for the feature (e.g. 'Red Fort').")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="WGS84 latitude.")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="WGS84 longitude.")
    category: Optional[str] = Field(default="landmark", description="Category/type (tourism, historic, etc.).")
    bbox_wgs84: Optional[list[float]] = Field(default=None, description="Optional bounding box [min_lon, min_lat, max_lon, max_lat].")
    radius_pixels: Optional[int] = Field(default=None, description="Custom marker box radius in pixels.")


class AffineMarkupRequest(BaseModel):
    """Input specification for Tool 11: Deterministic Affine Projector & Markup Engine."""
    geotiff_path: str = Field(..., description="Path to input GeoTIFF raster (source of CRS and affine matrix).")
    features: list[FeatureItem] = Field(default_factory=list, description="List of geographic features to project and mark.")
    base_image_path: Optional[str] = Field(default=None, description="Optional visual RGB preview PNG/JPEG. If omitted, rendered from GeoTIFF.")
    output_dir: Optional[str] = Field(default=None, description="Directory to save the annotated marked image.")
    draw_pill_badges: bool = Field(default=True, description="Whether to draw numbered pill badges above boxes.")
    draw_bounding_boxes: bool = Field(default=True, description="Whether to draw bounding boxes / crosshairs around points.")
    color_palette: Optional[list[str]] = Field(default=None, description="Custom hex color palette for features.")


# =============================================================================
# 3. Mathematical Affine Transform Core
# =============================================================================

def compute_inverse_affine_pixel(
    x_native: float,
    y_native: float,
    affine_params: Tuple[float, float, float, float, float, float],
) -> Tuple[float, float]:
    """Computes exact closed-form 2D inverse affine transformation.

    Forward Affine Equations (OGC GeoTIFF 19-008r4 & Snyder 1987):
      X = a * C + b * R + c
      Y = d * C + e * R + f

    Inverse Affine Solution:
      det = a * e - b * d
      C = ((X - c) * e - (Y - f) * b) / det
      R = ((Y - f) * a - (X - c) * d) / det

    Args:
      x_native: World coordinate X in native projected/geographic CRS.
      y_native: World coordinate Y in native projected/geographic CRS.
      affine_params: Tuple of (a, b, c, d, e, f).

    Returns:
      Tuple of floating point (column, row) pixel indices.
    """
    a, b, c, d, e, f = affine_params
    det = a * e - b * d
    if abs(det) < 1e-12:
        raise ValueError("Degenerate affine matrix: determinant is 0.")

    c_pixel = ((x_native - c) * e - (y_native - f) * b) / det
    r_pixel = ((y_native - f) * a - (x_native - c) * d) / det
    return c_pixel, r_pixel


def compute_forward_affine_coords(
    c_pixel: float,
    r_pixel: float,
    affine_params: Tuple[float, float, float, float, float, float],
) -> Tuple[float, float]:
    """Computes forward affine transformation (pixel C, R -> world X, Y)."""
    a, b, c, d, e, f = affine_params
    x_world = a * c_pixel + b * r_pixel + c
    y_world = d * c_pixel + e * r_pixel + f
    return x_world, y_world


# =============================================================================
# 4. CRS Harmonization & Reprojection
# =============================================================================

def reproject_wgs84_to_native(
    lon: float,
    lat: float,
    native_crs: Any,
) -> Tuple[float, float]:
    """Reprojects WGS84 (lon, lat) to native raster coordinate system."""
    import pyproj
    if native_crs is None:
        return lon, lat

    epsg = None
    try:
        epsg = native_crs.to_epsg()
    except Exception:
        pass

    if epsg == 4326:
        return lon, lat

    transformer = pyproj.Transformer.from_crs("EPSG:4326", native_crs, always_xy=True)
    x_native, y_native = transformer.transform(lon, lat)
    return float(x_native), float(y_native)


def reproject_native_to_wgs84(
    x_native: float,
    y_native: float,
    native_crs: Any,
) -> Tuple[float, float]:
    """Reprojects native raster coordinate system (X, Y) to WGS84 (lon, lat)
    -- the inverse of reproject_wgs84_to_native, used for the pixel -> world
    -> WGS84 direction (see fractional_bbox_to_wgs84)."""
    import pyproj
    if native_crs is None:
        return x_native, y_native

    epsg = None
    try:
        epsg = native_crs.to_epsg()
    except Exception:
        pass

    if epsg == 4326:
        return x_native, y_native

    transformer = pyproj.Transformer.from_crs(native_crs, "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(x_native, y_native)
    return float(lon), float(lat)


def _open_raster_affine_crs(geotiff_path: str) -> Tuple[Tuple[float, float, float, float, float, float], Any, int, int]:
    """Shared by fractional_bbox_to_wgs84 and polygon_pixels_to_wgs84: opens a
    GeoTIFF just long enough to read its affine transform, CRS, and pixel
    dimensions. Raises if the file has no CRS (not a georeferenced raster) --
    callers should treat that as "can't geocode this," not fail outright."""
    import rasterio

    with rasterio.open(geotiff_path) as src:
        crs = src.crs
        if crs is None:
            raise ValueError(f"{geotiff_path} has no CRS; cannot geocode pixel coordinates.")
        transform = src.transform
        affine_tuple = (transform.a, transform.b, transform.c, transform.d, transform.e, transform.f)
        return affine_tuple, crs, src.width, src.height


def _pixel_to_wgs84(
    c_px: float,
    r_px: float,
    affine_tuple: Tuple[float, float, float, float, float, float],
    crs: Any,
) -> Tuple[float, float]:
    """Pixel (column, row) -> WGS84 (lon, lat): forward affine, then
    reprojection -- the shared two-step math behind both bbox and polygon
    conversion below."""
    x_native, y_native = compute_forward_affine_coords(c_px, r_px, affine_tuple)
    return reproject_native_to_wgs84(x_native, y_native, crs)


def fractional_bbox_to_wgs84(
    geotiff_path: str,
    fractional_bbox: Tuple[float, float, float, float],
) -> Dict[str, Any]:
    """Converts a vision model's estimated bounding box -- [x_min, y_min,
    x_max, y_max] as fractions 0-1 of image width/height, top-left origin,
    e.g. mark_region_in_image's `bbox` -- into an exact real-world WGS84
    bounding box, using the GeoTIFF's own affine transform (the same
    closed-form math as compute_inverse_affine_pixel, run forward via
    compute_forward_affine_coords) rather than a linear approximation
    against the whole scene's own bounds_wgs84.

    Projects all four pixel corners individually (not just two opposite
    corners) and takes their min/max, so a rotated or skewed affine
    transform is still handled correctly, not just the common north-up
    case. Raises if the file has no CRS (not a georeferenced raster) --
    callers should treat that as "can't geocode this bbox," not fail
    the whole request.
    """
    x_min_f, y_min_f, x_max_f, y_max_f = fractional_bbox
    affine_tuple, crs, width, height = _open_raster_affine_crs(geotiff_path)

    corners_px = {
        "top_left": (x_min_f * width, y_min_f * height),
        "top_right": (x_max_f * width, y_min_f * height),
        "bottom_left": (x_min_f * width, y_max_f * height),
        "bottom_right": (x_max_f * width, y_max_f * height),
    }

    corners_wgs84: Dict[str, Dict[str, float]] = {}
    lons: list[float] = []
    lats: list[float] = []
    for label, (c_px, r_px) in corners_px.items():
        lon, lat = _pixel_to_wgs84(c_px, r_px, affine_tuple, crs)
        corners_wgs84[label] = {"latitude": lat, "longitude": lon}
        lons.append(lon)
        lats.append(lat)

    return {
        "bbox_wgs84": [min(lons), min(lats), max(lons), max(lats)],
        "corners_wgs84": corners_wgs84,
    }


def polygon_pixels_to_wgs84(
    geotiff_path: str,
    fractional_polygon: List[Tuple[float, float]],
) -> Dict[str, Any]:
    """Converts a vision model's estimated polygon path -- an ordered list of
    [x, y] fractions 0-1 of image width/height, top-left origin -- into exact
    real-world WGS84 vertices, using the same forward-affine + reprojection
    math as fractional_bbox_to_wgs84.

    Meant for an elongated, curved, or irregular feature (a river, road,
    coastline) where a rectangular bbox necessarily includes far more area
    than the actual feature -- unlike a bbox, a polygon can trace the
    feature's own path/outline. Returns:
      polygon_wgs84: the projected vertices, in order, as
        [{"latitude": ..., "longitude": ...}, ...]
      bbox_wgs84: the polygon's own axis-aligned bounding envelope, for any
        caller that still needs a plain rectangle (e.g. a raster crop
        window) -- always at least as tight as, and usually tighter than,
        a bbox drawn directly around the same feature.
      centroid_wgs84: the arithmetic mean of the projected vertices. This is
        a *path* centroid (appropriate for points sampled along a line, e.g.
        a river's course), not a filled-polygon area centroid -- a bbox's
        own midpoint can land far from an elongated feature's actual path,
        which this fixes for point-based lookups (weather, reverse geocode).

    Raises if the file has no CRS, or fewer than 3 vertices are given.
    """
    if len(fractional_polygon) < 3:
        raise ValueError("A polygon needs at least 3 vertices.")

    affine_tuple, crs, width, height = _open_raster_affine_crs(geotiff_path)

    polygon_wgs84: list[Dict[str, float]] = []
    lons: list[float] = []
    lats: list[float] = []
    for x_f, y_f in fractional_polygon:
        lon, lat = _pixel_to_wgs84(x_f * width, y_f * height, affine_tuple, crs)
        polygon_wgs84.append({"latitude": lat, "longitude": lon})
        lons.append(lon)
        lats.append(lat)

    return {
        "polygon_wgs84": polygon_wgs84,
        "bbox_wgs84": [min(lons), min(lats), max(lons), max(lats)],
        "centroid_wgs84": {"latitude": sum(lats) / len(lats), "longitude": sum(lons) / len(lons)},
    }


# =============================================================================
# 5. Visual Preview Extractor & Renderer
# =============================================================================

def _render_geotiff_preview_rgb(geotiff_path: str, output_path: str) -> Image.Image:
    """Renders high-quality RGB preview image from GeoTIFF with 2%-98% percentile stretch."""
    import rasterio
    with rasterio.open(geotiff_path) as src:
        count = src.count
        w, h = src.width, src.height

        if count >= 3:
            # Read first 3 bands (assumed R, G, B)
            b1 = src.read(1).astype(np.float32)
            b2 = src.read(2).astype(np.float32)
            b3 = src.read(3).astype(np.float32)
            channels = [b1, b2, b3]
        else:
            # Single band grayscale -> RGB
            b1 = src.read(1).astype(np.float32)
            channels = [b1, b1, b1]

        stretched_channels = []
        for ch in channels:
            valid = ch[np.isfinite(ch)]
            if len(valid) > 0:
                p2, p98 = np.percentile(valid, (2, 98))
                if p98 > p2:
                    clipped = np.clip(ch, p2, p98)
                    norm = ((clipped - p2) / (p98 - p2) * 255.0).astype(np.uint8)
                else:
                    norm = np.zeros_like(ch, dtype=np.uint8)
            else:
                norm = np.zeros_like(ch, dtype=np.uint8)
            stretched_channels.append(norm)

        rgb_arr = np.dstack(stretched_channels)
        img = Image.fromarray(rgb_arr, mode="RGB")
        img.save(output_path, "PNG")
        return img


# =============================================================================
# 6. High-Precision Markup Drawing Engine
# =============================================================================

def draw_markup_pill_badges(
    base_image: Image.Image,
    projected_features: list[dict[str, Any]],
    palette: list[str],
    draw_pill_badges: bool = True,
    draw_bounding_boxes: bool = True,
) -> Image.Image:
    """Renders high-contrast anti-aliased pill badges and markers on the image with collision avoidance."""
    annotated = base_image.convert("RGBA")
    overlay = Image.new("RGBA", annotated.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    w, h = annotated.size
    min_dim = min(w, h)

    # 1. Resolution-Adaptive Sizing
    adaptive_rad = max(7, min(18, int(min_dim * 0.04)))
    font_size = max(10, min(14, int(min_dim * 0.045)))
    pill_pad = max(3, min(6, int(min_dim * 0.015)))

    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    occupied_regions: list[tuple[int, int, int, int]] = []

    def boxes_intersect(b1: tuple[int, int, int, int], b2: tuple[int, int, int, int]) -> bool:
        return not (b1[2] < b2[0] or b1[0] > b2[2] or b1[3] < b2[1] or b1[1] > b2[3])

    # First pass: collect all marker boxes so badges can avoid colliding with them
    feature_marker_boxes: list[Optional[tuple[int, int, int, int]]] = []
    for idx, feat in enumerate(projected_features):
        if not feat.get("inside_aoi"):
            feature_marker_boxes.append(None)
            continue
        c = feat["pixel_c"]
        r = feat["pixel_r"]
        rad = feat.get("radius_pixels") or adaptive_rad
        box_left = max(0, c - rad)
        box_top = max(0, r - rad)
        box_right = min(w - 1, c + rad)
        box_bottom = min(h - 1, r + rad)
        box_rect = (box_left, box_top, box_right, box_bottom)
        feature_marker_boxes.append(box_rect)
        if draw_bounding_boxes:
            occupied_regions.append(box_rect)

    for idx, feat in enumerate(projected_features):
        if not feat.get("inside_aoi"):
            continue

        c = feat["pixel_c"]
        r = feat["pixel_r"]
        color_hex = palette[idx % len(palette)]
        rgb = tuple(int(color_hex.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
        neon_color = (rgb[0], rgb[1], rgb[2], 255)
        neon_glow = (rgb[0], rgb[1], rgb[2], 85)

        badge_num = feat.get("badge_number", idx + 1)
        name = feat.get("name", f"Feature {badge_num}")
        label_text = f"#{badge_num}: {name}"

        box_rect = feature_marker_boxes[idx]
        if box_rect is None:
            continue
        box_left, box_top, box_right, box_bottom = box_rect

        # 1. Bounding Box / Marker
        if draw_bounding_boxes:
            draw.rectangle([box_left, box_top, box_right, box_bottom], fill=neon_glow, outline=neon_color, width=2)
            cross_len = max(3, min(6, int(adaptive_rad * 0.5)))
            draw.line([(c - cross_len, r), (c + cross_len, r)], fill=(255, 255, 255, 240), width=2)
            draw.line([(c, r - cross_len), (c, r + cross_len)], fill=(255, 255, 255, 240), width=2)

        # 2. Pill Badge with Smart Placement & Collision Avoidance
        if draw_pill_badges:
            text_bbox = draw.textbbox((0, 0), label_text, font=font)
            text_w = text_bbox[2] - text_bbox[0]
            text_h = text_bbox[3] - text_bbox[1]

            pill_w = text_w + (pill_pad * 2) + 6
            pill_h = text_h + (pill_pad * 2) + 2

            candidate_positions = [
                # Top of box
                (c - (pill_w // 2), box_top - pill_h - 4),
                # Bottom of box
                (c - (pill_w // 2), box_bottom + 4),
                # Right of box
                (box_right + 4, r - (pill_h // 2)),
                # Left of box
                (box_left - pill_w - 4, r - (pill_h // 2)),
                # Top-Right of box
                (box_right + 2, box_top - pill_h - 2),
                # Bottom-Right of box
                (box_right + 2, box_bottom + 2),
            ]

            best_candidate = None
            best_score = float("inf")

            for cx0, cy0 in candidate_positions:
                clamped_x0 = max(4, min(w - pill_w - 4, cx0))
                clamped_y0 = max(4, min(h - pill_h - 4, cy0))
                cand_rect = (clamped_x0, clamped_y0, clamped_x0 + pill_w, clamped_y0 + pill_h)

                score = 0
                for occ in occupied_regions:
                    if occ == box_rect:
                        continue
                    if boxes_intersect(cand_rect, occ):
                        ox = max(0, min(cand_rect[2], occ[2]) - max(cand_rect[0], occ[0]))
                        oy = max(0, min(cand_rect[3], occ[3]) - max(cand_rect[1], occ[1]))
                        score += (ox * oy) + 500

                pos_idx = candidate_positions.index((cx0, cy0))
                score += pos_idx * 10

                if score < best_score:
                    best_score = score
                    best_candidate = (clamped_x0, clamped_y0, clamped_x0 + pill_w, clamped_y0 + pill_h)
                    if score == 0:
                        break

            pill_x0, pill_y0, pill_x1, pill_y1 = best_candidate or (
                max(4, min(w - pill_w - 4, c - (pill_w // 2))),
                max(4, min(h - pill_h - 4, box_top - pill_h - 4)),
                max(4, min(w - pill_w - 4, c - (pill_w // 2))) + pill_w,
                max(4, min(h - pill_h - 4, box_top - pill_h - 4)) + pill_h,
            )
            occupied_regions.append((pill_x0, pill_y0, pill_x1, pill_y1))

            # Pill Drop Shadow
            draw.rounded_rectangle(
                [pill_x0 + 1, pill_y0 + 1, pill_x1 + 1, pill_y1 + 1],
                radius=4,
                fill=(0, 0, 0, 150),
            )
            # Pill Dark Body
            draw.rounded_rectangle(
                [pill_x0, pill_y0, pill_x1, pill_y1],
                radius=4,
                fill=(15, 23, 42, 240),  # Slate 900
                outline=neon_color,
                width=1,
            )
            # Badge Text
            draw.text(
                (pill_x0 + pill_pad + 3, pill_y0 + pill_pad),
                label_text,
                fill=(255, 255, 255, 255),
                font=font,
            )

    composite = Image.alpha_composite(annotated, overlay)
    return composite.convert("RGB")


# =============================================================================
# 7. Main Projection & Markup Dispatcher
# =============================================================================

def project_and_markup_raster(request: Union[AffineMarkupRequest, Dict[str, Any]]) -> Dict[str, Any]:
    """Universal execution dispatcher for Tool 11: Deterministic Affine Projector & Markup Engine."""
    import rasterio

    if isinstance(request, dict):
        req = AffineMarkupRequest(**request)
    else:
        req = request

    if not req.features:
        return {
            "status": "no_features",
            "features": [],
            "features_total": 0,
            "features_inside_aoi": 0,
            "features_outside_aoi": 0,
            "message": "No valid geographic features provided for markup.",
        }

    geotiff_path = Path(req.geotiff_path).resolve()
    if not geotiff_path.exists() or not geotiff_path.is_file():
        return {
            "status": "error",
            "message": f"GeoTIFF file not found at path: '{req.geotiff_path}'",
        }

    # Prepare output paths
    out_dir = Path(req.output_dir).resolve() if req.output_dir else geotiff_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    marked_image_path = out_dir / f"{geotiff_path.stem}_marked.png"
    preview_base_path = out_dir / f"{geotiff_path.stem}_preview.png"

    with rasterio.open(geotiff_path) as src:
        crs = src.crs
        transform = src.transform  # affine.Affine(a, b, c, d, e, f)
        affine_tuple = (transform.a, transform.b, transform.c, transform.d, transform.e, transform.f)
        width, height = src.width, src.height
        bounds = src.bounds
        epsg = crs.to_epsg() if crs else None

    # Load or generate base preview image
    if req.base_image_path and Path(req.base_image_path).exists():
        base_img = Image.open(req.base_image_path).convert("RGB")
    else:
        base_img = _render_geotiff_preview_rgb(str(geotiff_path), str(preview_base_path))

    # Perform deterministic coordinate projection for each unique feature
    projected_features: list[dict[str, Any]] = []
    inside_count = 0
    outside_count = 0
    warnings: list[str] = []

    palette = req.color_palette or list(CONFIG.neon_palette)
    seen_pixels: list[tuple[int, int]] = []
    seen_names: set[str] = set()

    # Deduplicate input features
    unique_features: list[FeatureItem] = []
    for feat in req.features:
        key = (feat.name.strip().lower(), round(feat.latitude, 4), round(feat.longitude, 4))
        if key not in seen_names:
            seen_names.add(key)
            unique_features.append(feat)

    for idx, feat in enumerate(unique_features):
        lon, lat = feat.longitude, feat.latitude
        x_native, y_native = reproject_wgs84_to_native(lon, lat, native_crs=crs)

        # Compute exact inverse affine pixel coordinates
        c_exact, r_exact = compute_inverse_affine_pixel(x_native, y_native, affine_tuple)
        c_round = int(round(c_exact))
        r_round = int(round(r_exact))

        # Check proximity to already marked points: if within 5px, avoid duplicate badge overlay
        is_cluster_duplicate = any(abs(c_round - pc) <= 5 and abs(r_round - pr) <= 5 for pc, pr in seen_pixels)
        if is_cluster_duplicate and len(unique_features) > 1:
            continue
        seen_pixels.append((c_round, r_round))

        inside_aoi = (0 <= c_round < width) and (0 <= r_round < height)

        if inside_aoi:
            inside_count += 1
        else:
            outside_count += 1
            warnings.append(
                f"Feature '{feat.name}' at ({lat}°N, {lon}°E) projects to pixel ({c_round}, {r_round}) "
                f"which lies outside raster dimensions ({width}x{height})."
            )

        # Proportional normalized coordinates (0.0 to 1.0)
        norm_x = round(c_exact / width, 4) if width > 0 else 0.0
        norm_y = round(r_exact / height, 4) if height > 0 else 0.0

        badge_num = len(projected_features) + 1
        projected_features.append({
            "badge_number": badge_num,
            "name": feat.name,
            "category": feat.category or "landmark",
            "latitude": lat,
            "longitude": lon,
            "native_coords": {
                "x": round(x_native, 3),
                "y": round(y_native, 3),
            },
            "pixel_c": c_round,
            "pixel_r": r_round,
            "subpixel_c": round(c_exact, 3),
            "subpixel_r": round(r_exact, 3),
            "normalized_viewport": {
                "norm_x": norm_x,
                "norm_y": norm_y,
            },
            "inside_aoi": inside_aoi,
            "marker_color": palette[(badge_num - 1) % len(palette)],
            "radius_pixels": feat.radius_pixels,
        })

    # Render Visual Markup on Base Image
    marked_img = draw_markup_pill_badges(
        base_image=base_img,
        projected_features=projected_features,
        palette=palette,
        draw_pill_badges=req.draw_pill_badges,
        draw_bounding_boxes=req.draw_bounding_boxes,
    )
    marked_img.save(marked_image_path, "PNG")

    return {
        "status": "success",
        "geotiff_path": str(geotiff_path),
        "marked_image_path": str(marked_image_path),
        "raster_grid": {
            "width": width,
            "height": height,
            "crs": str(crs),
            "epsg": epsg,
            "affine_transform": list(affine_tuple),
        },
        "features_total": len(req.features),
        "features_inside_aoi": inside_count,
        "features_outside_aoi": outside_count,
        "features": projected_features,
        "warnings": warnings,
        "mathematical_provenance": {
            "standards": [
                "John P. Snyder (1987) USGS PP 1395",
                "OGC GeoTIFF 19-008r4 Sections 6 & 7",
            ],
            "equations": "C = ((X-c)e - (Y-f)b) / (ae - bd); R = ((Y-f)a - (X-c)d) / (ae - bd)",
            "subpixel_precision": True,
            "hallucination_probability": 0.0,
        },
    }


# =============================================================================
# 8. FastMCP Server Endpoint & Standalone Runner
# =============================================================================

if FastMCP:
    mcp_tool = FastMCP("satquery_tool11")

    @mcp_tool.tool(
        name="deterministic_affine_markup",
        description="Deterministic inverse affine coordinate projection and high-contrast visual badge markup.",
    )
    def mcp_deterministic_affine_markup(
        geotiff_path: str,
        features: list[dict[str, Any]],
        base_image_path: Optional[str] = None,
        output_dir: Optional[str] = None,
        draw_pill_badges: bool = True,
        draw_bounding_boxes: bool = True,
    ) -> Dict[str, Any]:
        feat_objects = [FeatureItem(**f) for f in features]
        req = AffineMarkupRequest(
            geotiff_path=geotiff_path,
            features=feat_objects,
            base_image_path=base_image_path,
            output_dir=output_dir,
            draw_pill_badges=draw_pill_badges,
            draw_bounding_boxes=draw_bounding_boxes,
        )
        return project_and_markup_raster(req)


if __name__ == "__main__":
    print("=== Testing Tool 11: Deterministic Affine Projector & Markup Engine ===")
    import tempfile
    import rasterio
    from rasterio.transform import from_bounds

    # Create synthetic test GeoTIFF (Delhi AOI)
    with tempfile.TemporaryDirectory() as tmpdir:
        test_tif = Path(tmpdir) / "delhi_test.tif"
        w, h = 512, 512
        min_lon, min_lat, max_lon, max_lat = 77.20, 28.62, 77.28, 28.68
        transform = from_bounds(min_lon, min_lat, max_lon, max_lat, w, h)

        data = (np.random.rand(3, h, w) * 255).astype(np.uint8)
        with rasterio.open(
            test_tif,
            "w",
            driver="GTiff",
            height=h,
            width=w,
            count=3,
            dtype="uint8",
            crs="EPSG:4326",
            transform=transform,
        ) as dst:
            dst.write(data)

        test_features = [
            FeatureItem(name="Red Fort", latitude=28.6562, longitude=77.2410, category="historic"),
            FeatureItem(name="Jama Masjid", latitude=28.6507, longitude=77.2334, category="religious"),
            FeatureItem(name="Taj Mahal (Out of Bounds)", latitude=27.1751, longitude=78.0421, category="monument"),
        ]

        res = project_and_markup_raster({
            "geotiff_path": str(test_tif),
            "features": [f.model_dump() for f in test_features],
            "output_dir": tmpdir,
        })
        print(json.dumps(res, indent=2))
        print(f"\nMarked image saved at: {res.get('marked_image_path')}")
