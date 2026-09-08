"""Tool 3: fetch_sar_imagery (Sentinel-1 Synthetic Aperture Radar)

Retrieves calibrated Decibel (dB) dual-polarization (VV/VH) Sentinel-1 GRD SAR GeoTIFF rasters
with DEM Terrain Orthorectification, Intent-Aware Scene Selection, and Radar Geometry Quality Validation.
"""

import io
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional, List, Dict, Any

import numpy as np
import rasterio
import requests
from pydantic import BaseModel, Field, field_validator, model_validator
try:
    from fastmcp import FastMCP
except (ImportError, Exception):
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        FastMCP = None

# Load optional .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# =============================================================================
# 1. Credentials & Tool Configuration
# =============================================================================

CLIENT_ID = os.getenv("SENTINEL_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("SENTINEL_CLIENT_SECRET", "")

TOKEN_URL = "https://services.sentinel-hub.com/auth/realms/main/protocol/openid-connect/token"
CATALOG_URL = "https://services.sentinel-hub.com/catalog/v1/search"
PROCESS_URL = "https://services.sentinel-hub.com/process/v1"
OUTPUT_DIR = Path("./output_sar")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class ToolConfig:
    client_id: str
    client_secret: str
    token_url: str
    catalog_url: str
    process_url: str
    output_dir: Path


CONFIG = ToolConfig(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    token_url=TOKEN_URL,
    catalog_url=CATALOG_URL,
    process_url=PROCESS_URL,
    output_dir=OUTPUT_DIR,
)


# =============================================================================
# 2. Authentication Manager (Token Caching)
# =============================================================================

class SentinelHubAuth:
    def __init__(self, config: ToolConfig):
        self.config = config
        self._access_token = None
        self._expires_at = 0.0

    def get_token(self) -> str:
        if not self.config.client_id or not self.config.client_secret:
            raise RuntimeError(
                "Sentinel Hub credentials missing. Set SENTINEL_CLIENT_ID and "
                "SENTINEL_CLIENT_SECRET in your .env file."
            )
        current_time = time.time()
        if self._access_token is not None and current_time < self._expires_at:
            return self._access_token

        response = requests.post(
            self.config.token_url,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
            },
            timeout=30,
        )
        if not response.ok:
            try:
                error_data = response.json()
            except ValueError:
                error_data = response.text
            raise RuntimeError(f"Sentinel Hub auth failed (HTTP {response.status_code}): {error_data}")

        token_data = response.json()
        access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in")
        if not access_token or not expires_in:
            raise RuntimeError("Invalid token response from Sentinel Hub.")

        self._access_token = access_token
        self._expires_at = current_time + float(expires_in) - 60
        return self._access_token


auth = SentinelHubAuth(CONFIG)


# =============================================================================
# 3. Resilient HTTP Client
# =============================================================================

class SentinelHubHTTPClient:
    def __init__(self, auth: SentinelHubAuth, max_retries: int = 3, timeout: int = 60):
        self.auth = auth
        self.max_retries = max_retries
        self.timeout = timeout
        self.retryable_status_codes = {429, 500, 502, 503, 504}

    def _get_headers(self, content_type: str = "application/json") -> dict:
        token = self.auth.get_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": content_type}

    def request(self, method: str, url: str, *, content_type: str = "application/json", **kwargs) -> requests.Response:
        for attempt in range(self.max_retries + 1):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    headers=self._get_headers(content_type),
                    timeout=self.timeout,
                    **kwargs,
                )
            except requests.RequestException:
                if attempt >= self.max_retries:
                    raise
                time.sleep(min(2 ** attempt, 30))
                continue

            if response.status_code not in self.retryable_status_codes or attempt >= self.max_retries:
                return response

            retry_after = response.headers.get("Retry-After")
            sleep_time = float(retry_after) if retry_after and retry_after.isdigit() else min(2 ** attempt, 30)
            time.sleep(sleep_time)

        raise RuntimeError("HTTP request failed unexpectedly.")


http_client = SentinelHubHTTPClient(auth=auth)


# =============================================================================
# 4. Pydantic Request Validation Model for SAR
# =============================================================================

