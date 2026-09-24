"""fractional_bbox_to_wgs84 (Tool 11): converts a vision model's fractional
image-space bbox into an exact WGS84 bounding box via the GeoTIFF's own
affine transform -- the backend half of "tighten the VLM's box, then let
exact math (not the model) place it in the real world."
"""
from __future__ import annotations

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from Tool_11_deterministic_affine_markup.deterministic_affine_markup import (
    fractional_bbox_to_wgs84,
    polygon_pixels_to_wgs84,
)

MIN_LON, MIN_LAT, MAX_LON, MAX_LAT = 77.20, 28.62, 77.28, 28.68
WIDTH = HEIGHT = 512


@pytest.fixture
def north_up_geotiff(tmp_path):
    """A synthetic, unrotated WGS84 GeoTIFF with known bounds -- same fixture
    shape as Tool 11's own __main__ smoke test."""
    path = tmp_path / "delhi_test.tif"
    transform = from_bounds(MIN_LON, MIN_LAT, MAX_LON, MAX_LAT, WIDTH, HEIGHT)
    data = (np.random.rand(3, HEIGHT, WIDTH) * 255).astype(np.uint8)
    with rasterio.open(
        path, "w", driver="GTiff", height=HEIGHT, width=WIDTH, count=3,
        dtype="uint8", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data)
    return str(path)


def test_full_image_bbox_recovers_exact_bounds(north_up_geotiff):
    geo = fractional_bbox_to_wgs84(north_up_geotiff, (0.0, 0.0, 1.0, 1.0))
    assert geo["bbox_wgs84"] == pytest.approx([MIN_LON, MIN_LAT, MAX_LON, MAX_LAT], abs=1e-9)


def test_partial_bbox_maps_to_correct_sub_region(north_up_geotiff):
    """[0,0]=top-left, [1,1]=bottom-right -- row-fraction 0 is the image top,
    which is the raster's max latitude (north-up), not its min."""
    geo = fractional_bbox_to_wgs84(north_up_geotiff, (0.25, 0.25, 0.75, 0.75))

    lon_span = MAX_LON - MIN_LON
    lat_span = MAX_LAT - MIN_LAT
    expected_min_lon = MIN_LON + 0.25 * lon_span
    expected_max_lon = MIN_LON + 0.75 * lon_span
    expected_min_lat = MAX_LAT - 0.75 * lat_span
    expected_max_lat = MAX_LAT - 0.25 * lat_span

    assert geo["bbox_wgs84"] == pytest.approx(
        [expected_min_lon, expected_min_lat, expected_max_lon, expected_max_lat], abs=1e-9
    )
    corners = geo["corners_wgs84"]
    assert corners["top_left"]["latitude"] == pytest.approx(expected_max_lat, abs=1e-9)
    assert corners["bottom_right"]["latitude"] == pytest.approx(expected_min_lat, abs=1e-9)


def test_raises_for_raster_with_no_crs(tmp_path):
    path = tmp_path / "no_crs.tif"
    data = (np.random.rand(3, 64, 64) * 255).astype(np.uint8)
    with rasterio.open(
        path, "w", driver="GTiff", height=64, width=64, count=3, dtype="uint8",
    ) as dst:
        dst.write(data)

    with pytest.raises(ValueError, match="no CRS"):
        fractional_bbox_to_wgs84(str(path), (0.0, 0.0, 1.0, 1.0))


def test_polygon_diagonal_path_envelope_and_centroid(north_up_geotiff):
    """A diagonal path (e.g. a river's course) from top-left to bottom-right:
    its envelope should be the full image (same as a loose bbox would give),
    but its own vertices -- and their centroid -- should trace the diagonal,
    not the envelope's unrelated center."""
    diagonal = [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)]
    geo = polygon_pixels_to_wgs84(north_up_geotiff, diagonal)

    assert geo["bbox_wgs84"] == pytest.approx([MIN_LON, MIN_LAT, MAX_LON, MAX_LAT], abs=1e-9)
    assert len(geo["polygon_wgs84"]) == 3
    assert geo["polygon_wgs84"][0] == pytest.approx(
        {"latitude": MAX_LAT, "longitude": MIN_LON}, abs=1e-9
    )
    assert geo["polygon_wgs84"][2] == pytest.approx(
        {"latitude": MIN_LAT, "longitude": MAX_LON}, abs=1e-9
    )
    # The path's own centroid: the mean of its three vertices, which for
    # this diagonal happens to equal the midpoint -- but derived from the
    # vertices themselves, not the envelope's own min/max.
    mid_lon = (MIN_LON + MAX_LON) / 2.0
    mid_lat = (MIN_LAT + MAX_LAT) / 2.0
    assert geo["centroid_wgs84"] == pytest.approx({"latitude": mid_lat, "longitude": mid_lon}, abs=1e-9)


def test_polygon_off_center_path_centroid_differs_from_envelope_midpoint(north_up_geotiff):
    """A path confined to one corner: its centroid should stay near that
    corner, not drift to the (much farther) envelope midpoint -- this is
    the concrete fix for a bbox's own center landing nowhere near an
    elongated feature's actual path."""
    corner_path = [(0.0, 0.0), (0.1, 0.05), (0.2, 0.0)]
    geo = polygon_pixels_to_wgs84(north_up_geotiff, corner_path)

    envelope_mid_lat = (MIN_LAT + MAX_LAT) / 2.0
    centroid = geo["centroid_wgs84"]
    # Near the top-left corner (max_lat, min_lon), not the envelope's middle.
    assert centroid["latitude"] > envelope_mid_lat
    assert abs(centroid["latitude"] - MAX_LAT) < abs(centroid["latitude"] - envelope_mid_lat)


def test_polygon_requires_at_least_three_vertices(north_up_geotiff):
    with pytest.raises(ValueError, match="at least 3"):
        polygon_pixels_to_wgs84(north_up_geotiff, [(0.0, 0.0), (1.0, 1.0)])


def test_polygon_raises_for_raster_with_no_crs(tmp_path):
    path = tmp_path / "no_crs.tif"
    data = (np.random.rand(3, 64, 64) * 255).astype(np.uint8)
    with rasterio.open(
        path, "w", driver="GTiff", height=64, width=64, count=3, dtype="uint8",
    ) as dst:
        dst.write(data)

    with pytest.raises(ValueError, match="no CRS"):
        polygon_pixels_to_wgs84(str(path), [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)])
