"""Tool 10: spatial_geocoding_poi (Spatial Geocoding & POI Discovery Engine)

Bridges the gap between raw GeoTIFF bounding boxes and human-readable geography.
Provides deterministic, georeferenced spatial identity and in-AOI landmark discovery:
  1. Forward Geocoding: Place Name -> Exact Lat/Lon + Viewbox Clamping.
  2. Reverse Geocoding: Lat/Lon -> Hierarchical Structured Address.
  3. Scene Identity Resolver: Bounding Box / GeoTIFF -> Centroid + Multi-zoom regional identity.
  4. In-AOI POI Discovery: BBox -> Overpass QL extraction of tourism, historic, natural & infrastructure POIs.

Provider Resiliency Chain:
  - Geocoding: LocationIQ API (Primary, 5,000 req/day) -> OSM Nominatim (Polite Fallback).
  - POI Discovery: Overpass QL Multi-Mirror Endpoints -> LocationIQ Category Fallback.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator

# Ensure project root is on sys.path and load environment variables
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

load_dotenv(ROOT_DIR / ".env")

logger = logging.getLogger("satquery.tool10_spatial_geocoding_poi")

try:
    from fastmcp import FastMCP
except (ImportError, Exception):
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        FastMCP = None


# =============================================================================
# 1. Configuration & Constants
# =============================================================================

@dataclass(frozen=True)
class GeocodingConfig:
    locationiq_base_url: str = "https://us1.locationiq.com/v1"
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    overpass_endpoints: tuple[str, ...] = (
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://lz4.overpass-api.de/api/interpreter",
    )
    user_agent: str = "SatQuery-GeospatialAgent/1.0 (https://github.com/SatQuery; satquery@earthobservatory.local)"
    http_timeout_s: float = 12.0
    nominatim_min_interval_s: float = 1.0


CONFIG = GeocodingConfig()
_LAST_NOMINATIM_CALL_TS = 0.0


# =============================================================================
# 2. Pydantic Request Models
# =============================================================================

class SpatialGeocodingRequest(BaseModel):
    """Input parameters for Tool 10: Spatial Geocoding & POI Discovery."""

    mode: Literal["forward", "reverse", "scene_identity", "poi_discovery", "auto"] = Field(
        default="auto",
        description=(
            "Operation mode: 'forward' (name to coords), 'reverse' (coords to address), "
            "'scene_identity' (bbox to regional summary), 'poi_discovery' (bbox to landmark list), "
            "or 'auto' (inferred from parameters)."
        ),
    )
    query: Optional[str] = Field(
        default=None,
        description="Place name, landmark, address, or search term (required for 'forward').",
    )
    landmark_names: Optional[list[str]] = Field(
        default=None,
        description=(
            "For 'scene_identity': the specific landmark name(s) to forward-geocode and "
            "check against the scene bbox -- already extracted by the caller from the "
            "user's question (this tool does not parse `query` for landmark names itself)."
        ),
    )
    latitude: Optional[float] = Field(
        default=None,
        ge=-90.0,
        le=90.0,
        description="Latitude in WGS84 decimal degrees (required for 'reverse').",
    )
    longitude: Optional[float] = Field(
        default=None,
        ge=-180.0,
        le=180.0,
        description="Longitude in WGS84 decimal degrees (required for 'reverse').",
    )
    bbox: Optional[list[float]] = Field(
        default=None,
        description="Bounding box in WGS84: [min_lon, min_lat, max_lon, max_lat] (required for 'scene_identity'/'poi_discovery').",
    )
    geotiff_path: Optional[str] = Field(
        default=None,
        description="Optional path to local GeoTIFF file from which to extract spatial bounds and CRS automatically.",
    )
    poi_categories: Optional[list[str]] = Field(
        default=None,
        description="List of POI categories to discover: 'tourism', 'historic', 'amenity', 'natural', 'infrastructure'. Default: all.",
    )
    max_results: int = Field(
        default=15,
        ge=1,
        le=50,
        description="Maximum number of POIs or geocoding candidates to return.",
    )
    zoom: Optional[int] = Field(
        default=None,
        ge=1,
        le=18,
        description="Reverse geocoding zoom level (e.g. 8=State, 10=District/City, 14=Suburb/Locality, 18=Building).",
    )
    viewbox_clamping: bool = Field(
        default=True,
        description="If True and bbox is provided, strictly prioritize/clamp forward searches within the bbox extent.",
    )

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, v: Optional[list[float]]) -> Optional[list[float]]:
        if v is None:
            return v
        if len(v) != 4:
            raise ValueError(f"bbox must have exactly 4 floats [min_lon, min_lat, max_lon, max_lat], got {len(v)}")
        min_lon, min_lat, max_lon, max_lat = v
        if not (-180.0 <= min_lon <= 180.0 and -180.0 <= max_lon <= 180.0):
            raise ValueError(f"Longitudes must be in range [-180, 180], got {min_lon}, {max_lon}")
        if not (-90.0 <= min_lat <= 90.0 and -90.0 <= max_lat <= 90.0):
            raise ValueError(f"Latitudes must be in range [-90, 90], got {min_lat}, {max_lat}")
        if min_lon > max_lon:
            raise ValueError(f"min_lon ({min_lon}) cannot exceed max_lon ({max_lon})")
        if min_lat > max_lat:
            raise ValueError(f"min_lat ({min_lat}) cannot exceed max_lat ({max_lat})")
        return v

    @model_validator(mode="after")
    def infer_and_validate_mode(self) -> SpatialGeocodingRequest:
        # Extract bbox from GeoTIFF if geotiff_path is given and bbox is missing
        if self.geotiff_path and not self.bbox:
            extracted_bbox = _extract_wgs84_bbox_from_geotiff(self.geotiff_path)
            if extracted_bbox:
                self.bbox = extracted_bbox

        if self.mode == "auto":
            if self.query and not self.latitude and not self.bbox:
                self.mode = "forward"
            elif self.latitude is not None and self.longitude is not None and not self.query:
                self.mode = "reverse"
            elif self.bbox and self.poi_categories is not None:
                self.mode = "poi_discovery"
            elif self.bbox:
                self.mode = "scene_identity"
            elif self.query:
                self.mode = "forward"
            else:
                raise ValueError("Could not automatically infer mode. Please specify query, coords, or bbox.")

        # Specific mode validations
        if self.mode == "forward" and not self.query:
            raise ValueError("Mode 'forward' requires a non-empty 'query' string.")
        if self.mode == "reverse" and (self.latitude is None or self.longitude is None):
            raise ValueError("Mode 'reverse' requires both 'latitude' and 'longitude'.")
        if self.mode in ("scene_identity", "poi_discovery") and not self.bbox:
            raise ValueError(f"Mode '{self.mode}' requires 'bbox' or a valid 'geotiff_path'.")

        return self


# =============================================================================
# 3. GeoTIFF BBox & Helper Extractors
# =============================================================================

def _extract_wgs84_bbox_from_geotiff(geotiff_path: str) -> Optional[list[float]]:
    """Extracts reprojected WGS84 bounding box [min_lon, min_lat, max_lon, max_lat] from a GeoTIFF."""
    try:
        import rasterio
        from rasterio.warp import transform_bounds
        p = Path(geotiff_path).resolve()
        if not p.exists() or not p.is_file():
            return None
        with rasterio.open(p) as src:
            if src.crs is None:
                return None
            bounds = src.bounds
            if src.crs.to_epsg() == 4326:
                return [round(bounds.left, 6), round(bounds.bottom, 6), round(bounds.right, 6), round(bounds.top, 6)]
            wgs84_bounds = transform_bounds(src.crs, "EPSG:4326", bounds.left, bounds.bottom, bounds.right, bounds.top)
            return [round(wgs84_bounds[0], 6), round(wgs84_bounds[1], 6), round(wgs84_bounds[2], 6), round(wgs84_bounds[3], 6)]
    except Exception as exc:
        logger.warning(f"Failed to extract bounds from GeoTIFF {geotiff_path}: {exc}")
        return None


def _rate_limit_nominatim() -> None:
    """Enforce OSM Nominatim polite rate limit (max 1 request per second)."""
    global _LAST_NOMINATIM_CALL_TS
    now = time.time()
    elapsed = now - _LAST_NOMINATIM_CALL_TS
    if elapsed < CONFIG.nominatim_min_interval_s:
        time.sleep(CONFIG.nominatim_min_interval_s - elapsed)
    _LAST_NOMINATIM_CALL_TS = time.time()


def _haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two points on Earth in kilometers."""
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2.0) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def _get_cardinal_direction(lat_from: float, lon_from: float, lat_to: float, lon_to: float) -> str:
    """Computes cardinal/intercardinal direction from one coordinate to another."""
    dlat = lat_to - lat_from
    dlon = lon_to - lon_from
    ns = "North" if dlat > 0.05 else ("South" if dlat < -0.05 else "")
    ew = "East" if dlon > 0.05 else ("West" if dlon < -0.05 else "")
    if ns and ew:
        return f"{ns}-{ew}"
    return ns or ew or "nearby"


