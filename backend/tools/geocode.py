"""Reverse geocoding: resolve a lat/long pair to a human-readable place name.

Backed by Tool 10's spatial_geocoding_poi engine (LocationIQ, falling back to
OpenStreetMap Nominatim).
"""
from __future__ import annotations

from typing import Any


def reverse_geocode(latitude: float, longitude: float) -> dict[str, Any]:
    """Resolve (latitude, longitude) to a place name.

    Returns {"place_name": str, "raw": dict} on success; raises on failure so
    the executor's generic error wrapping can report it.
    """
    from Tool_10_spatial_geocoding_poi.spatial_geocoding_poi import (
        reverse_geocode as _tool10_reverse_geocode,
    )

    result = _tool10_reverse_geocode(latitude, longitude)
    if result.get("status") != "success":
        raise RuntimeError(
            result.get("message") or "Reverse geocoding failed."
        )
    return {"place_name": result.get("display_name") or "Unknown location", "raw": result}
