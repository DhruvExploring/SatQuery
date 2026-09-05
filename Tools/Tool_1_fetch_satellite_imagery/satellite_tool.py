"""
satellite_tool.py — Importable production module for fetch_satellite_imagery.

This file is the extracted, importable form of the notebook
fetch_satellite_imagery.ipynb. The notebook remains the canonical
development document. This module exposes exactly one public symbol:

    mcp_fetch_satellite_imagery(**kwargs) -> dict

The LangGraph executor calls ONLY that function. All Sentinel Hub logic
lives here (and in the notebook). The orchestrator never duplicates it.

Environment variables required (put in a .env file or export them):
    SENTINEL_HUB_CLIENT_ID
    SENTINEL_HUB_CLIENT_SECRET
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

import requests
import rasterio
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TOKEN_URL = (
    "https://services.sentinel-hub.com/"
    "auth/realms/main/protocol/openid-connect/token"
)
CATALOG_URL = "https://services.sentinel-hub.com/catalog/v1/search"
PROCESS_URL = "https://services.sentinel-hub.com/process/v1"

# Output directory is relative to THIS file so it matches the notebook's behaviour.
OUTPUT_DIR = Path(__file__).parent / "sih_satellite_data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# SatelliteRequest — input validation model
# ---------------------------------------------------------------------------
class SatelliteRequest(BaseModel):
    bbox: list[float] = Field(
        ...,
        description="Bounding box in [min_lon, min_lat, max_lon, max_lat] order.",
    )
    start_date: str
    end_date: str
    modality: Literal["optical", "multispectral"] = "optical"
    bands: Optional[list[str]] = None
    max_cloud_cover: float = Field(default=30.0, ge=0.0, le=100.0)
    width: int = Field(default=512, ge=1, le=4096)
    height: int = Field(default=512, ge=1, le=4096)
    crs: str = "EPSG:4326"
    output_format: Literal["GeoTIFF"] = "GeoTIFF"

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: list[float]) -> list[float]:
        if len(value) != 4:
            raise ValueError("bbox must contain exactly 4 values: [min_lon, min_lat, max_lon, max_lat].")
        min_lon, min_lat, max_lon, max_lat = value
        if not -180 <= min_lon <= 180:
            raise ValueError("bbox min_lon must be between -180 and 180.")
        if not -180 <= max_lon <= 180:
            raise ValueError("bbox max_lon must be between -180 and 180.")
        if not -90 <= min_lat <= 90:
            raise ValueError("bbox min_lat must be between -90 and 90.")
        if not -90 <= max_lat <= 90:
            raise ValueError("bbox max_lat must be between -90 and 90.")
        if min_lon >= max_lon:
            raise ValueError("bbox min_lon must be smaller than max_lon.")
        if min_lat >= max_lat:
            raise ValueError("bbox min_lat must be smaller than max_lat.")
        return value

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date_format(cls, value: str) -> str:
        from datetime import date
        try:
            date.fromisoformat(value)
        except ValueError:
            raise ValueError(f"Invalid date '{value}'. Use YYYY-MM-DD format.")
        return value

    @model_validator(mode="after")
    def validate_date_range(self) -> "SatelliteRequest":
        from datetime import date
        if date.fromisoformat(self.start_date) > date.fromisoformat(self.end_date):
            raise ValueError("start_date cannot be later than end_date.")
        return self

    @model_validator(mode="after")
    def validate_band_configuration(self) -> "SatelliteRequest":
        if self.modality == "optical" and self.bands is not None:
            raise ValueError(
                "bands must be omitted when modality='optical'. "
                "Optical mode always returns B04/B03/B02 RGB."
            )
        if self.modality == "multispectral" and not self.bands:
            raise ValueError("bands must be provided when modality='multispectral'.")
        return self


# ---------------------------------------------------------------------------
# Sentinel Hub HTTP client (token-based auth)
# ---------------------------------------------------------------------------
class _SentinelHubClient:
    """Thin HTTP wrapper that handles OAuth token refresh automatically."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expiry: float = 0.0

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 30:
            return self._token

        client_id = os.getenv("SENTINEL_HUB_CLIENT_ID", "")
        client_secret = os.getenv("SENTINEL_HUB_CLIENT_SECRET", "")

        if not client_id or not client_secret:
            raise RuntimeError(
                "SENTINEL_HUB_CLIENT_ID and SENTINEL_HUB_CLIENT_SECRET "
                "must be set as environment variables."
            )

        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expiry = time.time() + payload.get("expires_in", 3600)
        return self._token

    def request(
        self,
        method: str,
        url: str,
        *,
        json: dict | None = None,
        content_type: str = "application/json",
    ) -> requests.Response:
        token = self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
            "Accept": "application/json, image/tiff",
        }
        return requests.request(method, url, headers=headers, json=json, timeout=60)


