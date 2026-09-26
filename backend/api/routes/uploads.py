"""File upload endpoint for user-supplied GeoTIFF/TIFF rasters.

POST /api/v1/query only ever accepts a *path* to a file already on the
server's filesystem (see resolve_data_path in backend/api/models.py) — this
endpoint is what turns a browser file picker into that path.
"""

from __future__ import annotations

import uuid
from pathlib import Path

# pyrefly: ignore [missing-import]
from fastapi import APIRouter, HTTPException, Query, UploadFile

from backend.orchestrator.ingest_graph import run_ingest

router = APIRouter()

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_UPLOAD_DIR = _PROJECT_ROOT / "uploads"
_ALLOWED_SUFFIXES = {".tif", ".tiff"}
_MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB — generous for a GeoTIFF, bounds abuse
_CHUNK_SIZE = 1024 * 1024


def resolve_temp_upload_path(raw_path: str) -> Path | None:
    """Validate that the path is strictly inside _UPLOAD_DIR and not escaping it.

    Protects permanent satellite datasets by only allowing files within the
    temporary uploads directory.
    """
    if not raw_path or not raw_path.strip():
        return None
    try:
        p = Path(raw_path)
        candidate = (_PROJECT_ROOT / p).resolve() if not p.is_absolute() else p.resolve()
        upload_dir_resolved = _UPLOAD_DIR.resolve()
        if candidate.is_relative_to(upload_dir_resolved) and candidate != upload_dir_resolved:
            return candidate
    except Exception:
        pass
    return None


def delete_temp_upload_file(raw_path: str) -> bool:
    """Delete a temporary uploaded file and its .kb.json sibling if it exists.

    Never touches permanent satellite datasets.
    """
    candidate = resolve_temp_upload_path(raw_path)
    if not candidate:
        return False
    deleted = False
    if candidate.is_file():
        candidate.unlink(missing_ok=True)
        deleted = True
    kb_path = candidate.with_suffix(".kb.json")
    if kb_path.is_file():
        kb_path.unlink(missing_ok=True)
    return deleted


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


@router.delete("/api/v1/upload-raster", tags=["uploads"])
async def delete_upload_raster(
    path: str = Query(..., description="Path of temporary uploaded raster to delete"),
) -> dict:
    """Delete a user-supplied temporary raster and its associated knowledge base.

    Rejects any request targeting permanent satellite datasets outside uploads/.
    """
    candidate = resolve_temp_upload_path(path)
    if not candidate:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Only temporary files in the uploads directory can be deleted.",
        )
    deleted = delete_temp_upload_file(path)
    return {"ok": True, "path": path, "deleted": deleted}
