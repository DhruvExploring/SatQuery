"""Render a GeoTIFF band or band-combination to a viewable PNG.

Used by two callers:
- GET /api/v1/raster-preview and GET /api/v1/raster-file
  (backend/api/routes/rasters.py) for the frontend's RasterViewer.
- the vision tool (backend/tools/executor.py::_run_vlm_analysis), which needs a
  standard image file before handing anything to a VLM — EarthMind, InternVL, and
  OpenAI vision models cannot consume a multi-band float32 GeoTIFF directly.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.errors import WindowError as RasterioWindowError
from rasterio.warp import transform_bounds
from rasterio.windows import Window, bounds as window_bounds, from_bounds

# Rasters whose pixel values are discrete class codes (LULC, change masks) must be
# resampled with nearest-neighbor, never interpolated — matches the safe-resampling
# rule already documented in backend/orchestrator/registry.py and the top-level README.
_CATEGORICAL_PATH_HINTS = ("worldcover", "lulc", "landcover", "change_mask", "zone_mask")

_PALETTE = [
    (0, 0, 0), (34, 139, 34), (154, 205, 50), (189, 183, 107),
    (255, 215, 0), (205, 92, 92), (169, 169, 169), (255, 255, 255),
    (0, 191, 255), (32, 178, 170), (147, 112, 219), (218, 112, 214),
]


def _looks_categorical(path: str) -> bool:
    lowered = path.replace("\\", "/").lower()
    return any(hint in lowered for hint in _CATEGORICAL_PATH_HINTS)


def _stretch_to_uint8(
    band: np.ndarray,
    mask: np.ndarray,
    low_pct: float = 2.0,
    high_pct: float = 98.0,
) -> np.ndarray:
    """Percentile-stretch a single band to 0-255, ignoring masked (invalid) pixels."""
    valid = band[mask]
    if valid.size == 0:
        return np.zeros(band.shape, dtype=np.uint8)
    lo, hi = np.percentile(valid, [low_pct, high_pct])
    if hi <= lo:
        lo, hi = float(valid.min()), float(valid.max())
        if hi <= lo:
            hi = lo + 1.0
    scaled = np.clip((band.astype(np.float64) - lo) / (hi - lo), 0.0, 1.0)
    out = (scaled * 255.0).astype(np.uint8)
    out[~mask] = 0
    return out


def _render_categorical(band: np.ndarray, mask: np.ndarray) -> Image.Image:
    values = sorted(np.unique(band[mask]).tolist()) if mask.any() else []
    color_for_value = {v: _PALETTE[i % len(_PALETTE)] for i, v in enumerate(values)}

    rgb = np.zeros((*band.shape, 3), dtype=np.uint8)
    for value, color in color_for_value.items():
        rgb[band == value] = color
    return Image.fromarray(rgb, mode="RGB")


def _select_band_indices(band_count: int, band_selection: list[int] | None) -> list[int]:
    if band_selection:
        indices = [i for i in band_selection if 1 <= i <= band_count]
    elif band_count >= 3:
        indices = [1, 2, 3]
    else:
        indices = [1]
    return indices or [1]


def _finalize_preview_image(
    data: np.ndarray,
    nodata: float | None,
    categorical: bool,
    indices: list[int],
) -> Image.Image:
    if nodata is not None:
        if np.issubdtype(data.dtype, np.floating):
            mask = ~np.isclose(data, nodata)
        else:
            mask = data != nodata
    else:
        mask = np.ones_like(data, dtype=bool)
    if np.issubdtype(data.dtype, np.floating):
        mask &= np.isfinite(data)

    if categorical:
        return _render_categorical(data[0], mask[0])
    if len(indices) >= 3:
        channels = [_stretch_to_uint8(data[i], mask[i]) for i in range(3)]
        return Image.merge("RGB", [Image.fromarray(c) for c in channels])
    return Image.fromarray(_stretch_to_uint8(data[0], mask[0]), mode="L")


def render_geotiff_preview(
    path: str,
    band_selection: list[int] | None = None,
    size: int = 1024,
    categorical: bool | None = None,
) -> bytes:
    """Render a GeoTIFF to PNG bytes, downsampled so its longest edge is <= size.

    band_selection: 1-based band indices to read. Defaults to bands [1, 2, 3] for
    3+ band rasters (optical/multispectral RGB), or band [1] alone otherwise
    (e.g. a single-band index, or SAR VV/VH — the preview shows VV; the full
    GeoTIFF with both polarizations is still available via raster-file download).
    categorical: force nearest-neighbor resampling and a discrete-class palette
    for LULC / change-mask rasters. Auto-detected from the filename when omitted.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Raster not found: {path}")

    if categorical is None:
        categorical = _looks_categorical(path)
    resampling = Resampling.nearest if categorical else Resampling.bilinear

    with rasterio.open(p) as src:
        indices = _select_band_indices(src.count, band_selection)

        scale = min(1.0, size / max(src.width, src.height))
        out_width = max(1, round(src.width * scale))
        out_height = max(1, round(src.height * scale))

        data = src.read(
            indices,
            out_shape=(len(indices), out_height, out_width),
            resampling=resampling,
        )
        nodata = src.nodata

    image = _finalize_preview_image(data, nodata, categorical, indices)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def render_geotiff_region_preview(
    path: str,
    bbox_wgs84: list[float],
    band_selection: list[int] | None = None,
    size: int = 768,
    categorical: bool | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Render only the pixel window covered by a WGS84 bbox, cropping the
    source raster itself rather than the whole rendered scene.

    Used to ground a description in a region the user actually marked/drew
    (e.g. a frontend ROI box converted to real-world coordinates), instead of
    asking a vision model to visually re-locate that region in the full image.

    Returns (png_bytes, region_info): region_info reports the pixel window
    actually read and its real-world extent *after* clamping to the raster's
    own bounds, since a drawn box can slightly overshoot the image edge.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Raster not found: {path}")
    if not bbox_wgs84 or len(bbox_wgs84) != 4:
        raise ValueError("bbox_wgs84 must be [min_lon, min_lat, max_lon, max_lat].")

    if categorical is None:
        categorical = _looks_categorical(path)
    resampling = Resampling.nearest if categorical else Resampling.bilinear

    min_lon, min_lat, max_lon, max_lat = bbox_wgs84

    with rasterio.open(p) as src:
        if src.crs is None:
            raise ValueError(
                "This image has no georeferencing (no CRS) -- region cropping "
                "by real-world coordinates requires a georeferenced GeoTIFF."
            )

        if str(src.crs) != "EPSG:4326":
            left, bottom, right, top = transform_bounds(
                "EPSG:4326", src.crs, min_lon, min_lat, max_lon, max_lat
            )
        else:
            left, bottom, right, top = min_lon, min_lat, max_lon, max_lat

        window = from_bounds(left, bottom, right, top, transform=src.transform)
        # Clamp to the raster's actual extent -- a marked region can slightly
        # overshoot the image edge (rounding in the frontend's fractional ROI
        # math, or a region drawn right at the border). intersection() raises
        # WindowError rather than returning an empty window when there's no
        # overlap at all, so that case is handled explicitly below.
        try:
            window = window.intersection(Window(0, 0, src.width, src.height))
        except RasterioWindowError:
            window = None
        if window is None or window.width < 1 or window.height < 1:
            raise ValueError("The marked region does not overlap this raster's extent.")

        indices = _select_band_indices(src.count, band_selection)

        scale = min(1.0, size / max(window.width, window.height))
        out_width = max(1, round(window.width * scale))
        out_height = max(1, round(window.height * scale))

        data = src.read(
            indices,
            window=window,
            out_shape=(len(indices), out_height, out_width),
            resampling=resampling,
        )
        nodata = src.nodata

        achieved_native = window_bounds(window, src.transform)
        achieved_wgs84 = (
            transform_bounds(src.crs, "EPSG:4326", *achieved_native)
            if str(src.crs) != "EPSG:4326"
            else achieved_native
        )

    image = _finalize_preview_image(data, nodata, categorical, indices)
    buf = io.BytesIO()
    image.save(buf, format="PNG")

    region_info = {
        "pixel_window": {
            "col_off": round(window.col_off, 2),
            "row_off": round(window.row_off, 2),
            "width": round(window.width, 2),
            "height": round(window.height, 2),
        },
        "bounds_wgs84_requested": {
            "min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat,
        },
        "bounds_wgs84_achieved": {
            "min_lon": round(achieved_wgs84[0], 6),
            "min_lat": round(achieved_wgs84[1], 6),
            "max_lon": round(achieved_wgs84[2], 6),
            "max_lat": round(achieved_wgs84[3], 6),
        },
    }
    return buf.getvalue(), region_info
