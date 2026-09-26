from __future__ import annotations

from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_UPLOAD_DIR = _PROJECT_ROOT / "uploads"


def test_conversation_reset_endpoint_basic():
    resp = client.post("/api/v1/conversation/reset", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["message"] == "Conversation context reset."
    assert data["deleted_temp_files"] == []


def test_conversation_reset_alias_endpoint():
    resp = client.post("/api/v1/reset", json={"session_id": "test-session-123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_delete_temporary_uploaded_file():
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    test_file = _UPLOAD_DIR / "test_temp_scene_123.tif"
    test_kb = _UPLOAD_DIR / "test_temp_scene_123.kb.json"
    test_file.write_bytes(b"dummy geotiff bytes")
    test_kb.write_text('{"place_name": "Test"}')

    assert test_file.is_file()
    assert test_kb.is_file()

    rel_path = "uploads/test_temp_scene_123.tif"
    resp = client.delete(f"/api/v1/upload-raster?path={rel_path}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["deleted"] is True

    # Both file and .kb.json must be deleted
    assert not test_file.exists()
    assert not test_kb.exists()


def test_permanent_satellite_dataset_is_not_deleted():
    # A path outside uploads/ (e.g. output_optical or root) must be rejected
    perm_dir = _PROJECT_ROOT / "output_optical"
    perm_dir.mkdir(parents=True, exist_ok=True)
    perm_file = perm_dir / "permanent_sample_dataset.tif"
    perm_file.write_bytes(b"permanent satellite dataset")

    try:
        rel_path = "output_optical/permanent_sample_dataset.tif"
        resp = client.delete(f"/api/v1/upload-raster?path={rel_path}")
        assert resp.status_code == 403
        # Permanent file must still exist
        assert perm_file.is_file()
    finally:
        perm_file.unlink(missing_ok=True)


def test_conversation_reset_cleans_temporary_files_only():
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = _UPLOAD_DIR / "temp_convo_scene.tif"
    temp_kb = _UPLOAD_DIR / "temp_convo_scene.kb.json"
    temp_file.write_bytes(b"temp raster")
    temp_kb.write_text('{"temp": true}')

    perm_dir = _PROJECT_ROOT / "output_optical"
    perm_dir.mkdir(parents=True, exist_ok=True)
    perm_file = perm_dir / "perm_convo_scene.tif"
    perm_file.write_bytes(b"permanent raster")

    try:
        resp = client.post(
            "/api/v1/conversation/reset",
            json={
                "session_id": "sess-abc",
                "temp_files": [
                    "uploads/temp_convo_scene.tif",
                    "output_optical/perm_convo_scene.tif",
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "uploads/temp_convo_scene.tif" in data["deleted_temp_files"]
        assert "output_optical/perm_convo_scene.tif" not in data["deleted_temp_files"]

        # Temp file was deleted
        assert not temp_file.exists()
        assert not temp_kb.exists()

        # Permanent file was protected and NOT deleted
        assert perm_file.is_file()
    finally:
        temp_file.unlink(missing_ok=True)
        temp_kb.unlink(missing_ok=True)
        perm_file.unlink(missing_ok=True)