_client = _SentinelHubClient()


# ---------------------------------------------------------------------------
# Catalog search
# ---------------------------------------------------------------------------
def search_sentinel2_catalog(request: SatelliteRequest, max_results: int = 20) -> list[dict]:
    datetime_range = f"{request.start_date}T00:00:00Z/{request.end_date}T23:59:59Z"
    payload: dict = {
        "bbox": request.bbox,
        "datetime": datetime_range,
        "collections": ["sentinel-2-l2a"],
        "limit": min(10, max_results),
    }
    if request.max_cloud_cover < 100:
        payload["filter"] = f"eo:cloud_cover <= {request.max_cloud_cover}"

    all_features: list[dict] = []

    while len(all_features) < max_results:
        response = _client.request("POST", CATALOG_URL, json=payload)
        if not response.ok:
            try:
                error_data = response.json()
            except ValueError:
                error_data = response.text
            raise RuntimeError(f"Catalog search failed (HTTP {response.status_code}): {error_data}")

        data = response.json()
        features = data.get("features", [])
        if not isinstance(features, list):
            raise RuntimeError("Catalog response contains an invalid 'features' field.")
        all_features.extend(features)

        next_value = data.get("context", {}).get("next")
        if not next_value or not features:
            break

        payload["next"] = next_value
        remaining = max_results - len(all_features)
        if remaining <= 0:
            break
        payload["limit"] = min(10, remaining)

    return all_features[:max_results]


# ---------------------------------------------------------------------------
# Scene normalisation + selection
# ---------------------------------------------------------------------------
def normalize_scene(raw: dict) -> dict:
    props = raw.get("properties", {})
    return {
        "scene_id": raw.get("id"),
        "acquisition_time": props.get("datetime"),
        "cloud_cover": props.get("eo:cloud_cover"),
        "bbox": raw.get("bbox"),
    }


def select_best_scene(scenes: list[dict]) -> dict | None:
    valid = [s for s in scenes if s.get("cloud_cover") is not None]
    if not valid:
        return None
    return min(valid, key=lambda s: s["cloud_cover"])


# ---------------------------------------------------------------------------
# Evalscript builder
# ---------------------------------------------------------------------------
def build_evalscript(request: SatelliteRequest) -> str:
    if request.modality == "optical":
        return """
//VERSION=3
function setup() {
    return { input: [{ bands: ["B04","B03","B02"] }], output: { bands: 3, sampleType: "UINT16" } };
}
function evaluatePixel(sample) {
    return [sample.B04 * 10000, sample.B03 * 10000, sample.B02 * 10000];
}
"""
    if request.modality == "multispectral":
        if not request.bands:
            raise ValueError("bands must be provided when modality='multispectral'.")
        band_list = ", ".join(f'"{b}"' for b in request.bands)
        sample_values = ", ".join(f"sample.{b}" for b in request.bands)
        return f"""
//VERSION=3
function setup() {{
    return {{ input: [{{ bands: [{band_list}] }}], output: {{ bands: {len(request.bands)}, sampleType: "FLOAT32" }} }};
}}
function evaluatePixel(sample) {{ return [{sample_values}]; }}
"""
    raise ValueError(f"Unsupported modality: {request.modality}")


# ---------------------------------------------------------------------------
# Processing API call
# ---------------------------------------------------------------------------
def build_process_payload(request: SatelliteRequest, scene: dict) -> dict:
    evalscript = build_evalscript(request)
    acquisition_time = scene.get("acquisition_time")
    if not acquisition_time:
        raise ValueError("Selected scene does not contain an acquisition time.")

    acquisition_dt = datetime.fromisoformat(acquisition_time.replace("Z", "+00:00"))

    return {
        "input": {
            "bounds": {
                "bbox": request.bbox,
                "properties": {"crs": f"http://www.opengis.net/def/crs/EPSG/0/{request.crs.split(':')[1]}"},
            },
            "data": [
                {
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "timeRange": {
                            "from": acquisition_dt.isoformat(),
                            "to": acquisition_dt.isoformat(),
                        },
                        "mosaickingOrder": "leastCC",
                        "maxCloudCoverage": request.max_cloud_cover,
                    },
                }
            ],
        },
        "output": {
            "width": request.width,
            "height": request.height,
            "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}],
        },
        "evalscript": evalscript,
    }


def create_output_path(request: SatelliteRequest, scene: dict | None = None) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    scene_id = "unknown_scene"
    if scene and scene.get("scene_id"):
        scene_id = scene["scene_id"]
    safe_scene_id = re.sub(r"[^A-Za-z0-9_-]", "_", scene_id)
    filename = (
        f"sentinel2_{safe_scene_id}_"
        f"{request.start_date}_{request.end_date}_"
        f"{request.modality}_{timestamp}.tif"
    )
    return OUTPUT_DIR / filename