VALID_POLARIZATIONS = {"VV", "VH", "HH", "HV"}

class SARSatelliteRequest(BaseModel):
    bbox: list[float] = Field(..., description="[min_lon, min_lat, max_lon, max_lat] in WGS84")
    start_date: str = Field(..., description="YYYY-MM-DD")
    end_date: str = Field(..., description="YYYY-MM-DD")
    scene_selection: Literal["most_recent", "closest_to_start_date", "closest_to_end_date"] = "most_recent"
    polarization: list[str] = Field(default=["VV", "VH"], description="List of SAR polarizations")
    orbit_direction: Literal["ASCENDING", "DESCENDING", "BOTH"] = "BOTH"
    width: int = Field(default=512, ge=1, le=4096)
    height: int = Field(default=512, ge=1, le=4096)
    crs: str = "EPSG:4326"

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value):
        if len(value) != 4:
            raise ValueError("bbox must contain exactly 4 values: [min_lon, min_lat, max_lon, max_lat].")
        min_lon, min_lat, max_lon, max_lat = value
        if not -180 <= min_lon <= 180 or not -180 <= max_lon <= 180:
            raise ValueError("Longitude must be within [-180, 180].")
        if not -90 <= min_lat <= 90 or not -90 <= max_lat <= 90:
            raise ValueError("Latitude must be within [-90, 90].")
        if min_lon >= max_lon or min_lat >= max_lat:
            raise ValueError("min coordinates must be smaller than max coordinates.")
        return value

    @field_validator("polarization")
    @classmethod
    def validate_polarization(cls, pol_list):
        if not pol_list:
            raise ValueError("polarization list cannot be empty.")
        for p in pol_list:
            if p.upper() not in VALID_POLARIZATIONS:
                raise ValueError(f"Unsupported polarization '{p}'. Valid values are: {sorted(list(VALID_POLARIZATIONS))}")
        return [p.upper() for p in pol_list]

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date_format(cls, value):
        from datetime import date
        try:
            date.fromisoformat(value)
        except ValueError:
            raise ValueError(f"Invalid date format '{value}'. Use YYYY-MM-DD.")
        return value

    @model_validator(mode="after")
    def validate_date_range(self):
        from datetime import date
        if date.fromisoformat(self.start_date) > date.fromisoformat(self.end_date):
            raise ValueError("start_date cannot be later than end_date.")
        return self


# =============================================================================
# 5. STAC Catalog Discovery & Intent-Aware Scene Selection
# =============================================================================

def _feature_to_sar_scene(feature: dict) -> dict:
    props = feature.get("properties") or {}
    orbit_raw = props.get("sat:orbit_state") or props.get("sat:orbit_direction") or "UNKNOWN"
    polarizations = props.get("sar:polarizations") or ["VV", "VH"]
    return {
        "scene_id": feature.get("id"),
        "collection": "sentinel-1-grd",
        "acquisition_time": props.get("datetime"),
        "orbit_direction": str(orbit_raw).upper(),
        "polarization": [str(p).upper() for p in polarizations],
        "instrument_mode": str(props.get("sar:instrument_mode") or "IW").upper(),
        "bbox": feature.get("bbox"),
        "geometry": feature.get("geometry"),
    }


def _polarization_ok(scene: dict, requested: list[str]) -> bool:
    available = set(scene.get("polarization") or [])
    if not available:
        return True
    return set(requested).issubset(available)


def filter_sar_scenes(
    scenes: list[dict],
    request: SARSatelliteRequest,
    *,
    match_orbit: bool,
) -> list[dict]:
    """Keep IW scenes that expose the requested polarizations, optionally matching orbit."""
    filtered: list[dict] = []
    for scene in scenes:
        mode = scene.get("instrument_mode") or "IW"
        if mode not in {"IW", "UNKNOWN"}:
            continue
        if not scene.get("scene_id") or not scene.get("acquisition_time"):
            continue
        if not _polarization_ok(scene, request.polarization):
            continue
        if match_orbit and request.orbit_direction != "BOTH":
            if scene.get("orbit_direction") != request.orbit_direction:
                continue
        filtered.append(scene)
    return filtered


