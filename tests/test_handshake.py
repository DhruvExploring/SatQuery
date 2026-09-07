"""Handshake loop: chained tools, Tool 6 gate, missions, hop cap."""

from __future__ import annotations

from backend.orchestrator.graph import build_graph, invoke_satquery
from backend.orchestrator.state import empty_state

DELHI = [77.10, 28.50, 77.30, 28.70]
LULC = "dummy_lulc.tif"


def _run(state):
    return invoke_satquery(state, build_graph())


def _tools(result) -> list[str]:
    return [item["tool"] for item in result.get("tool_results") or []]


def test_ndvi_with_bbox_fetches_multispectral_then_indices():
    result = _run(
        empty_state(
            query="Compute NDVI vegetation indices",
            bbox=DELHI,
            start_date="2025-01-01",
            end_date="2025-01-31",
        )
    )
    assert result["status"] == "success"
    assert result["intent"] == "chain_indices"
    assert _tools(result) == [
        "fetch_multispectral_imagery",
        "compute_vegetation_indices",
    ]
    multi_path = result["tool_results"][0]["result"]["data"]["file_path"]
    assert result["tool_results"][1]["result"]["request"]["file_path"] == multi_path
    assert result["tool_results"][0]["result"]["request"]["bands"] == [
        "B02",
        "B03",
        "B04",
        "B05",
        "B07",
        "B08",
        "B11",
        "B12",
    ]


def test_temporal_two_dates_and_lulc_runs_full_chain():
    result = _run(
        empty_state(
            query="Detect deforestation and vegetation loss before and after",
            bbox=DELHI,
            start_date="2024-01-01",
            end_date="2024-01-31",
            post_start_date="2025-01-01",
            post_end_date="2025-01-31",
            lulc_raster_path=LULC,
        )
    )
    assert result["status"] == "success"
    assert result["intent"] == "chain_temporal"
    assert _tools(result) == [
        "fetch_multispectral_imagery",
        "fetch_multispectral_imagery",
        "compute_vegetation_indices",
        "compute_vegetation_indices",
        "inspect_geotiff_metadata",
        "analyze_temporal_change",
        "analyze_spatial_landcover_terrain",
    ]
    t1_args = result["tool_results"][0]["result"]["request"]
    t2_args = result["tool_results"][1]["result"]["request"]
    assert t1_args["start_date"] == "2024-01-01"
    assert t2_args["start_date"] == "2025-01-01"
    mask = result["tool_results"][5]["result"]["generated_products"]["change_mask_path"]
    assert result["tool_results"][6]["result"]["request"]["zone_mask_path"] == mask
    assert result["last_change_mask_path"] == mask


def test_tool6_gate_skips_tool7_when_not_pixelwise_ready(monkeypatch):
    import backend.orchestrator.nodes as nodes
    import backend.tools.executor as executor

    original = nodes.execute_tool

    def _gated(name, args):
        result = original(name, args)
        if name == "inspect_geotiff_metadata":
            result = dict(result)
            result["compatibility"] = {"pixelwise_operation_ready": False}
        return result

    monkeypatch.setattr(executor, "execute_tool", _gated)
    monkeypatch.setattr(nodes, "execute_tool", _gated)

    result = _run(
        empty_state(
            query="Analyze temporal change between these two rasters",
            raster_before_path="dummy_before.tif",
            raster_after_path="dummy_after.tif",
        )
    )
    assert "analyze_temporal_change" not in _tools(result)
    assert _tools(result) == ["inspect_geotiff_metadata"]
    assert result["status"] == "error"
    assert any("pixelwise_operation_ready" in err for err in result["errors"])


def test_optical_sar_recommended_appends_tool3(monkeypatch):
    import backend.orchestrator.nodes as nodes
    import backend.tools.executor as executor

    original = nodes.execute_tool

    def _flagged(name, args):
        result = original(name, args)
        if name == "fetch_optical_imagery":
            result = dict(result)
            result["flags"] = {
                "sar_recommended": True,
                "optical_quality_poor": False,
            }
        return result

    monkeypatch.setattr(executor, "execute_tool", _flagged)
    monkeypatch.setattr(nodes, "execute_tool", _flagged)

    result = _run(
        empty_state(
            query="Fetch Sentinel-2 optical imagery for Delhi",
            bbox=DELHI,
            start_date="2025-01-01",
            end_date="2025-01-31",
        )
    )
    assert result["status"] == "success"
    assert _tools(result) == ["fetch_optical_imagery", "fetch_sar_imagery"]


def test_wildfire_mission_calls_workflow_once(monkeypatch):
    called: list[str] = []

    import backend.orchestrator.nodes as nodes
    import backend.tools.executor as executor

    original = nodes.execute_tool

    def _track(name, args):
        called.append(name)
        return original(name, args)

    monkeypatch.setattr(executor, "execute_tool", _track)
    monkeypatch.setattr(nodes, "execute_tool", _track)

    result = _run(
        empty_state(
            query="Map wildfire burn severity and fire scar",
            raster_before_path="dummy_pre.tif",
            raster_after_path="dummy_post.tif",
            lulc_raster_path=LULC,
        )
    )
    assert result["status"] == "success"
    assert result["intent"] == "mission_wildfire"
    assert called == ["workflow_wildfire_burn_severity"]
    assert _tools(result) == ["workflow_wildfire_burn_severity"]


def test_flood_mission_fetches_sar_pair_then_workflow():
    result = _run(
        empty_state(
            query="Assess flood inundation impact",
            bbox=DELHI,
            start_date="2024-07-01",
            end_date="2024-07-10",
            post_start_date="2024-07-20",
            post_end_date="2024-07-31",
            lulc_raster_path=LULC,
        )
    )
    assert result["status"] == "success"
    assert result["intent"] == "mission_flood"
    assert _tools(result) == [
        "fetch_sar_imagery",
        "fetch_sar_imagery",
        "workflow_flood_inundation_impact",
    ]
    assert result["plan"]["tool"] == "workflow_flood_inundation_impact"


def test_handshake_cannot_exceed_max_hops(monkeypatch):
    import backend.orchestrator.handshake as handshake

    monkeypatch.setattr(handshake, "MAX_HANDSHAKE_HOPS", 1)

    result = _run(
        empty_state(
            query="Compute NDVI vegetation indices",
            bbox=DELHI,
        )
    )
    assert result["status"] == "error"
    assert any("max hops" in err.lower() for err in result["errors"])
    assert _tools(result) == ["fetch_multispectral_imagery"]
    assert "compute_vegetation_indices" not in _tools(result)