def _is_valid_landmark_candidate(cand: dict[str, Any]) -> bool:
    """Filters out low-importance commercial noise (e.g. shops, local restaurants)
    when searching for a landmark by an already-decided name (landmark_names, see
    resolve_scene_identity) -- purely on the geocoder's own structured result
    metadata (class/type/importance), never on the user's original wording:
    deciding *which* name to search for is the caller's job, not this filter's.
    """
    osm_class = str(cand.get("class") or "").lower()
    osm_type = str(cand.get("type") or "").lower()
    importance = float(cand.get("importance") or 0.0)

    # Commercial noise classes
    noise_classes = {"amenity", "shop", "office", "commercial", "craft", "leisure"}

    # Valid cultural/heritage types even if under amenity
    valid_heritage_types = {
        "place_of_worship", "monastery", "theatre", "museum", "arts_centre", "attraction",
        "monument", "castle", "fort", "memorial", "tomb", "temple", "mosque", "church", "ruins"
    }

    if osm_class in noise_classes:
        if osm_type in valid_heritage_types or importance >= 0.55:
            return True
        # Discard low-importance local shops/restaurants that share a name with a famous landmark
        return False

    return True


# =============================================================================
# 4. Forward Geocoding Engine
# =============================================================================

def forward_geocode(
    query: str,
    bbox: Optional[list[float]] = None,
    viewbox_clamping: bool = True,
    max_results: int = 5,
) -> Dict[str, Any]:
    """Resolves a place name to geographic coordinates and bounding box.

    `query` is expected to already be a clean place/feature name (e.g. "Yamuna
    River"), not a full natural-language sentence -- the caller (the LLM
    planner, see registry.py's trusted_args_for_tool for
    geocode_place_to_coordinates) is responsible for extracting that from the
    user's actual question. This function does no interpretation of its own
    beyond whitespace trimming.
    """
    locationiq_key = os.getenv("LOCATIONIQ_API_KEY", "").strip()
    errors: list[str] = []

    clean_q = query.strip()

    # 1. Try LocationIQ (Primary)
    if locationiq_key:
        try:
            params: dict[str, Any] = {
                "key": locationiq_key,
                "q": clean_q,
                "format": "json",
                "limit": max_results,
                "addressdetails": 1,
            }
            if bbox and viewbox_clamping:
                # LocationIQ viewbox format: min_lon,max_lat,max_lon,min_lat
                params["viewbox"] = f"{bbox[0]},{bbox[3]},{bbox[2]},{bbox[1]}"
                params["bounded"] = 1

            resp = requests.get(
                f"{CONFIG.locationiq_base_url}/search.php",
                params=params,
                headers={"User-Agent": CONFIG.user_agent},
                timeout=CONFIG.http_timeout_s,
            )
            if resp.status_code == 200:
                raw_results = resp.json()
                if isinstance(raw_results, list) and len(raw_results) > 0:
                    candidates = []
                    for item in raw_results:
                        candidates.append(_format_geocoding_candidate(item, provider="locationiq"))
                    return {
                        "provider": "locationiq",
                        "status": "success",
                        "query": query,
                        "candidates_count": len(candidates),
                        "candidates": candidates,
                        "best_match": candidates[0],
                    }
            elif resp.status_code == 404:
                # No matches found within bounded viewbox; retry without bounded clamping
                if bbox and viewbox_clamping:
                    params.pop("bounded", None)
                    resp_unbounded = requests.get(
                        f"{CONFIG.locationiq_base_url}/search.php",
                        params=params,
                        headers={"User-Agent": CONFIG.user_agent},
                        timeout=CONFIG.http_timeout_s,
                    )
                    if resp_unbounded.status_code == 200:
                        raw_results = resp_unbounded.json()
                        if isinstance(raw_results, list) and len(raw_results) > 0:
                            candidates = [_format_geocoding_candidate(it, provider="locationiq") for it in raw_results]
                            return {
                                "provider": "locationiq (unbounded)",
                                "status": "success",
                                "query": query,
                                "candidates_count": len(candidates),
                                "candidates": candidates,
                                "best_match": candidates[0],
                            }
            errors.append(f"LocationIQ status {resp.status_code}: {resp.text[:120]}")
        except Exception as exc:
            errors.append(f"LocationIQ request error: {exc}")

    # 2. Fallback to OpenStreetMap Nominatim
    try:
        _rate_limit_nominatim()
        nom_params: dict[str, Any] = {
            "q": clean_q,
            "format": "jsonv2",
            "limit": max_results,
            "addressdetails": 1,
        }
        if bbox and viewbox_clamping:
            nom_params["viewbox"] = f"{bbox[0]},{bbox[3]},{bbox[2]},{bbox[1]}"
            nom_params["bounded"] = 1

        nom_resp = requests.get(
            f"{CONFIG.nominatim_base_url}/search",
            params=nom_params,
            headers={"User-Agent": CONFIG.user_agent},
            timeout=CONFIG.http_timeout_s,
        )
        if nom_resp.status_code == 200:
            nom_results = nom_resp.json()
            if isinstance(nom_results, list) and len(nom_results) > 0:
                candidates = [_format_geocoding_candidate(it, provider="nominatim") for it in nom_results]
                return {
                    "provider": "nominatim",
                    "status": "success",
                    "query": query,
                    "candidates_count": len(candidates),
                    "candidates": candidates,
                    "best_match": candidates[0],
                }
    except Exception as exc:
        errors.append(f"Nominatim fallback error: {exc}")

    return {
        "status": "error",
        "query": query,
        "message": f"No geocoding matches found for '{query}'.",
        "errors": errors,
    }