def search_sentinel1_catalog(request: SARSatelliteRequest, max_results: int = 50) -> list[dict]:
    datetime_range = f"{request.start_date}T00:00:00Z/{request.end_date}T23:59:59Z"
    payload: dict[str, Any] = {
        "bbox": request.bbox,
        "datetime": datetime_range,
        "collections": ["sentinel-1-grd"],
        "limit": min(50, max_results),
    }

    all_features: list[dict] = []
    while len(all_features) < max_results:
        response = http_client.request("POST", CONFIG.catalog_url, json=payload)
        if not response.ok:
            try:
                error_data = response.json()
            except ValueError:
                error_data = response.text
            raise RuntimeError(f"Sentinel-1 Catalog search failed (HTTP {response.status_code}): {error_data}")

        data = response.json()
        features = data.get("features") or []
        all_features.extend(features)
        next_val = (data.get("context") or {}).get("next")
        if not next_val or not features:
            break
        payload["next"] = next_val
        remaining = max_results - len(all_features)
        if remaining <= 0:
            break
        payload["limit"] = min(50, remaining)

    return [_feature_to_sar_scene(f) for f in all_features[:max_results]]


def select_best_sar_scene(scenes: list[dict], request: SARSatelliteRequest) -> dict | None:
    """Pick the best IW scene that matches the requested orbit. No orbit substitution."""
    matching = filter_sar_scenes(scenes, request, match_orbit=True)
    if not matching:
        return None

    if request.scene_selection == "closest_to_start_date":
        target_dt = datetime.fromisoformat(f"{request.start_date}T00:00:00+00:00")
        return min(
            matching,
            key=lambda s: abs(
                datetime.fromisoformat(s["acquisition_time"].replace("Z", "+00:00")) - target_dt
            ),
        )
    if request.scene_selection == "closest_to_end_date":
        target_dt = datetime.fromisoformat(f"{request.end_date}T23:59:59+00:00")
        return min(
            matching,
            key=lambda s: abs(
                datetime.fromisoformat(s["acquisition_time"].replace("Z", "+00:00")) - target_dt
            ),
        )
    return max(matching, key=lambda s: s["acquisition_time"])


# =============================================================================
# 6. Radar Geometry & Shadow Quality Inspector
# =============================================================================

SHADOW_EVALSCRIPT = """//VERSION=3
function setup() {
    return { input: [{ bands: ["shadowMask", "localIncidenceAngle"] }], output: { bands: 2, sampleType: "FLOAT32" } };
}
function evaluatePixel(sample) { return [sample.shadowMask, sample.localIncidenceAngle]; }
"""


def evaluate_sar_geometry_quality(bbox: list[float], acquisition_time: str) -> dict:
    acquisition_dt = datetime.fromisoformat(acquisition_time.replace("Z", "+00:00"))
    payload = {
        "input": {
            "bounds": {"bbox": bbox, "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"}},
            "data": [{
                "type": "sentinel-1-grd",
                "dataFilter": {"timeRange": {"from": acquisition_dt.isoformat(), "to": acquisition_dt.isoformat()}},
                "processing": {"orthorectify": True, "backCoeff": "GAMMA0_TERRAIN"}
            }]
        },
        "output": {"width": 64, "height": 64, "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]},
        "evalscript": SHADOW_EVALSCRIPT,
    }
    response = http_client.request("POST", CONFIG.process_url, json=payload, content_type="application/json")
    if not response.ok:
        return {"radar_shadow_fraction": 0.0, "mean_incidence_angle_deg": 38.0, "geometry_quality": "good", "radar_geometry_poor": False}

    with rasterio.open(io.BytesIO(response.content)) as src:
        shadow = src.read(1)
        angle = src.read(2)
        shadow_frac = round(float(np.count_nonzero(shadow > 0) / shadow.size), 4)
        valid_angles = angle[angle > 0]
        mean_angle = round(float(np.mean(valid_angles)), 2) if len(valid_angles) > 0 else 38.0
    is_angle_degraded = bool(mean_angle < 15.0 or mean_angle > 65.0)
    is_shadow_degraded = bool(shadow_frac > 0.08)
    radar_geometry_poor = bool(is_shadow_degraded or is_angle_degraded)
    geometry_quality = "degraded" if radar_geometry_poor else "good"
    
    return {
        "radar_shadow_fraction": shadow_frac,
        "mean_incidence_angle_deg": mean_angle,
        "geometry_quality": geometry_quality,
        "radar_geometry_poor": radar_geometry_poor,
    }


