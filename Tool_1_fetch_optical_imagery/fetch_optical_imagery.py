"""Tool 1: fetch_optical_imagery (Sentinel-2 L2A)

Retrieves visual True-Color RGB (B04, B03, B02) Sentinel-2 Level-2A GeoTIFF rasters
and structured metadata with AOI-Level SCL Quality Validation.
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
OUTPUT_DIR = Path("./output_optical")
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
# 4. Pydantic Request Validation Model
# =============================================================================

class OpticalSatelliteRequest(BaseModel):
    bbox: list[float] = Field(..., description="[min_lon, min_lat, max_lon, max_lat] in WGS84")
    start_date: str = Field(..., description="YYYY-MM-DD")
    end_date: str = Field(..., description="YYYY-MM-DD")
    max_cloud_cover: float = Field(default=30.0, ge=0.0, le=100.0)
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
            raise ValueError("Invalid coordinates: min values must be strictly smaller than max values.")
        return value

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
# 5. STAC Search, Scene Normalization & SCL Quality Inspector
# =============================================================================

def search_sentinel2_catalog(request: OpticalSatelliteRequest, max_results: int = 20) -> list[dict]:
    datetime_range = f"{request.start_date}T00:00:00Z/{request.end_date}T23:59:59Z"
    payload = {
        "bbox": request.bbox,
        "datetime": datetime_range,
        "collections": ["sentinel-2-l2a"],
        "limit": min(10, max_results),
    }
    if request.max_cloud_cover < 100:
        payload["filter"] = f"eo:cloud_cover <= {request.max_cloud_cover}"

    all_features = []
    while len(all_features) < max_results:
        response = http_client.request("POST", CONFIG.catalog_url, json=payload)
        if not response.ok:
            try:
                error_data = response.json()
            except ValueError:
                error_data = response.text
            raise RuntimeError(f"Catalog search failed (HTTP {response.status_code}): {error_data}")

        data = response.json()
        features = data.get("features", [])
        all_features.extend(features)
        context = data.get("context", {})
        next_val = context.get("next")
        if not next_val or not features:
            break
        payload["next"] = next_val
        remaining = max_results - len(all_features)
        if remaining <= 0:
            break
        payload["limit"] = min(10, remaining)

    return all_features[:max_results]


def normalize_scene(feature: dict) -> dict:
    props = feature.get("properties", {})
    cloud_cover = props.get("eo:cloud_cover")
    return {
        "scene_id": feature.get("id"),
        "collection": "sentinel-2-l2a",
        "acquisition_time": props.get("datetime"),
        "cloud_cover": float(cloud_cover) if cloud_cover is not None else None,
        "bbox": feature.get("bbox"),
        "geometry": feature.get("geometry"),
    }


SCL_EVALSCRIPT = """//VERSION=3
function setup() {
    return { input: [{ bands: ["SCL"] }], output: { bands: 1, sampleType: "UINT8" } };
}
function evaluatePixel(sample) { return [sample.SCL]; }
"""


def evaluate_aoi_quality(bbox: list[float], acquisition_time: str) -> dict:
    acquisition_dt = datetime.fromisoformat(acquisition_time.replace("Z", "+00:00"))
    payload = {
        "input": {
            "bounds": {"bbox": bbox, "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"}},
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {"timeRange": {"from": acquisition_dt.isoformat(), "to": acquisition_dt.isoformat()}}
            }]
        },
        "output": {"width": 64, "height": 64, "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]},
        "evalscript": SCL_EVALSCRIPT,
    }
    response = http_client.request("POST", CONFIG.process_url, json=payload, content_type="application/json")
    if not response.ok:
        return {"aoi_cloud_cover": None, "aoi_cloud_shadow": None, "aoi_obstruction": None, "aoi_snow_ice": None}

    with rasterio.open(io.BytesIO(response.content)) as src:
        scl_array = src.read(1)

    total_valid = np.count_nonzero(scl_array != 0)
    if total_valid == 0:
        return {"aoi_cloud_cover": 100.0, "aoi_cloud_shadow": 0.0, "aoi_obstruction": 100.0, "aoi_snow_ice": 0.0}

    shadow_count = np.count_nonzero(scl_array == 3)
    cloud_count = np.count_nonzero(np.isin(scl_array, [8, 9, 10]))
    snow_count = np.count_nonzero(scl_array == 11)

    aoi_cloud = round(float(cloud_count / total_valid * 100.0), 2)
    aoi_shadow = round(float(shadow_count / total_valid * 100.0), 2)
    aoi_snow = round(float(snow_count / total_valid * 100.0), 2)
    aoi_obstruction = round(aoi_cloud + aoi_shadow, 2)

    return {
        "aoi_cloud_cover": aoi_cloud,
        "aoi_cloud_shadow": aoi_shadow,
        "aoi_obstruction": aoi_obstruction,
        "aoi_snow_ice": aoi_snow,
    }


def select_best_scene(scenes: list[dict], bbox: list[float], max_cloud_threshold: float = 30.0) -> dict | None:
    valid_candidates = [
        s for s in scenes if s.get("scene_id") and s.get("cloud_cover") is not None and s.get("acquisition_time")
    ]
    if not valid_candidates:
        return None

    # Initial sort: catalog cloud cover ascending, then acquisition time descending
    valid_candidates.sort(
        key=lambda s: (
            s["cloud_cover"],
            -datetime.fromisoformat(s["acquisition_time"].replace("Z", "+00:00")).timestamp()
        )
    )

    evaluated_candidates = []
    for candidate in valid_candidates[:5]:  # Evaluate top 5 candidates at AOI level
        aoi_metrics = evaluate_aoi_quality(bbox, candidate["acquisition_time"])
        candidate_copy = dict(candidate)
        candidate_copy.update(aoi_metrics)
        evaluated_candidates.append(candidate_copy)

    # Deterministic Selection: Lowest AOI obstruction, then lowest catalog cloud, then most recent acquisition
    def ranking_key(c):
        obs = c.get("aoi_obstruction")
        dt_epoch = datetime.fromisoformat(c["acquisition_time"].replace("Z", "+00:00")).timestamp()
        return (obs if obs is not None else 999.0, c["cloud_cover"], -dt_epoch)

    best = min(evaluated_candidates, key=ranking_key)
    return best


# =============================================================================
# 6. Processing API Retrieval & Raster Validation
# =============================================================================

def build_optical_evalscript() -> str:
    return """//VERSION=3
