"""Raster asset endpoints for the frontend: rendered PNG previews and raw downloads.

Both endpoints only serve files that resolve inside the SatQuery project root —
never an arbitrary absolute filesystem path — since this is an unauthenticated,
publicly reachable file-serving surface.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response

from backend.api.models import resolve_data_path

router = APIRouter()

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _resolve_safe_path(raw_path: str) -> Path:
    resolved = resolve_data_path(raw_path)
    if not resolved:
        raise HTTPException(status_code=400, detail="path is required.")
    candidate = Path(resolved).resolve()
    if not candidate.is_relative_to(_PROJECT_ROOT):
        raise HTTPException(status_code=403, detail="path must be inside the SatQuery project.")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {raw_path}")
    return candidate


@router.get("/api/v1/raster-preview", tags=["rasters"])
def raster_preview(
    path: str = Query(..., description="GeoTIFF path, relative to the SatQuery root or absolute."),
    size: int = Query(1024, ge=64, le=4096, description="Longest edge of the rendered preview, in pixels."),
) -> Response:
    from backend.rendering.raster_preview import render_geotiff_preview

    candidate = _resolve_safe_path(path)
    try:
        png_bytes = render_geotiff_preview(str(candidate), size=size)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not render preview: {exc}") from exc
    return Response(content=png_bytes, media_type="image/png")


@router.get("/api/v1/raster-file", tags=["rasters"])
def raster_file(
    path: str = Query(..., description="Raster path, relative to the SatQuery root or absolute."),
) -> FileResponse:
    candidate = _resolve_safe_path(path)
    media_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
    return FileResponse(candidate, media_type=media_type, filename=candidate.name)