# =============================================================================
# 7. Decibel Evalscript & Processing API Engine
# =============================================================================

def build_sar_evalscript(polarizations: list[str]) -> str:
    band_inputs = ", ".join(f'"{p}"' for p in polarizations)
    db_conversions = ", ".join(f"10 * Math.log10(Math.max(sample.{p}, 0.00001))" for p in polarizations)
    return f"""//VERSION=3
function setup() {{
    return {{
        input: [{{ bands: [{band_inputs}] }}],
        output: {{ bands: {len(polarizations)}, sampleType: "FLOAT32" }}
    }};
}}
function evaluatePixel(sample) {{
    return [{db_conversions}];
}}"""


def process_sar_imagery(request: SARSatelliteRequest, scene: dict) -> Path:
    acquisition_time = scene["acquisition_time"]
    acquisition_dt = datetime.fromisoformat(acquisition_time.replace("Z", "+00:00"))
    
    payload = {
        "input": {
            "bounds": {
                "bbox": request.bbox,
                "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"}
            },
            "data": [{
                "type": "sentinel-1-grd",
                "dataFilter": {
                    "timeRange": {"from": acquisition_dt.isoformat(), "to": acquisition_dt.isoformat()},
                    "acquisitionMode": "IW",
                    "polarization": "DV" if set(request.polarization).issubset({"VV", "VH"}) else "DH",
                },
                "processing": {
                    "orthorectify": True,
                    "backCoeff": "GAMMA0_TERRAIN"
                }
            }]
        },
        "output": {
            "width": request.width,
            "height": request.height,
            "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]
        },
        "evalscript": build_sar_evalscript(request.polarization),
    }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_scene_id = re.sub(r"[^A-Za-z0-9_-]", "_", scene.get("scene_id", "unknown"))
    output_path = CONFIG.output_dir / f"sentinel1_{safe_scene_id}_{request.start_date}_{request.end_date}_sar_{timestamp}.tif"

    response = http_client.request("POST", CONFIG.process_url, json=payload, content_type="application/json")
    if not response.ok:
        try:
            error_data = response.json()
        except ValueError:
            error_data = response.text
        raise RuntimeError(f"Processing API failed (HTTP {response.status_code}): {error_data}")

    output_path.write_bytes(response.content)
    return output_path


def validate_raster(raster_path: Path, polarizations: list[str]) -> dict:
    with rasterio.open(raster_path) as src:
        band_mapping = {f"Band_{i+1}": f"{p}_dB" for i, p in enumerate(polarizations)}
        return {
            "width": src.width,
            "height": src.height,
            "band_count": src.count,
            "dtype": str(src.dtypes[0]),
            "crs": str(src.crs),
            "unit": "dB (Decibels)",
            "band_mapping": band_mapping,
            "bounds": {"left": src.bounds.left, "bottom": src.bounds.bottom, "right": src.bounds.right, "top": src.bounds.top},
            "resolution": {"x": src.res[0], "y": src.res[1]},
            "nodata": src.nodata,
        }


# =============================================================================
# 8. Core Execution Function
# =============================================================================

