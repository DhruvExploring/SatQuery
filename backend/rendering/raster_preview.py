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

import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling

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
        band_count = src.count
        if band_selection:
            indices = [i for i in band_selection if 1 <= i <= band_count]
        elif band_count >= 3:
            indices = [1, 2, 3]
        else:
            indices = [1]
        if not indices:
            indices = [1]

        scale = min(1.0, size / max(src.width, src.height))
        out_width = max(1, round(src.width * scale))
        out_height = max(1, round(src.height * scale))

        data = src.read(
            indices,
            out_shape=(len(indices), out_height, out_width),
            resampling=resampling,
        )
        nodata = src.nodata

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
        image = _render_categorical(data[0], mask[0])
    elif len(indices) >= 3:
        channels = [_stretch_to_uint8(data[i], mask[i]) for i in range(3)]
        image = Image.merge("RGB", [Image.fromarray(c) for c in channels])
    else:
        image = Image.fromarray(_stretch_to_uint8(data[0], mask[0]), mode="L")

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
