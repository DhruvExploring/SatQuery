"""GeoTIFF -> PNG rendering: no network, exercises real rasterio/Pillow code
against a checked-in sample raster.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.rendering.raster_preview import render_geotiff_preview

_SAMPLE_OPTICAL = (
    Path(__file__).resolve().parent.parent
    / "Tool_1_fetch_optical_imagery"
    / "test_runs"
    / "sample_optical_output.tif"
)

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.mark.skipif(not _SAMPLE_OPTICAL.is_file(), reason="sample fixture raster not present")
def test_render_geotiff_preview_returns_valid_png():
    png_bytes = render_geotiff_preview(str(_SAMPLE_OPTICAL), size=256)
    assert png_bytes.startswith(_PNG_MAGIC)
    assert len(png_bytes) > 0


def test_render_geotiff_preview_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        render_geotiff_preview("does/not/exist.tif")