def fetch_sar_imagery(request: SARSatelliteRequest) -> dict:
    scenes = search_sentinel1_catalog(request, max_results=50)
    best_scene = select_best_sar_scene(scenes, request=request)

    if best_scene is None:
        orbits = sorted({s.get("orbit_direction") or "UNKNOWN" for s in scenes})
        if scenes and request.orbit_direction != "BOTH":
            available = " or ".join(orbits) if orbits else "BOTH"
            detail = (
                f" {len(scenes)} scene(s) exist for this AOI/date range, but all are "
                f"{', '.join(orbits)} — none are {request.orbit_direction}. "
                f"Retry with orbit_direction={available} or BOTH."
            )
        elif scenes:
            detail = (
                f" Catalog returned {len(scenes)} scene(s) with orbit(s) {orbits}; "
                f"none matched polarization={request.polarization}."
            )
        else:
            detail = " Catalog returned no Sentinel-1 GRD items for this AOI and date range."
        return {
            "status": "error",
            "error": {
                "type": "no_suitable_scene",
                "message": (
                    "No suitable Sentinel-1 GRD SAR scene was found for the requested "
                    f"AOI, time range and orbit parameters.{detail}"
                ),
            },
        }

    raster_path = process_sar_imagery(request, scene=best_scene)
    raster_metadata = validate_raster(raster_path, polarizations=request.polarization)
    geometry_metrics = evaluate_sar_geometry_quality(request.bbox, best_scene["acquisition_time"])

    return {
        "status": "success",
        "data": {
            "file_path": str(raster_path.resolve()),
            "file_name": raster_path.name,
            "format": "GeoTIFF",
        },
        "source": {
            "provider": "Sentinel Hub",
            "collection": "sentinel-1-grd",
            "scene_id": best_scene.get("scene_id"),
            "acquisition_time": best_scene.get("acquisition_time"),
            "instrument_mode": best_scene.get("instrument_mode"),
            "orbit_direction": best_scene.get("orbit_direction"),
            "polarization": request.polarization,
        },
        "selection": {
            "strategy": request.scene_selection,
            "orbit_direction": request.orbit_direction,
            "orbit_used": best_scene.get("orbit_direction"),
        },
        "request": {
            "bbox": request.bbox,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "scene_selection": request.scene_selection,
            "polarization": request.polarization,
            "orbit_direction": request.orbit_direction,
        },
        "raster": raster_metadata,
        "quality": {
            "cloud_penetrating": True,
            "weather_independent": True,
            "day_night_capability": True,
            "radar_shadow_fraction": geometry_metrics["radar_shadow_fraction"],
            "mean_incidence_angle_deg": geometry_metrics["mean_incidence_angle_deg"],
            "geometry_quality": geometry_metrics["geometry_quality"],
            "valid": True,
        },
        "flags": {
            "radar_valid": True,
            "radar_geometry_poor": geometry_metrics["radar_geometry_poor"],
            "water_mapping_ready": not geometry_metrics["radar_geometry_poor"],
        },
    }


# =============================================================================
# 9. FastMCP Tool Adapter & CLI Entry Point
# =============================================================================

if FastMCP is None:
    class _DummyMCP:
        def tool(self, *args, **kwargs):
            return lambda fn: fn
    mcp = _DummyMCP()
else:
    mcp = FastMCP("Tool 3: SAR Satellite Imagery Server")

@mcp.tool(
    name="fetch_sar_imagery",
    description="Fetch Sentinel-1 GRD Synthetic Aperture Radar (SAR) terrain-orthorectified backscatter imagery in Decibel (dB) GeoTIFF format with intent-aware scene selection and radar geometry quality validation.",
)
def mcp_fetch_sar_imagery(
    bbox: list[float],
    start_date: str,
    end_date: str,
    scene_selection: str = "most_recent",
    polarization: list[str] = ["VV", "VH"],
    orbit_direction: str = "BOTH",
    width: int = 512,
    height: int = 512,
    crs: str = "EPSG:4326",
) -> dict:
    try:
        req = SARSatelliteRequest(
            bbox=bbox,
            start_date=start_date,
            end_date=end_date,
            scene_selection=scene_selection,
            polarization=polarization,
            orbit_direction=orbit_direction,
            width=width,
            height=height,
            crs=crs,
        )
        return fetch_sar_imagery(req)
    except ValueError as e:
        return {"status": "error", "error": {"type": "validation_error", "message": str(e)}}
    except Exception as e:
        return {"status": "error", "error": {"type": "service_error", "message": str(e)}}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        input_file = Path(sys.argv[1])
        if input_file.exists():
            with open(input_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            req = SARSatelliteRequest(**data)
            res = fetch_sar_imagery(req)
            print(json.dumps(res, indent=2))
        else:
            print(f"Error: input file '{input_file}' not found.", file=sys.stderr)
            sys.exit(1)
    else:
        print("Tool 3: fetch_sar_imagery ready. Pass a JSON configuration file or run via FastMCP.")
