"""Tool 4: fetch_weather_environment (Meteorological & Environmental Context)

Extracts global meteorological reanalysis data (ERA5 / ERA5-Land) via Open-Meteo
to provide factual atmospheric, thermal, and hydrological context for satellite observations
with strict separation between measured metrics and derived environmental stress indicators.

For a date range that reaches into the last few days or the future, the ERA5
archive (below) is stale or empty -- those days are instead served by
Open-Meteo's forecast API, which also covers real current conditions and true
forecasts. A range spanning both is split and the two daily series are
merged; see _split_date_range/_fetch_daily_for_point.
"""

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
from typing import Literal, Optional, List, Dict, Any, Tuple

import numpy as np
import requests
from pydantic import BaseModel, Field, field_validator, model_validator
try:
    from fastmcp import FastMCP
except (ImportError, Exception):
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        FastMCP = None


# =============================================================================
# 1. Configuration & Resilient HTTP Client
# =============================================================================

ARCHIVE_API_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_API_URL = "https://api.open-meteo.com/v1/forecast"

# ERA5/ERA5-Land archive assimilation latency: days newer than this are
# unreliable/absent from the archive and are fetched from the forecast API
# instead (see _split_date_range).
ARCHIVE_LATENCY_DAYS = 5

@dataclass(frozen=True)
class ToolConfig:
    archive_api_url: str = ARCHIVE_API_URL
    forecast_api_url: str = FORECAST_API_URL

CONFIG = ToolConfig()


class WeatherHTTPClient:
    def __init__(self, max_retries: int = 3, timeout: int = 30):
        self.max_retries = max_retries
        self.timeout = timeout
        self.retryable_status_codes = {429, 500, 502, 503, 504}

    def get(self, url: str, params: dict) -> requests.Response:
        for attempt in range(self.max_retries + 1):
            try:
                response = requests.get(url, params=params, timeout=self.timeout)
            except requests.RequestException:
                if attempt >= self.max_retries:
                    raise
                time.sleep(min(2 ** attempt, 30))
                continue

            if response.status_code not in self.retryable_status_codes or attempt >= self.max_retries:
                return response

            time.sleep(min(2 ** attempt, 30))
        raise RuntimeError("Weather HTTP request failed unexpectedly.")


http_client = WeatherHTTPClient()


# =============================================================================
# 2. Pydantic Request Validation Model
# =============================================================================

class WeatherEnvironmentRequest(BaseModel):
    bbox: Optional[list[float]] = Field(default=None, description="[min_lon, min_lat, max_lon, max_lat] in WGS84")
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    start_date: str = Field(..., description="YYYY-MM-DD")
    end_date: str = Field(..., description="YYYY-MM-DD")
    rolling_windows: list[int] = Field(default=[7, 30], description="Rolling summary windows in days")

    @model_validator(mode="after")
    def validate_spatial_and_dates(self):
        if self.bbox is None and (self.latitude is None or self.longitude is None):
            raise ValueError("Must provide either 'bbox' [min_lon, min_lat, max_lon, max_lat] or ('latitude', 'longitude').")
        
        if self.bbox is not None:
            if len(self.bbox) != 4:
                raise ValueError("bbox must contain exactly 4 values: [min_lon, min_lat, max_lon, max_lat].")
            min_lon, min_lat, max_lon, max_lat = self.bbox
            if not -180 <= min_lon <= 180 or not -180 <= max_lon <= 180:
                raise ValueError("Longitude must be within [-180, 180].")
            if not -90 <= min_lat <= 90 or not -90 <= max_lat <= 90:
                raise ValueError("Latitude must be within [-90, 90].")
            if min_lon >= max_lon or min_lat >= max_lat:
                raise ValueError("min coordinates must be smaller than max coordinates.")
        
        try:
            d_start = date.fromisoformat(self.start_date)
            d_end = date.fromisoformat(self.end_date)
        except ValueError as e:
            raise ValueError(f"Invalid date format. Use YYYY-MM-DD: {e}")
        
        if d_start > d_end:
            raise ValueError("start_date cannot be later than end_date.")
        
        return self


# =============================================================================
# 3. Spatial Sampling & ERA5 Parameter List
# =============================================================================

ERA5_DAILY_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "apparent_temperature_mean",
    "precipitation_sum",
    "et0_fao_evapotranspiration",
    "soil_temperature_0_to_7cm_mean",
    "soil_moisture_0_to_7cm_mean",
    "shortwave_radiation_sum",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
]