# =============================================================================
# 5. Reverse Geocoding Engine
# =============================================================================

def reverse_geocode(
    latitude: float,
    longitude: float,
    zoom: Optional[int] = None,
) -> Dict[str, Any]:
    """Resolves coordinates to structured human-readable address hierarchy."""
    locationiq_key = os.getenv("LOCATIONIQ_API_KEY", "").strip()
    errors: list[str] = []

    # 1. Try LocationIQ (Primary)
    if locationiq_key:
        try:
            params: dict[str, Any] = {
                "key": locationiq_key,
                "lat": latitude,
                "lon": longitude,
                "format": "json",
                "addressdetails": 1,
            }
            if zoom is not None:
                params["zoom"] = zoom

            resp = requests.get(
                f"{CONFIG.locationiq_base_url}/reverse.php",
                params=params,
                headers={"User-Agent": CONFIG.user_agent},
                timeout=CONFIG.http_timeout_s,
            )
            if resp.status_code == 200:
                data = resp.json()
                return _format_reverse_response(data, provider="locationiq", lat=latitude, lon=longitude)
            errors.append(f"LocationIQ reverse status {resp.status_code}: {resp.text[:120]}")
        except Exception as exc:
            errors.append(f"LocationIQ reverse error: {exc}")

    # 2. Fallback to OpenStreetMap Nominatim
    try:
        _rate_limit_nominatim()
        nom_params: dict[str, Any] = {
            "lat": latitude,
            "lon": longitude,
            "format": "jsonv2",
            "addressdetails": 1,
        }
        if zoom is not None:
            nom_params["zoom"] = zoom

        nom_resp = requests.get(
            f"{CONFIG.nominatim_base_url}/reverse",
            params=nom_params,
            headers={"User-Agent": CONFIG.user_agent},
            timeout=CONFIG.http_timeout_s,
        )
        if nom_resp.status_code == 200:
            nom_data = nom_resp.json()
            return _format_reverse_response(nom_data, provider="nominatim", lat=latitude, lon=longitude)
    except Exception as exc:
        errors.append(f"Nominatim reverse error: {exc}")

    return {
        "status": "error",
        "latitude": latitude,
        "longitude": longitude,
        "message": f"Could not reverse geocode coordinates ({latitude}, {longitude}).",
        "errors": errors,
    }


