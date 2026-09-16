"""Region cropping (backend/rendering/raster_preview.py) and the per-pixel
WGS84 resolution/corner fields Tool 6 now extracts (Tool_6_inspect_geotiff_metadata).
No network -- builds a small synthetic north-up GeoTIFF with rasterio.
"""
from __future__ import annotations

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from backend.rendering.raster_preview import render_geotiff_region_preview

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# A 100x100 px, north-up, EPSG:4326 raster covering exactly [10.0, 20.0, 11.0, 21.0].
_BBOX = (10.0, 20.0, 11.0, 21.0)


def _write_synthetic_tif(path, bbox=_BBOX, width=100, height=100, count=3, crs="EPSG:4326"):
    transform = from_bounds(*bbox, width, height)
    data = (np.random.rand(count, height, width) * 255).astype("uint8")
    with rasterio.open(
        path, "w", driver="GTiff", height=height, width=width, count=count,
        dtype="uint8", crs=crs, transform=transform,
    ) as dst:
        dst.write(data)


def test_region_crop_returns_png_and_clamped_window(tmp_path):
    tif_path = tmp_path / "scene.tif"
    _write_synthetic_tif(tif_path)

    # A sub-region entirely inside the raster's bounds.
    png_bytes, region_info = render_geotiff_region_preview(
        str(tif_path), [10.25, 20.25, 10.75, 20.75]
    )
    assert png_bytes.startswith(_PNG_MAGIC)
    assert region_info["pixel_window"]["width"] > 0
    assert region_info["pixel_window"]["height"] > 0
    achieved = region_info["bounds_wgs84_achieved"]
    assert 10.2 < achieved["min_lon"] < 10.3
    assert 10.7 < achieved["max_lon"] < 10.8


def test_region_crop_clamps_overshooting_region(tmp_path):
    tif_path = tmp_path / "scene.tif"
    _write_synthetic_tif(tif_path)

    # Overshoots past the raster's actual bounds on all sides -- should clamp,
    # not fail, since it still overlaps the raster.
    png_bytes, region_info = render_geotiff_region_preview(
        str(tif_path), [9.0, 19.0, 12.0, 22.0]
    )
    assert png_bytes.startswith(_PNG_MAGIC)
    achieved = region_info["bounds_wgs84_achieved"]
    assert achieved["min_lon"] >= 9.99
    assert achieved["max_lon"] <= 11.01


def test_region_crop_rejects_non_overlapping_region(tmp_path):
    tif_path = tmp_path / "scene.tif"
    _write_synthetic_tif(tif_path)

    with pytest.raises(ValueError, match="does not overlap"):
        render_geotiff_region_preview(str(tif_path), [50.0, 50.0, 51.0, 51.0])


def test_region_crop_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        render_geotiff_region_preview(str(tmp_path / "nope.tif"), [10.0, 20.0, 10.5, 20.5])


def test_region_crop_requires_georeferencing(tmp_path):
    tif_path = tmp_path / "no_crs.tif"
    transform = from_bounds(*_BBOX, 50, 50)
    data = (np.random.rand(3, 50, 50) * 255).astype("uint8")
    with rasterio.open(
        tif_path, "w", driver="GTiff", height=50, width=50, count=3,
        dtype="uint8", transform=transform,
    ) as dst:
        dst.write(data)

    with pytest.raises(ValueError, match="no georeferencing"):
        render_geotiff_region_preview(str(tif_path), [10.25, 20.25, 10.75, 20.75])


def test_tool6_reports_pixel_resolution_and_corners(tmp_path):
    from Tool_6_inspect_geotiff_metadata.inspect_geotiff_metadata import (
        GeoTIFFInspectionRequest,
        inspect_geotiff_metadata,
    )

    tif_path = tmp_path / "scene.tif"
    _write_synthetic_tif(tif_path, width=100, height=200)

    req = GeoTIFFInspectionRequest(file_path=str(tif_path))
    result = inspect_geotiff_metadata(req)

    assert result["status"] == "success"
    spatial = result["spatial"]
    pixel_size = spatial["pixel_size_wgs84_degrees"]
    # 1 degree of lon over 100 px, 1 degree of lat over 200 px.
    assert pixel_size["lon_per_pixel"] == pytest.approx(0.01, rel=1e-3)
    assert pixel_size["lat_per_pixel"] == pytest.approx(0.005, rel=1e-3)

    corners = spatial["corners_wgs84"]
    assert corners["top_left"] == {"latitude": 21.0, "longitude": 10.0}
    assert corners["top_right"] == {"latitude": 21.0, "longitude": 11.0}
    assert corners["bottom_left"] == {"latitude": 20.0, "longitude": 10.0}
    assert corners["bottom_right"] == {"latitude": 20.0, "longitude": 11.0}