def resolve_weather_sampling_points(req: WeatherEnvironmentRequest) -> tuple[list[tuple[float, float]], str, bool]:
    if req.bbox is not None:
        min_lon, min_lat, max_lon, max_lat = req.bbox
        lon_span = max_lon - min_lon
        lat_span = max_lat - min_lat
        
        # Small AOI (<= 0.5 degrees, approx 55 km) -> use centroid
        if lon_span <= 0.5 and lat_span <= 0.5:
            centroid_lat = (min_lat + max_lat) / 2.0
            centroid_lon = (min_lon + max_lon) / 2.0
            return [(centroid_lat, centroid_lon)], "centroid", True
        else:
            # Large AOI -> sample 5 representative grid locations (centroid + 4 corner offsets)
            pts = [
                ((min_lat + max_lat) / 2.0, (min_lon + max_lon) / 2.0),
                (min_lat + 0.25 * lat_span, min_lon + 0.25 * lon_span),
                (min_lat + 0.25 * lat_span, max_lon - 0.25 * lon_span),
                (max_lat - 0.25 * lat_span, min_lon + 0.25 * lon_span),
                (max_lat - 0.25 * lat_span, max_lon - 0.25 * lon_span),
            ]
            return pts, "multi_point_spatial_average", False
    else:
        return [(req.latitude, req.longitude)], "point_coordinate", True


# =============================================================================
# 4. Core Weather Processing & Environmental Indicators
# =============================================================================

def _split_date_range(
    start_date: str, end_date: str
) -> tuple[tuple[str, str] | None, tuple[str, str] | None]:
    """Split [start_date, end_date] into an archive-eligible sub-range and a
    forecast-eligible sub-range (either may be None). Days newer than
    ARCHIVE_LATENCY_DAYS from today go to the forecast API; everything older
    goes to the archive, unchanged from this tool's original behavior.
    """
    today = datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=ARCHIVE_LATENCY_DAYS)
    d_start = date.fromisoformat(start_date)
    d_end = date.fromisoformat(end_date)

    archive_range = (start_date, min(d_end, cutoff).isoformat()) if d_start <= cutoff else None
    forecast_start = max(d_start, cutoff + timedelta(days=1))
    forecast_range = (forecast_start.isoformat(), end_date) if d_end > cutoff else None
    return archive_range, forecast_range