def process_satellite_imagery(request: SatelliteRequest, scene: dict) -> Path:
    payload = build_process_payload(request, scene)
    output_path = create_output_path(request, scene)

    response = _client.request("POST", PROCESS_URL, json=payload)

    if not response.ok:
        try:
            error_data = response.json()
        except ValueError:
            error_data = response.text
        raise RuntimeError(f"Processing API failed (HTTP {response.status_code}): {error_data}")

    content_type = response.headers.get("Content-Type", "").lower()
    if "image/tiff" not in content_type:
        raise RuntimeError(f"Processing API returned unexpected content type: {content_type}")

    output_path.write_bytes(response.content)

    if output_path.stat().st_size == 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError("Processing API returned an empty GeoTIFF.")

    return output_path


# ---------------------------------------------------------------------------
# Raster validation
# ---------------------------------------------------------------------------
def validate_raster(path: Path) -> dict:
    with rasterio.open(path) as ds:
        return {
            "width": ds.width,
            "height": ds.height,
            "band_count": ds.count,
            "dtype": str(ds.dtypes[0]),
            "crs": str(ds.crs),
        }


# ---------------------------------------------------------------------------
# Success result builder
# ---------------------------------------------------------------------------
def build_success_result(
    request: SatelliteRequest,
    scene: dict | None,
    raster_path: Path,
    raster_metadata: dict,
) -> dict:
    cloud_cover = scene.get("cloud_cover") if scene else None
    optical_quality_poor = cloud_cover is not None and cloud_cover > 50

    return {
        "status": "success",
        "data": {
            "file_path": str(raster_path),
            "file_name": raster_path.name,
            "format": request.output_format,
        },
        "source": {
            "provider": "Sentinel Hub",
            "collection": "sentinel-2-l2a",
            "scene_id": scene.get("scene_id") if scene else None,
            "acquisition_time": scene.get("acquisition_time") if scene else None,
        },
        "request": {
            "bbox": request.bbox,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "modality": request.modality,
            "bands": request.bands,
            "max_cloud_cover": request.max_cloud_cover,
        },
        "raster": raster_metadata,
        "quality": {"cloud_cover": cloud_cover, "valid": True},
        "flags": {
            "optical_quality_poor": optical_quality_poor,
            "sar_recommended": optical_quality_poor,
        },
    }


# ---------------------------------------------------------------------------
# Core fetch function
# ---------------------------------------------------------------------------
def fetch_satellite_imagery(request: SatelliteRequest) -> dict:
    """Full pipeline: catalog → scene selection → download → validate → result."""
    raw_scenes = search_sentinel2_catalog(request, max_results=20)
    scenes = [normalize_scene(s) for s in raw_scenes]
    best_scene = select_best_scene(scenes)

    if best_scene is None:
        return {
            "status": "error",
            "error": {
                "type": "no_suitable_scene",
                "message": (
                    "No suitable Sentinel-2 L2A scene was found "
                    "for the requested AOI, time range and cloud threshold."
                ),
            },
        }

    raster_path = process_satellite_imagery(request, scene=best_scene)
    raster_metadata = validate_raster(raster_path)
    return build_success_result(
        request=request,
        scene=best_scene,
        raster_path=raster_path,
        raster_metadata=raster_metadata,
    )


# ---------------------------------------------------------------------------
# Public entry point — called by the LangGraph executor
# ---------------------------------------------------------------------------
def mcp_fetch_satellite_imagery(
    bbox: list[float],
    start_date: str,
    end_date: str,
    modality: str = "optical",
    bands: list[str] | None = None,
    max_cloud_cover: float = 30.0,
    width: int = 512,
    height: int = 512,
    crs: Literal["EPSG:4326"] = "EPSG:4326",
) -> dict:
    """
    Called by executor.py. Accepts flat kwargs, builds SatelliteRequest,
    and delegates to fetch_satellite_imagery(). Never called directly
    by nodes.py or graph.py.
    """
    try:
        request = SatelliteRequest(
            bbox=bbox,
            start_date=start_date,
            end_date=end_date,
            modality=modality,
            bands=bands,
            max_cloud_cover=max_cloud_cover,
            width=width,
            height=height,
            crs=crs,
            output_format="GeoTIFF",
        )
        return fetch_satellite_imagery(request)

    except ValueError as exc:
        return {"status": "error", "error": {"type": "validation_error", "message": str(exc)}}
    except RuntimeError as exc:
        return {"status": "error", "error": {"type": "service_error", "message": str(exc)}}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": {"type": "unexpected_error", "message": str(exc)}}
