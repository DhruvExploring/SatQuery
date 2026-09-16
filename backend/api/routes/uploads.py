"""File upload endpoint for user-supplied GeoTIFF/TIFF rasters.

POST /api/v1/query only ever accepts a *path* to a file already on the
server's filesystem (see resolve_data_path in backend/api/models.py) — this
endpoint is what turns a browser file picker into that path.
"""

from __future__ import annotations

import uuid
from pathlib import Path

# pyrefly: ignore [missing-import]
from fastapi import APIRouter, HTTPException, UploadFile

from backend.orchestrator.ingest_graph import run_ingest

router = APIRouter()

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_UPLOAD_DIR = _PROJECT_ROOT / "uploads"
_ALLOWED_SUFFIXES = {".tif", ".tiff"}
_MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB — generous for a GeoTIFF, bounds abuse
_CHUNK_SIZE = 1024 * 1024


@router.post("/api/v1/upload-raster", tags=["uploads"])
async def upload_raster(file: UploadFile) -> dict:
    # Path(...).name strips any directory components the client sent, so a
    # filename like "../../etc/passwd" can never escape _UPLOAD_DIR.
    original_name = Path(file.filename or "").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="Only .tif/.tiff files are accepted.")

    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    # A generated name avoids both path-traversal tricks and same-name
    # collisions between different uploads.
    safe_name = f"{uuid.uuid4().hex}{suffix}"
    destination = _UPLOAD_DIR / safe_name

    size = 0
    try:
        with destination.open("wb") as out:
            while chunk := await file.read(_CHUNK_SIZE):
                size += len(chunk)
                if size > _MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="File too large (max 500 MB).")
                out.write(chunk)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc

    ingest_result = run_ingest(str(destination))
    if not ingest_result["ok"]:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=ingest_result["error"])

    return {
        "path": f"uploads/{safe_name}",
        "original_filename": original_name,
        "size_bytes": size,
        "knowledge_base": ingest_result["knowledge_base"],
    }