def _request_daily(url: str, lat: float, lon: float, start_date: str, end_date: str):
    """One Open-Meteo call; returns (daily_dict, resolved_coords, error_message)."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": ERA5_DAILY_VARS,
        "timezone": "UTC",
    }
    resp = http_client.get(url, params=params)
    if not resp.ok:
        try:
            err = resp.json()
        except Exception:
            err = resp.text
        return None, None, str(err)
    data = resp.json()
    resolved = {
        "latitude": round(data.get("latitude", lat), 4),
        "longitude": round(data.get("longitude", lon), 4),
        "elevation_m": data.get("elevation", None),
    }
    return data.get("daily", {}), resolved, None


def _fetch_daily_for_point(
    lat: float, lon: float, start_date: str, end_date: str
) -> tuple[dict | None, dict | None, str, str | None]:
    """Fetch one point's full daily series across whichever endpoint(s) the
    date range needs, concatenated in chronological order. Returns
    (merged_daily, resolved_coords, data_sources_used, error_message).
    """
    archive_range, forecast_range = _split_date_range(start_date, end_date)
    daily_parts: list[dict] = []
    resolved = None
    sources: list[str] = []

    if archive_range:
        daily, resolved, err = _request_daily(CONFIG.archive_api_url, lat, lon, *archive_range)
        if err:
            return None, None, "", f"ERA5 archive request failed: {err}"
        daily_parts.append(daily)
        sources.append("era5_archive")

    if forecast_range:
        daily, resolved, err = _request_daily(CONFIG.forecast_api_url, lat, lon, *forecast_range)
        if err:
            return None, None, "", f"Open-Meteo forecast request failed: {err}"
        daily_parts.append(daily)
        sources.append("forecast_current_and_upcoming")

    if not daily_parts:
        return None, None, "", "No data source covers the requested date range."

    merged: dict[str, list] = {}
    for key in daily_parts[0]:
        merged[key] = [v for part in daily_parts for v in part.get(key, [])]

    return merged, resolved, "+".join(sources), None


def fetch_weather_environment(req: WeatherEnvironmentRequest) -> dict:
    points, method, is_centroid = resolve_weather_sampling_points(req)

    queried_coords = []
    all_daily_data = []
    data_sources_used: set[str] = set()

    for lat, lon in points:
        daily, resolved, sources_label, err = _fetch_daily_for_point(
            lat, lon, req.start_date, req.end_date
        )
        if err:
            return {"status": "error", "error": {"type": "service_error", "message": err}}

        queried_coords.append(resolved)
        all_daily_data.append(daily)
        data_sources_used.update(sources_label.split("+"))

    if not all_daily_data or not all_daily_data[0].get("time"):
        return {"status": "error", "error": {"type": "no_data", "message": "No meteorological data returned for specified range."}}
    
    dates = all_daily_data[0]["time"]
    days_count = len(dates)
    
    def get_avg_series(var_name: str) -> np.ndarray:
        series_list = []
        for d in all_daily_data:
            vals = d.get(var_name, [])
            if vals:
                series_list.append([np.nan if v is None else float(v) for v in vals])
        if not series_list:
            return np.zeros(days_count)
        arr = np.array(series_list)
        return np.nanmean(arr, axis=0)
    
    t_mean = get_avg_series("temperature_2m_mean")
    t_min = get_avg_series("temperature_2m_min")
    t_max = get_avg_series("temperature_2m_max")
    t_app = get_avg_series("apparent_temperature_mean")
    precip = get_avg_series("precipitation_sum")
    et0 = get_avg_series("et0_fao_evapotranspiration")
    soil_t = get_avg_series("soil_temperature_0_to_7cm_mean")
    soil_m = get_avg_series("soil_moisture_0_to_7cm_mean")
    radiation = get_avg_series("shortwave_radiation_sum")
    wind_max = get_avg_series("wind_speed_10m_max")
    wind_gusts = get_avg_series("wind_gusts_10m_max")
    
    # 1. Observed Factual Metrics
    total_precip_mm = round(float(np.nansum(precip)), 2)
    max_daily_precip_mm = round(float(np.nanmax(precip)), 2) if len(precip) > 0 else 0.0
    mean_temp_c = round(float(np.nanmean(t_mean)), 2)
    min_temp_c = round(float(np.nanmin(t_min)), 2)
    max_temp_c = round(float(np.nanmax(t_max)), 2)
    mean_app_temp_c = round(float(np.nanmean(t_app)), 2)
    mean_soil_temp_c = round(float(np.nanmean(soil_t)), 2)
    mean_soil_moist = round(float(np.nanmean(soil_m)), 3)
    et0_total_mm = round(float(np.nansum(et0)), 2)
    water_balance_mm = round(total_precip_mm - et0_total_mm, 2)
    mean_rad_mj = round(float(np.nanmean(radiation)), 2)
    max_wind_kmh = round(float(np.nanmax(wind_max)), 2)
    max_gusts_kmh = round(float(np.nanmax(wind_gusts)), 2)
    
    # 2. Derived Environmental Stress Indicators
    heavy_rainfall = bool(max_daily_precip_mm >= 25.0 or total_precip_mm >= 100.0)
    heat_stress = bool(np.any(t_max >= 35.0) or mean_temp_c >= 32.0)
    cold_stress = bool(np.any(t_min <= 4.0))
    moisture_deficit = bool(water_balance_mm < 0.0)
    
    if water_balance_mm >= 0.0:
        deficit_intensity = "none"
    elif water_balance_mm >= -50.0:
        deficit_intensity = "moderate"
    else:
        deficit_intensity = "severe"
        
    # 3. Rolling Summaries
    rolling_summaries = {}
    for window in req.rolling_windows:
        if days_count >= window:
            w_precip = round(float(np.nansum(precip[-window:])), 2)
            w_et0 = round(float(np.nansum(et0[-window:])), 2)
            rolling_summaries[f"{window}_day_recent"] = {
                "rainfall_sum_mm": w_precip,
                "et0_sum_mm": w_et0,
                "water_balance_mm": round(w_precip - w_et0, 2),
                "mean_temperature_c": round(float(np.nanmean(t_mean[-window:])), 2),
                "mean_soil_moisture": round(float(np.nanmean(soil_m[-window:])), 3),
            }
            
    # 4. Daily Time Series Array
    time_series = []
    for i, d_str in enumerate(dates):
        time_series.append({
            "date": d_str,
            "temp_mean_c": round(float(t_mean[i]), 2),
            "temp_min_c": round(float(t_min[i]), 2),
            "temp_max_c": round(float(t_max[i]), 2),
            "apparent_temp_mean_c": round(float(t_app[i]), 2),
            "precip_mm": round(float(precip[i]), 2),
            "et0_mm": round(float(et0[i]), 2),
            "soil_moisture_m3_m3": round(float(soil_m[i]), 3),
            "soil_temp_c": round(float(soil_t[i]), 2),
            "solar_radiation_mj_m2": round(float(radiation[i]), 2),
            "wind_speed_max_kmh": round(float(wind_max[i]), 2),
        })
        
    # Flag any day that is a genuine forecast (in the future) rather than an
    # observation, and note when the archive and forecast products were both
    # used and stitched together (a seam between two products, at worst a
    # discontinuity right at the join date).
    today_utc = datetime.now(timezone.utc).date()
    start_date_obj = date.fromisoformat(req.start_date)
    end_date_obj = date.fromisoformat(req.end_date)
    forecast_range_start = max(start_date_obj, today_utc)
    forecast_days_count = (
        max(0, (end_date_obj - forecast_range_start).days + 1) if end_date_obj >= today_utc else 0
    )

    operational_warnings = []
    if forecast_days_count > 0:
        operational_warnings.append(
            f"{forecast_days_count} day(s) in this range are today or in the future: those "
            "values are model forecasts (or a same-day nowcast), not confirmed observations."
        )
    if len(data_sources_used) > 1:
        operational_warnings.append(
            "This range was served by more than one data product (ERA5 archive and/or the "
            "forecast API) and the daily series were concatenated -- there may be a small "
            "discontinuity right at the join date."
        )

    return {
        "status": "success",
        "source": {
            "provider": "Open-Meteo",
            "dataset": "ERA5 & ERA5-Land Reanalysis",
            "data_sources_used": sorted(data_sources_used),
            "model_grid_resolution_deg": 0.1,
            "spatial_representativeness": "Meteorological reanalysis grid cell (approx 9-11 km). Not equal to satellite pixel resolution.",
        },
        "warnings": operational_warnings if operational_warnings else None,
        "spatial_context": {
            "requested_bbox": req.bbox,
            "weather_coordinates": queried_coords,
            "grid_points_count": len(queried_coords),
            "aggregation_method": method,
            "is_centroid_based": is_centroid,
        },
        "request": {
            "start_date": req.start_date,
            "end_date": req.end_date,
            "days_count": days_count,
        },
        "observed_metrics": {
            "total_rainfall_mm": total_precip_mm,
            "max_daily_rainfall_mm": max_daily_precip_mm,
            "mean_temperature_c": mean_temp_c,
            "min_temperature_c": min_temp_c,
            "max_temperature_c": max_temp_c,
            "mean_apparent_temperature_c": mean_app_temp_c,
            "mean_soil_temperature_0_to_7cm_c": mean_soil_temp_c,
            "mean_soil_moisture_0_to_7cm_m3_m3": mean_soil_moist,
            "et0_total_mm": et0_total_mm,
            "water_balance_mm": water_balance_mm,
            "mean_solar_radiation_mj_m2": mean_rad_mj,
            "max_wind_speed_kmh": max_wind_kmh,
            "max_wind_gusts_kmh": max_gusts_kmh,
        },
        "environmental_indicators": {
            "heavy_rainfall_detected": heavy_rainfall,
            "heat_stress_detected": heat_stress,
            "cold_stress_detected": cold_stress,
            "moisture_deficit_detected": moisture_deficit,
            "water_deficit_intensity": deficit_intensity,
            "interpretation_basis": "rule_based_moisture_deficit_indicator",
        },
        "interpretation_metadata": {
            "indicators_are_rule_based": True,
            "drought_diagnosis_supported": False,
            "note": "Indicators represent short-term meteorological rule-based conditions, not long-term climatological anomaly diagnostics.",
        },
        "rolling_summaries": rolling_summaries,
        "time_series": time_series,
    }


# =============================================================================
# 5. FastMCP Tool Registration & CLI Entry Point
# =============================================================================

if FastMCP is None:
    class _DummyMCP:
        def tool(self, *args, **kwargs):
            return lambda fn: fn
    mcp = _DummyMCP()
else:
    mcp = FastMCP("Tool 4: Weather & Environment Intelligence Server")

@mcp.tool(
    name="fetch_weather_environment",
    description="Fetch factual ERA5/ERA5-Land meteorological observations (temperature, rainfall, soil moisture, evapotranspiration, water balance) and derived environmental stress indicators for geospatial analysis.",
)
def mcp_fetch_weather_environment(
    start_date: str,
    end_date: str,
    bbox: Optional[list[float]] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    rolling_windows: list[int] = [7, 30],
) -> dict:
    try:
        req = WeatherEnvironmentRequest(
            bbox=bbox,
            latitude=latitude,
            longitude=longitude,
            start_date=start_date,
            end_date=end_date,
            rolling_windows=rolling_windows,
        )
        return fetch_weather_environment(req)
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
            req = WeatherEnvironmentRequest(**data)
            res = fetch_weather_environment(req)
            print(json.dumps(res, indent=2))
        else:
            print(f"Error: input file '{input_file}' not found.", file=sys.stderr)
            sys.exit(1)
    else:
        print("Tool 4: fetch_weather_environment ready. Pass a JSON configuration file or run via FastMCP.")
