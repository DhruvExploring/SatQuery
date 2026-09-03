"""
Tests for the FastAPI layer (Milestone 3).

Uses FastAPI's TestClient which runs the app in-process.
All graph calls go through the real LangGraph graph but with
SATQUERY_MOCK_TOOLS=true (default), so no network is needed.

We test the HTTP contract, not the graph logic — that is already
covered by test_graph_mock.py.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
def test_health_returns_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /api/v1/query
# ---------------------------------------------------------------------------
def test_query_fetch_succeeds():
    resp = client.post(
        "/api/v1/query",
        json={
            "query": "Fetch Sentinel-2 imagery for Delhi",
            "bbox": [77.1, 28.5, 77.3, 28.7],
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["final_answer"] is not None
    assert "GeoTIFF" in body["final_answer"] or "tif" in body["final_answer"]
    assert body["plan"]["tool"] == "fetch_satellite_imagery"
    assert len(body["tool_results"]) == 1


def test_query_without_bbox_returns_clarify():
    resp = client.post(
        "/api/v1/query",
        json={"query": "Fetch Sentinel-2 imagery for Delhi"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "clarify"
    assert "bounding box" in body["final_answer"].lower()
    assert body["tool_results"] == []


def test_query_invalid_bbox_returns_error():
    resp = client.post(
        "/api/v1/query",
        json={
            "query": "Fetch Sentinel-2 imagery for Delhi",
            "bbox": [200, 28.5, 77.3, 28.7],   # invalid longitude
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "error"
    assert len(body["errors"]) > 0
    assert body["tool_results"] == []


def test_query_empty_string_rejected_by_pydantic():
    """Pydantic rejects empty query before it reaches the graph."""
    resp = client.post("/api/v1/query", json={"query": ""})
    assert resp.status_code == 422   # FastAPI/Pydantic validation error


def test_query_missing_query_field_rejected():
    resp = client.post("/api/v1/query", json={"bbox": [77.1, 28.5, 77.3, 28.7]})
    assert resp.status_code == 422