# =============================================================================
# 6. Scene Identity Resolver (BBox Centroid & Hierarchical Levels)
# =============================================================================

def resolve_scene_identity(
    bbox: list[float],
    query: Optional[str] = None,
    landmark_names: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Calculates BBox centroid and executes hierarchical reverse geocoding to synthesize place identity,
    and forwards-geocodes each of `landmark_names` (the specific landmarks the caller -- the LLM
    planner, having already read the user's question -- has decided the query refers to; this
    function does no interpretation of `query` itself, which is accepted only for context/logging).
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    centroid_lat = round((min_lat + max_lat) / 2.0, 6)
    centroid_lon = round((min_lon + max_lon) / 2.0, 6)

    # Hierarchical lookups:
    # zoom 8: State / Regional extent
    # zoom 10: District / Metropolitan City extent
    # zoom 14: Suburb / Locality extent
    state_level = reverse_geocode(centroid_lat, centroid_lon, zoom=8)
    district_level = reverse_geocode(centroid_lat, centroid_lon, zoom=10)
    suburb_level = reverse_geocode(centroid_lat, centroid_lon, zoom=14)

    # Extract clean address components
    suburb_addr = suburb_level.get("address", {}) if suburb_level.get("status") == "success" else {}
    dist_addr = district_level.get("address", {}) if district_level.get("status") == "success" else {}
    state_addr = state_level.get("address", {}) if state_level.get("status") == "success" else {}

    place_name = (
        suburb_addr.get("suburb")
        or suburb_addr.get("neighbourhood")
        or suburb_addr.get("city_district")
        or suburb_addr.get("village")
        or suburb_addr.get("town")
        or dist_addr.get("city")
        or dist_addr.get("state_district")
        or dist_addr.get("district")
        or dist_addr.get("county")
        or "Unknown Region"
    )
    city = (
        suburb_addr.get("city")
        or suburb_addr.get("town")
        or suburb_addr.get("municipality")
        or dist_addr.get("city")
        or dist_addr.get("town")
        or dist_addr.get("municipality")
        or dist_addr.get("state_district")
        or dist_addr.get("district")
        or dist_addr.get("county")
        or state_addr.get("state")
        or ""
    )
    state = state_addr.get("state") or dist_addr.get("state") or suburb_addr.get("state") or ""
    country = state_addr.get("country") or dist_addr.get("country") or suburb_addr.get("country") or ""

    # Synthesize concise human-readable factual description
    parts = [p for p in (place_name, city, state, country) if p]
    distinct_parts: list[str] = []
    for p in parts:
        if p not in distinct_parts:
            distinct_parts.append(p)
    geographic_identity = ", ".join(distinct_parts)

    narrative_summary = (
        f"This satellite raster covers {geographic_identity} centered at coordinates "
        f"({centroid_lat}°N, {centroid_lon}°E)."
    )

    response_dict: dict[str, Any] = {
        "status": "success",
        "bbox": bbox,
        "centroid": {
            "latitude": centroid_lat,
            "longitude": centroid_lon,
        },
        "geographic_identity": geographic_identity,
        "narrative_summary": narrative_summary,
        "hierarchy": {
            "locality": place_name,
            "city": city,
            "state": state,
            "country": country,
        },
        "full_display_name": suburb_level.get("display_name") or district_level.get("display_name"),
        "landmarks": [],
        "boundary_audits": [],
        "candidates": [],
    }

    # For each caller-supplied landmark name, resolve via Two-Tier Geocoding Strategy:
    # Tier 1: Global Unbounded Search to find the true canonical landmark and coordinates.
    # Tier 2: Check raster BBox containment. If inside -> mark valid. If outside -> emit Spatial Boundary Audit (rejecting local homonyms/shops).
    landmark_names = landmark_names or []
    landmarks_found: list[dict[str, Any]] = []
    boundary_audits: list[dict[str, Any]] = []

    for name in landmark_names:
        logger.info("[SPATIAL GEOCODING] Resolving landmark: %r (Two-Tier Strategy)", name)
        
        # 1. Global Unbounded Forward Geocode
        fwd_glob = forward_geocode(name, bbox=None, viewbox_clamping=False)
        glob_candidates = fwd_glob.get("candidates", []) if fwd_glob.get("status") == "success" else []
        valid_glob_candidates = [c for c in glob_candidates if _is_valid_landmark_candidate(c)]

        canonical = valid_glob_candidates[0] if valid_glob_candidates else (fwd_glob.get("best_match") if fwd_glob.get("status") == "success" else None)

        if canonical:
            c_lat = float(canonical["latitude"])
            c_lon = float(canonical["longitude"])
            is_inside = (min_lon <= c_lon <= max_lon) and (min_lat <= c_lat <= max_lat)

            if is_inside:
                # Landmark is genuinely inside the scene bounds
                landmarks_found.append({
                    "name": name,
                    "display_name": canonical.get("display_name"),
                    "latitude": c_lat,
                    "longitude": c_lon,
                    "best_match": canonical,
                    "inside_aoi": True,
                })
                response_dict["narrative_summary"] += (
                    f" Located landmark '{name}' at ({c_lat:.4f}°N, {c_lon:.4f}°E)."
                )
            else:
                # Canonical landmark is OUTSIDE the scene bounds
                dist_km = _haversine_distance_km(centroid_lat, centroid_lon, c_lat, c_lon)
                dir_str = _get_cardinal_direction(centroid_lat, centroid_lon, c_lat, c_lon)
                audit_entry = {
                    "landmark": name,
                    "status": "outside_bounds",
                    "canonical_name": canonical.get("display_name"),
                    "coordinates": [c_lat, c_lon],
                    "raster_bbox": bbox,
                    "distance_km": round(dist_km, 1),
                    "direction": dir_str,
                    "verdict": (
                        f"The canonical landmark '{name}' ({canonical.get('display_name')}) is located at ({c_lat:.4f}°N, {c_lon:.4f}°E), "
                        f"which lies ~{round(dist_km)} km {dir_str} outside the raster boundary [{bbox[0]}°E, {bbox[1]}°N to {bbox[2]}°E, {bbox[3]}°N]."
                    ),
                }
                boundary_audits.append(audit_entry)
                response_dict["narrative_summary"] += f" {audit_entry['verdict']}"
        else:
            # Fallback: In-AOI Search with Strict Entity Type Filtering
            fwd_local = forward_geocode(name, bbox=bbox, viewbox_clamping=True)
            local_candidates = fwd_local.get("candidates", []) if fwd_local.get("status") == "success" else []
            valid_local_candidates = [c for c in local_candidates if _is_valid_landmark_candidate(c)]

            if valid_local_candidates:
                best_local = valid_local_candidates[0]
                l_lat = float(best_local["latitude"])
                l_lon = float(best_local["longitude"])
                landmarks_found.append({
                    "name": name,
                    "display_name": best_local.get("display_name"),
                    "latitude": l_lat,
                    "longitude": l_lon,
                    "best_match": best_local,
                    "inside_aoi": True,
                })
                response_dict["narrative_summary"] += (
                    f" Located landmark '{name}' at ({l_lat:.4f}°N, {l_lon:.4f}°E)."
                )
            else:
                audit_entry = {
                    "landmark": name,
                    "status": "not_found",
                    "raster_bbox": bbox,
                    "verdict": f"No geocoding matches found for landmark '{name}' in OpenStreetMap within or near this region.",
                }
                boundary_audits.append(audit_entry)
                response_dict["narrative_summary"] += f" {audit_entry['verdict']}"

    response_dict["landmarks"] = landmarks_found
    response_dict["boundary_audits"] = boundary_audits

    if landmarks_found:
        response_dict["best_match"] = landmarks_found[0]["best_match"]
        response_dict["candidates"] = [l["best_match"] for l in landmarks_found]

    return response_dict


# =============================================================================
# 7. In-AOI POI Discovery Engine (Overpass QL with Fallback)
# =============================================================================

def discover_in_aoi_pois(
    bbox: list[float],
    categories: Optional[list[str]] = None,
    max_results: int = 20,
) -> Dict[str, Any]:
    """Queries Overpass API for tourism, historic, natural & infrastructure POIs strictly inside the BBox."""
    min_lon, min_lat, max_lon, max_lat = bbox
    # Overpass bounding box order: (south, west, north, east) -> (min_lat, min_lon, max_lat, max_lon)
    south, west, north, east = min_lat, min_lon, max_lat, max_lon

    cats = set(categories) if categories else {"tourism", "historic", "amenity", "natural", "infrastructure"}

    # Build Overpass QL query fragments
    query_parts: list[str] = []
    if "tourism" in cats:
        query_parts.append(f'node["tourism"~"attraction|museum|viewpoint|zoo|theme_park|monument|gallery"]({south},{west},{north},{east});')
        query_parts.append(f'way["tourism"~"attraction|museum|viewpoint|zoo|theme_park|monument|gallery"]({south},{west},{north},{east});')
    if "historic" in cats:
        query_parts.append(f'node["historic"~"monument|memorial|castle|fort|ruins|archaeological_site|heritage"]({south},{west},{north},{east});')
        query_parts.append(f'way["historic"~"monument|memorial|castle|fort|ruins|archaeological_site|heritage"]({south},{west},{north},{east});')
    if "amenity" in cats:
        query_parts.append(f'node["amenity"~"place_of_worship|hospital|university|theatre|courthouse"]({south},{west},{north},{east});')
        query_parts.append(f'way["amenity"~"place_of_worship|hospital|university|theatre|courthouse"]({south},{west},{north},{east});')
    if "natural" in cats:
        query_parts.append(f'node["natural"~"water|wood|peak|wetland|bay|beach"]({south},{west},{north},{east});')
        query_parts.append(f'way["natural"~"water|wood|peak|wetland|bay|beach"]({south},{west},{north},{east});')
    if "infrastructure" in cats:
        query_parts.append(f'node["aeroway"~"aerodrome|terminal"]({south},{west},{north},{east});')
        query_parts.append(f'node["railway"~"station|junction"]({south},{west},{north},{east});')
        query_parts.append(f'way["bridge"="yes"]["name"]({south},{west},{north},{east});')

    if not query_parts:
        query_parts.append(f'node["tourism"]({south},{west},{north},{east});')
        query_parts.append(f'node["historic"]({south},{west},{north},{east});')

    overpass_ql = f"[out:json][timeout:20];(\n  " + "\n  ".join(query_parts) + f"\n);\nout center {max_results * 2};"

    errors: list[str] = []
    for endpoint in CONFIG.overpass_endpoints:
        try:
            resp = requests.post(
                endpoint,
                data={"data": overpass_ql},
                headers={"User-Agent": CONFIG.user_agent},
                timeout=CONFIG.http_timeout_s,
            )
            if resp.status_code == 200:
                data = resp.json()
                elements = data.get("elements", [])
                pois = _parse_overpass_elements(elements, bbox=bbox, max_results=max_results)
                return {
                    "status": "success",
                    "provider": f"overpass ({endpoint})",
                    "bbox": bbox,
                    "categories_requested": list(cats),
                    "poi_count": len(pois),
                    "pois": pois,
                }
            errors.append(f"Overpass mirror {endpoint} status {resp.status_code}")
        except Exception as exc:
            errors.append(f"Overpass mirror {endpoint} error: {exc}")

    # Fallback to LocationIQ nearby/POI search if Overpass fails
    locationiq_key = os.getenv("LOCATIONIQ_API_KEY", "").strip()
    if locationiq_key:
        try:
            centroid_lat = (min_lat + max_lat) / 2.0
            centroid_lon = (min_lon + max_lon) / 2.0
            iq_resp = requests.get(
                f"{CONFIG.locationiq_base_url}/nearby.php",
                params={
                    "key": locationiq_key,
                    "lat": centroid_lat,
                    "lon": centroid_lon,
                    "tag": "tourism:attraction,historic:monument",
                    "radius": 10000,
                    "format": "json",
                },
                headers={"User-Agent": CONFIG.user_agent},
                timeout=CONFIG.http_timeout_s,
            )
            if iq_resp.status_code == 200:
                raw_pois = iq_resp.json()
                if isinstance(raw_pois, list) and len(raw_pois) > 0:
                    fallback_pois = []
                    for item in raw_pois[:max_results]:
                        p_lat = float(item.get("lat", 0.0))
                        p_lon = float(item.get("lon", 0.0))
                        inside = (min_lon <= p_lon <= max_lon) and (min_lat <= p_lat <= max_lat)
                        fallback_pois.append({
                            "name": item.get("display_name", "").split(",")[0] or item.get("name", "Unnamed POI"),
                            "category": item.get("type", "landmark"),
                            "type": item.get("class", "poi"),
                            "latitude": round(p_lat, 6),
                            "longitude": round(p_lon, 6),
                            "inside_aoi": inside,
                            "osm_id": item.get("osm_id"),
                        })
                    return {
                        "status": "success",
                        "provider": "locationiq (fallback)",
                        "bbox": bbox,
                        "categories_requested": list(cats),
                        "poi_count": len(fallback_pois),
                        "pois": fallback_pois,
                    }
        except Exception as exc:
            errors.append(f"LocationIQ POI fallback error: {exc}")

    # Fallback to Nominatim search within bounding box if Overpass and LocationIQ fail
    try:
        _rate_limit_nominatim()
        nom_pois: list[dict[str, Any]] = []
        for cat in list(cats)[:2]:
            nom_resp = requests.get(
                f"{CONFIG.nominatim_base_url}/search",
                params={
                    "q": cat,
                    "viewbox": f"{bbox[0]},{bbox[3]},{bbox[2]},{bbox[1]}",
                    "bounded": 1,
                    "format": "jsonv2",
                    "limit": max_results,
                    "addressdetails": 1,
                },
                headers={"User-Agent": CONFIG.user_agent},
                timeout=CONFIG.http_timeout_s,
            )
            if nom_resp.status_code == 200:
                raw_nom = nom_resp.json()
                if isinstance(raw_nom, list) and len(raw_nom) > 0:
                    for item in raw_nom:
                        p_lat = float(item.get("lat", 0.0))
                        p_lon = float(item.get("lon", 0.0))
                        inside = (min_lon <= p_lon <= max_lon) and (min_lat <= p_lat <= max_lat)
                        nom_pois.append({
                            "name": item.get("display_name", "").split(",")[0] or item.get("name", "Unnamed POI"),
                            "category": item.get("type", "landmark"),
                            "type": item.get("class", "poi"),
                            "latitude": round(p_lat, 6),
                            "longitude": round(p_lon, 6),
                            "inside_aoi": inside,
                            "osm_id": f"{item.get('osm_type', 'node')}/{item.get('osm_id')}",
                        })
        if nom_pois:
            return {
                "status": "success",
                "provider": "nominatim (fallback)",
                "bbox": bbox,
                "categories_requested": list(cats),
                "poi_count": len(nom_pois[:max_results]),
                "pois": nom_pois[:max_results],
            }
    except Exception as exc:
        errors.append(f"Nominatim POI fallback error: {exc}")

    return {
        "status": "error",
        "bbox": bbox,
        "message": "Failed to retrieve POIs from all Overpass, LocationIQ, and Nominatim endpoints.",
        "errors": errors,
    }


def _parse_overpass_elements(
    elements: list[dict[str, Any]],
    bbox: list[float],
    max_results: int,
) -> list[dict[str, Any]]:
    min_lon, min_lat, max_lon, max_lat = bbox
    pois: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:en") or tags.get("official_name")
        if not name or name in seen_names:
            continue

        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue

        lat, lon = float(lat), float(lon)
        # Strict BBox bounds guardrail
        inside_aoi = (min_lon <= lon <= max_lon) and (min_lat <= lat <= max_lat)
        if not inside_aoi:
            continue

        category = (
            tags.get("tourism")
            or tags.get("historic")
            or tags.get("amenity")
            or tags.get("natural")
            or tags.get("aeroway")
            or tags.get("railway")
            or "landmark"
        )
        subtype = tags.get("amenity") or tags.get("heritage") or tags.get("building") or category

        seen_names.add(name)
        pois.append({
            "name": name,
            "category": category,
            "type": subtype,
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "inside_aoi": True,
            "osm_id": f"{el.get('type', 'node')}/{el.get('id')}",
            "tags": {k: v for k, v in tags.items() if k in ("wikidata", "wikipedia", "historic", "tourism", "amenity")},
        })

        if len(pois) >= max_results:
            break

    return pois


# =============================================================================
# 8. Formatting Helpers
# =============================================================================

def _format_geocoding_candidate(item: dict[str, Any], provider: str) -> dict[str, Any]:
    lat = float(item.get("lat", 0.0))
    lon = float(item.get("lon", 0.0))
    raw_bbox = item.get("boundingbox")
    formatted_bbox = None
    if raw_bbox and len(raw_bbox) == 4:
        try:
            formatted_bbox = [
                round(float(raw_bbox[2]), 6),
                round(float(raw_bbox[0]), 6),
                round(float(raw_bbox[3]), 6),
                round(float(raw_bbox[1]), 6),
            ]
        except (ValueError, TypeError):
            formatted_bbox = None

    addr = item.get("address", {})
    return {
        "name": item.get("display_name", "").split(",")[0] or item.get("name", "Unknown"),
        "display_name": item.get("display_name", ""),
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "bounding_box_wgs84": formatted_bbox,
        "type": item.get("type"),
        "class": item.get("class"),
        "importance": round(float(item.get("importance", 0.0)), 4) if item.get("importance") else None,
        "address": {
            "road": addr.get("road"),
            "suburb": addr.get("suburb") or addr.get("neighbourhood"),
            "city": addr.get("city") or addr.get("town") or addr.get("municipality"),
            "district": addr.get("state_district") or addr.get("county"),
            "state": addr.get("state"),
            "country": addr.get("country"),
            "postcode": addr.get("postcode"),
        },
        "osm_id": f"{item.get('osm_type', 'node')}/{item.get('osm_id')}",
        "provider": provider,
    }


def _format_reverse_response(
    data: dict[str, Any],
    provider: str,
    lat: float,
    lon: float,
) -> dict[str, Any]:
    addr = data.get("address", {})
    display_name = data.get("display_name", "")
    return {
        "status": "success",
        "provider": provider,
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "display_name": display_name,
        "address": {
            "house_number": addr.get("house_number"),
            "road": addr.get("road"),
            "neighbourhood": addr.get("neighbourhood"),
            "suburb": addr.get("suburb"),
            "village": addr.get("village"),
            "hamlet": addr.get("hamlet"),
            "city": addr.get("city") or addr.get("town") or addr.get("municipality") or addr.get("village"),
            "county": addr.get("county") or addr.get("state_district") or addr.get("district"),
            "district": addr.get("state_district") or addr.get("district") or addr.get("county"),
            "state_district": addr.get("state_district") or addr.get("district") or addr.get("county"),
            "state": addr.get("state"),
            "country": addr.get("country"),
            "postcode": addr.get("postcode"),
        },
        "osm_id": f"{data.get('osm_type', 'node')}/{data.get('osm_id')}",
    }


# =============================================================================
# 9. Main Unified Execution Entry Point
# =============================================================================

def fetch_spatial_geocoding_poi(request: Union[SpatialGeocodingRequest, Dict[str, Any]]) -> Dict[str, Any]:
    """Universal execution dispatcher for Tool 10: Spatial Geocoding & POI Discovery."""
    if isinstance(request, dict):
        req = SpatialGeocodingRequest(**request)
    else:
        req = request

    if req.mode == "forward":
        return forward_geocode(
            query=req.query or "",
            bbox=req.bbox,
            viewbox_clamping=req.viewbox_clamping,
            max_results=req.max_results,
        )
    elif req.mode == "reverse":
        return reverse_geocode(
            latitude=req.latitude or 0.0,
            longitude=req.longitude or 0.0,
            zoom=req.zoom,
        )
    elif req.mode == "scene_identity":
        return resolve_scene_identity(bbox=req.bbox or [0, 0, 0, 0], query=req.query, landmark_names=req.landmark_names)
    elif req.mode == "poi_discovery":
        return discover_in_aoi_pois(
            bbox=req.bbox or [0, 0, 0, 0],
            categories=req.poi_categories,
            max_results=req.max_results,
        )
    else:
        return {
            "status": "error",
            "message": f"Unsupported geocoding mode: '{req.mode}'",
        }


# =============================================================================
# 10. Standalone Test Runner & FastMCP Registration
# =============================================================================

if FastMCP:
    mcp_tool = FastMCP("satquery_tool10")

    @mcp_tool.tool(
        name="spatial_geocoding_poi",
        description="Forward & reverse geocoding, scene identity resolution, and in-AOI POI discovery.",
    )
    def mcp_spatial_geocoding_poi(
        mode: Literal["forward", "reverse", "scene_identity", "poi_discovery", "auto"] = "auto",
        query: Optional[str] = None,
        landmark_names: Optional[list[str]] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        bbox: Optional[list[float]] = None,
        geotiff_path: Optional[str] = None,
        poi_categories: Optional[list[str]] = None,
        max_results: int = 15,
        zoom: Optional[int] = None,
        viewbox_clamping: bool = True,
    ) -> Dict[str, Any]:
        req = SpatialGeocodingRequest(
            mode=mode,
            query=query,
            landmark_names=landmark_names,
            latitude=latitude,
            longitude=longitude,
            bbox=bbox,
            geotiff_path=geotiff_path,
            poi_categories=poi_categories,
            max_results=max_results,
            zoom=zoom,
            viewbox_clamping=viewbox_clamping,
        )
        return fetch_spatial_geocoding_poi(req)


if __name__ == "__main__":
    print("=== Testing Tool 10: Spatial Geocoding & POI Discovery Engine ===")
    # 1. Forward Geocoding test
    print("\n1. Forward Geocoding: 'Red Fort, Delhi'")
    fwd_res = fetch_spatial_geocoding_poi({"mode": "forward", "query": "Red Fort, Delhi", "max_results": 2})
    print(json.dumps(fwd_res, indent=2))

    # 2. Scene Identity test (Delhi BBox)
    delhi_bbox = [77.20, 28.62, 77.28, 28.68]
    print(f"\n2. Scene Identity Resolution for BBox: {delhi_bbox}")
    ident_res = fetch_spatial_geocoding_poi({"mode": "scene_identity", "bbox": delhi_bbox})
    print(json.dumps(ident_res, indent=2))

    # 3. In-AOI POI Discovery test
    print(f"\n3. In-AOI POI Discovery for BBox: {delhi_bbox}")
    poi_res = fetch_spatial_geocoding_poi({
        "mode": "poi_discovery",
        "bbox": delhi_bbox,
        "poi_categories": ["tourism", "historic"],
        "max_results": 5,
    })
    print(json.dumps(poi_res, indent=2))