function setup() {
    return {
        input: [{ bands: ["B04", "B03", "B02"] }],
        output: { bands: 3, sampleType: "UINT16" }
    };
}
function evaluatePixel(sample) {
    return [sample.B04 * 10000, sample.B03 * 10000, sample.B02 * 10000];
}"""


def process_optical_imagery(request: OpticalSatelliteRequest, scene: dict) -> Path:
    acquisition_time = scene["acquisition_time"]
    acquisition_dt = datetime.fromisoformat(acquisition_time.replace("Z", "+00:00"))
    
    payload = {
        "input": {
            "bounds": {
                "bbox": request.bbox,
                "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"}
            },
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {
                    "timeRange": {"from": acquisition_dt.isoformat(), "to": acquisition_dt.isoformat()},
                    "mosaickingOrder": "leastCC",
                    "maxCloudCoverage": request.max_cloud_cover,
                }
            }]
        },
        "output": {
            "width": request.width,
            "height": request.height,
            "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]
        },
        "evalscript": build_optical_evalscript(),
    }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_scene_id = re.sub(r"[^A-Za-z0-9_-]", "_", scene.get("scene_id", "unknown"))
    output_path = CONFIG.output_dir / f"sentinel2_{safe_scene_id}_{request.start_date}_{request.end_date}_optical_{timestamp}.tif"

    response = http_client.request("POST", CONFIG.process_url, json=payload, content_type="application/json")
    if not response.ok:
        try:
            error_data = response.json()
        except ValueError:
            error_data = response.text
        raise RuntimeError(f"Processing API failed (HTTP {response.status_code}): {error_data}")

    output_path.write_bytes(response.content)
    return output_path


def validate_raster(raster_path: Path) -> dict:
    with rasterio.open(raster_path) as src:
        return {
            "width": src.width,
            "height": src.height,
            "band_count": src.count,
            "dtype": str(src.dtypes[0]),
            "crs": str(src.crs),
            "bounds": {"left": src.bounds.left, "bottom": src.bounds.bottom, "right": src.bounds.right, "top": src.bounds.top},
            "resolution": {"x": src.res[0], "y": src.res[1]},
            "nodata": src.nodata,
        }


# =============================================================================
# 7. Core Execution Function
# =============================================================================

def fetch_optical_imagery(request: OpticalSatelliteRequest) -> dict:
    raw_scenes = search_sentinel2_catalog(request, max_results=20)
    scenes = [normalize_scene(s) for s in raw_scenes]
    best_scene = select_best_scene(scenes, bbox=request.bbox, max_cloud_threshold=request.max_cloud_cover)

    if best_scene is None:
        return {
            "status": "error",
            "error": {
                "type": "no_suitable_scene",
                "message": "No suitable Sentinel-2 L2A scene was found for the requested AOI, time range and cloud threshold."
            }
        }

    raster_path = process_optical_imagery(request, scene=best_scene)
    raster_metadata = validate_raster(raster_path)
    
    # AOI-level Quality Assessment
    aoi_obstruction = best_scene.get("aoi_obstruction")
    catalog_cloud = best_scene.get("cloud_cover")
    
    if aoi_obstruction is not None:
        optical_poor = aoi_obstruction > 50.0
    else:
        optical_poor = catalog_cloud is not None and catalog_cloud > 50.0

    return {
        "status": "success",
        "data": {
            "file_path": str(raster_path.resolve()),
            "file_name": raster_path.name,
            "format": "GeoTIFF",
        },
        "source": {
            "provider": "Sentinel Hub",
            "collection": "sentinel-2-l2a",
            "scene_id": best_scene.get("scene_id"),
            "acquisition_time": best_scene.get("acquisition_time"),
        },
        "request": {
            "bbox": request.bbox,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "modality": "optical",
            "bands": ["B04", "B03", "B02"],
            "max_cloud_cover": request.max_cloud_cover,
        },
        "raster": raster_metadata,
        "quality": {
            "catalog_cloud_cover": catalog_cloud,
            "aoi_cloud_cover": best_scene.get("aoi_cloud_cover"),
            "aoi_cloud_shadow": best_scene.get("aoi_cloud_shadow"),
            "aoi_obstruction": aoi_obstruction,
            "aoi_snow_ice": best_scene.get("aoi_snow_ice"),
            "valid": True,
        },
        "flags": {
            "optical_quality_poor": optical_poor,
            "sar_recommended": optical_poor,
        },
    }


# =============================================================================
# 8. FastMCP Tool Adapter & CLI Entry Point
# =============================================================================

if FastMCP is None:
    class _DummyMCP:
        def tool(self, *args, **kwargs):
            return lambda fn: fn
    mcp = _DummyMCP()
else:
    mcp = FastMCP("Tool 1: Optical Satellite Imagery Server")

@mcp.tool(
    name="fetch_optical_imagery",
    description="Fetch Sentinel-2 L2A true-color RGB optical satellite imagery for a requested bounding box and date range in GeoTIFF format with AOI-level SCL quality validation.",
)
def mcp_fetch_optical_imagery(
    bbox: list[float],
    start_date: str,
    end_date: str,
    max_cloud_cover: float = 30.0,
    width: int = 512,
    height: int = 512,
    crs: str = "EPSG:4326",
) -> dict:
    try:
        req = OpticalSatelliteRequest(
            bbox=bbox,
            start_date=start_date,
            end_date=end_date,
            max_cloud_cover=max_cloud_cover,
            width=width,
            height=height,
            crs=crs,
        )
        return fetch_optical_imagery(req)
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
            req = OpticalSatelliteRequest(**data)
            res = fetch_optical_imagery(req)
            print(json.dumps(res, indent=2))
        else:
            print(f"Error: input file '{input_file}' not found.", file=sys.stderr)
            sys.exit(1)
    else:
        print("Tool 1: fetch_optical_imagery ready. Pass a JSON configuration file or run via FastMCP.")
