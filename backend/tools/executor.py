"""Tool execution for Tools 1–4 — always calls the real Python tool functions.

No mock-tools flag. Unit tests stub this module via pytest monkeypatch if needed.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Callable

from backend.config.settings import settings
from backend.orchestrator.registry import (
    TOOL_MULTI,
    TOOL_OPTICAL,
    TOOL_SAR,
    TOOL_WEATHER,
)

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _wrap_tool_error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ValueError):
        return {
            "status": "error",
            "error": {"type": "validation_error", "message": str(exc)},
        }
    if isinstance(exc, ImportError):
        logger.error(
            "SATQUERY_IMPORT_ERROR could not import tool module "
            "interpreter=%s cwd=%s",
            sys.executable,
            Path.cwd(),
            exc_info=True,
        )
        return {
            "status": "error",
            "error": {
                "type": "import_error",
                "message": (
                    f"Could not import tool module: {exc}. "
                    f"Interpreter: {sys.executable}. "
                    "Install project requirements into this environment "
                    "(from SatQuery root: python -m pip install -r requirements.txt)."
                ),
            },
        }
    return {
        "status": "error",
        "error": {"type": "service_error", "message": str(exc)},
    }


def _run_optical(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from Tool_1_fetch_optical_imagery.fetch_optical_imagery import (
            OpticalSatelliteRequest,
            fetch_optical_imagery,
        )

        req = OpticalSatelliteRequest(
            bbox=args.get("bbox") or [],
            start_date=args.get("start_date") or settings.default_start_date,
            end_date=args.get("end_date") or settings.default_end_date,
            max_cloud_cover=float(args.get("max_cloud_cover") or settings.default_max_cloud_cover),
            width=int(args.get("width") or settings.default_width),
            height=int(args.get("height") or settings.default_height),
            crs=args.get("crs") or settings.default_crs,
        )
        return fetch_optical_imagery(req)
    except Exception as exc:  # noqa: BLE001
        return _wrap_tool_error(exc)


def _run_multispectral(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from Tool_2_fetch_multispectral_imagery.fetch_multispectral_imagery import (
            MultispectralSatelliteRequest,
            fetch_multispectral_imagery,
        )

        req = MultispectralSatelliteRequest(
            bbox=args.get("bbox") or [],
            start_date=args.get("start_date") or settings.default_start_date,
            end_date=args.get("end_date") or settings.default_end_date,
            bands=args.get("bands") or ["B02", "B03", "B04", "B08"],
            max_cloud_cover=float(args.get("max_cloud_cover") or settings.default_max_cloud_cover),
            width=int(args.get("width") or settings.default_width),
            height=int(args.get("height") or settings.default_height),
            crs=args.get("crs") or settings.default_crs,
        )
        return fetch_multispectral_imagery(req)
    except Exception as exc:  # noqa: BLE001
        return _wrap_tool_error(exc)


def _run_sar(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from Tool_3_fetch_sar_imagery.fetch_sar_imagery import (
            SARSatelliteRequest,
            fetch_sar_imagery,
        )

        req = SARSatelliteRequest(
            bbox=args.get("bbox") or [],
            start_date=args.get("start_date") or settings.default_start_date,
            end_date=args.get("end_date") or settings.default_end_date,
            scene_selection=args.get("scene_selection") or "most_recent",
            polarization=args.get("polarization") or ["VV", "VH"],
            orbit_direction=args.get("orbit_direction") or "BOTH",
            width=int(args.get("width") or settings.default_width),
            height=int(args.get("height") or settings.default_height),
            crs=args.get("crs") or settings.default_crs,
        )
        return fetch_sar_imagery(req)
    except Exception as exc:  # noqa: BLE001
        return _wrap_tool_error(exc)


def _run_weather(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from Tool_4_fetch_weather_environment.fetch_weather_environment import (
            WeatherEnvironmentRequest,
            fetch_weather_environment,
        )

        req = WeatherEnvironmentRequest(
            bbox=args.get("bbox"),
            latitude=args.get("latitude"),
            longitude=args.get("longitude"),
            start_date=args.get("start_date") or settings.default_start_date,
            end_date=args.get("end_date") or settings.default_end_date,
            rolling_windows=args.get("rolling_windows") or [7, 30],
        )
        return fetch_weather_environment(req)
    except Exception as exc:  # noqa: BLE001
        return _wrap_tool_error(exc)


_EXECUTORS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    TOOL_OPTICAL: _run_optical,
    TOOL_MULTI: _run_multispectral,
    TOOL_SAR: _run_sar,
    TOOL_WEATHER: _run_weather,
}


def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Dispatch to a real Tool_1..4 implementation by name."""
    executor = _EXECUTORS.get(name)
    if executor is None:
        return {
            "status": "error",
            "error": {
                "type": "unknown_tool",
                "message": f"No executor is registered for tool '{name}'.",
            },
        }
    return executor(args)
