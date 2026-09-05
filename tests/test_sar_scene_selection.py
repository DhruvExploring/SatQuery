import sys

import pytest

if sys.platform == "win32":
    pytest.importorskip("pywintypes")

try:
    from Tool_3_fetch_sar_imagery.fetch_sar_imagery import (
        SARSatelliteRequest,
        select_best_sar_scene,
    )
except ImportError:
    pytest.skip("Tool 3 / FastMCP extras unavailable", allow_module_level=True)


def _scene(scene_id: str, when: str, orbit: str, pols=None) -> dict:
    return {
        "scene_id": scene_id,
        "acquisition_time": when,
        "orbit_direction": orbit,
        "polarization": pols or ["VV", "VH"],
        "instrument_mode": "IW",
    }


def test_select_does_not_substitute_descending_for_ascending():
    scenes = [
        _scene("desc-old", "2025-01-07T01:03:25Z", "DESCENDING"),
        _scene("desc-new", "2025-01-31T01:03:23Z", "DESCENDING"),
    ]
    req = SARSatelliteRequest(
        bbox=[72.8, 18.9, 73.0, 19.1],
        start_date="2025-01-01",
        end_date="2025-01-31",
        orbit_direction="ASCENDING",
        polarization=["VV"],
    )
    assert select_best_sar_scene(scenes, req) is None


def test_select_keeps_requested_orbit_when_available():
    scenes = [
        _scene("desc", "2025-01-31T01:03:23Z", "DESCENDING"),
        _scene("asc", "2025-01-20T13:00:00Z", "ASCENDING"),
    ]
    req = SARSatelliteRequest(
        bbox=[72.8, 18.9, 73.0, 19.1],
        start_date="2025-01-01",
        end_date="2025-01-31",
        orbit_direction="ASCENDING",
    )
    best = select_best_sar_scene(scenes, req)
    assert best is not None
    assert best["scene_id"] == "asc"
    assert best["orbit_direction"] == "ASCENDING"
