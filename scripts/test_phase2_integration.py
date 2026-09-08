"""SatQuery Phase 2 Integration & Scientific Workflow Test Suite.

Rigorously tests:
- Master FastMCP Tool Registration (8/8 Tools)
- Cross-Tool Spatial Handshakes (Tool 5 -> Tool 6 -> Tool 7 -> Tool 8)
- Complete Pipeline A (Wildfire Burn Severity & Topography)
- Complete Pipeline B (Radar Flood Inundation & LULC Impact)
- Complete Pipeline C (Agricultural Drought & Canopy Stress)
using deterministic, self-consistent synthetic GeoTIFF rasters with zero network requirements.
"""

import os
import sys
import asyncio
import unittest
import shutil
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import rasterio
from rasterio.transform import from_bounds

# Add root directory to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Import FastMCP server and tools
import satquery_server
from satquery_workflows import (
    workflow_wildfire_burn_severity,
    workflow_flood_inundation_impact,
    workflow_agricultural_drought_canopy_stress,
)
from Tool_4_fetch_weather_environment.fetch_weather_environment import WeatherEnvironmentRequest
from Tool_5_compute_vegetation_indices.compute_vegetation_indices import (
    VegetationIndicesRequest,
    compute_vegetation_indices,
)
from Tool_6_inspect_geotiff_metadata.inspect_geotiff_metadata import (
    GeoTIFFInspectionRequest,
    inspect_geotiff_metadata,
)
from Tool_7_analyze_temporal_change.analyze_temporal_change import (
    TemporalChangeRequest,
    analyze_temporal_change,
)
from Tool_8_analyze_spatial_landcover_terrain.analyze_spatial_landcover_terrain import (
    SpatialLandcoverTerrainRequest,
    analyze_spatial_landcover_terrain,
)


class TestPhase2IntegrationSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = ROOT_DIR / "phase2_test_scratch"
        cls.test_dir.mkdir(parents=True, exist_ok=True)
        
        # Define 64x64 grid over Delhi NCR [77.10, 28.50, 77.30, 28.70]
        cls.width = 64
        cls.height = 64
        cls.bounds = (77.10, 28.50, 77.30, 28.70)
        cls.transform = from_bounds(cls.bounds[0], cls.bounds[1], cls.bounds[2], cls.bounds[3], cls.width, cls.height)
        cls.crs = "EPSG:4326"
        
        # 1. Generate Synthetic Multispectral Rasters (T1: Healthy vegetation, T2: Burned patch in upper left)
        cls.multi_t1_path = cls.test_dir / "synth_multispectral_t1.tif"
        cls.multi_t2_path = cls.test_dir / "synth_multispectral_t2.tif"
        
        bands_list = ["B02", "B03", "B04", "B05", "B07", "B08", "B11", "B12"]
        
        # T1 Bands: High NIR (B08 = 0.45), Low SWIR (B12 = 0.10) => High NBR = (0.45 - 0.10) / 0.55 = 0.636
        t1_data = np.zeros((8, cls.height, cls.width), dtype=np.float32)
        t1_data[0] = 0.05  # B02 Blue
        t1_data[1] = 0.08  # B03 Green
        t1_data[2] = 0.06  # B04 Red
        t1_data[3] = 0.12  # B05 RE1
        t1_data[4] = 0.28  # B07 RE3
        t1_data[5] = 0.45  # B08 NIR
        t1_data[6] = 0.18  # B11 SWIR1
        t1_data[7] = 0.10  # B12 SWIR2
        
        meta = {
            "driver": "GTiff",
            "height": cls.height,
            "width": cls.width,
            "count": 8,
            "dtype": "float32",
            "crs": cls.crs,
            "transform": cls.transform,
            "nodata": -9999.0,
        }
        
        with rasterio.open(cls.multi_t1_path, "w", **meta) as dst:
            for idx in range(8):
                dst.write(t1_data[idx], idx + 1)
                dst.set_band_description(idx + 1, bands_list[idx])
                
        # T2 Bands: In top-left 32x32 area, drop NIR to 0.10 and increase SWIR2 to 0.35 (Severe Burn)
        t2_data = t1_data.copy()
        t2_data[5, :32, :32] = 0.10  # Drop NIR
        t2_data[7, :32, :32] = 0.35  # Increase SWIR2
        
        with rasterio.open(cls.multi_t2_path, "w", **meta) as dst:
            for idx in range(8):
                dst.write(t2_data[idx], idx + 1)
                dst.set_band_description(idx + 1, bands_list[idx])
                
        # 2. Generate Synthetic SAR Rasters (T1: Dry land ~ -10 dB, T2: Flooded bottom-right ~ -22 dB)
        cls.sar_t1_path = cls.test_dir / "synth_sar_t1.tif"
        cls.sar_t2_path = cls.test_dir / "synth_sar_t2.tif"
        
        sar_meta = meta.copy()
        sar_meta.update({"count": 2})
        
        sar_t1 = np.full((2, cls.height, cls.width), -10.0, dtype=np.float32)
        sar_t1[1] = -16.0  # VH
        
        with rasterio.open(cls.sar_t1_path, "w", **sar_meta) as dst:
            dst.write(sar_t1[0], 1)
            dst.write(sar_t1[1], 2)
            dst.set_band_description(1, "VV_dB")
            dst.set_band_description(2, "VH_dB")
            
        sar_t2 = sar_t1.copy()
        sar_t2[0, 32:, 32:] = -22.0  # Strong backscatter drop (water inundation)
        sar_t2[1, 32:, 32:] = -28.0
        
        with rasterio.open(cls.sar_t2_path, "w", **sar_meta) as dst:
            dst.write(sar_t2[0], 1)
            dst.write(sar_t2[1], 2)
            dst.set_band_description(1, "VV_dB")
            dst.set_band_description(2, "VH_dB")
            
        # 3. Generate Synthetic LULC Raster (ESA WorldCover classes: 10=Tree Cover, 40=Cropland, 50=Built-up)
        cls.lulc_path = cls.test_dir / "synth_lulc.tif"
        lulc_meta = meta.copy()
        lulc_meta.update({"count": 1, "dtype": "int32", "nodata": -1})
        
        lulc_data = np.full((cls.height, cls.width), 40, dtype=np.int32)  # Default Cropland
        lulc_data[:32, :32] = 10   # Top-left is Forest/Tree Cover
        lulc_data[32:, :32] = 50   # Bottom-left is Built-up
        lulc_data[32:, 32:] = 40   # Bottom-right is Cropland
        
        with rasterio.open(cls.lulc_path, "w", **lulc_meta) as dst:
            dst.write(lulc_data, 1)
            
        # 4. Generate Synthetic DEM Raster (Elevation 200m to 600m with realistic slope)
        cls.dem_path = cls.test_dir / "synth_dem.tif"
        dem_meta = meta.copy()
        dem_meta.update({"count": 1, "dtype": "float32", "nodata": -9999.0})
        
        y_grad, x_grad = np.mgrid[0:cls.height, 0:cls.width]
        dem_data = (200.0 + (x_grad * 4.0) + (y_grad * 3.0)).astype(np.float32)
        
        with rasterio.open(cls.dem_path, "w", **dem_meta) as dst:
            dst.write(dem_data, 1)

    @classmethod
    def tearDownClass(cls):
        # Clean up scratch files after tests
        if cls.test_dir.exists():
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_01_master_fastmcp_server_tools(self):
        """Verify FastMCP server registers all 8 tools cleanly."""
        tools = asyncio.run(satquery_server.mcp.list_tools())
        registered_tools = [t.name for t in tools]
        expected_tools = [
            "fetch_optical_imagery",
            "fetch_multispectral_imagery",
            "fetch_sar_imagery",
            "fetch_weather_environment",
            "compute_vegetation_indices",
            "inspect_geotiff_metadata",
            "analyze_temporal_change",
            "analyze_spatial_landcover_terrain",
        ]
        for t in expected_tools:
            self.assertIn(t, registered_tools, f"Tool '{t}' missing from FastMCP master server registration.")

    def test_02_synthetic_spectral_indices_computation(self):
        """Verify Tool 5 computes spectral indices on synthetic 8-band raster."""
        req = VegetationIndicesRequest(
            file_path=str(self.multi_t1_path),
            indices=["NDVI", "NBR", "NDMI", "EVI"],
            output_dir=str(self.test_dir / "out_indices")
        )
        res = compute_vegetation_indices(req)
        self.assertEqual(res["status"], "success")
        self.assertIn("NDVI", res["statistics"])
        self.assertIn("NBR", res["statistics"])
        self.assertAlmostEqual(res["statistics"]["NBR"]["mean"], 0.636, places=2)

    def test_03_preflight_raster_inspection(self):
        """Verify Tool 6 detects grid compatibility between T1 and T2 rasters."""
        req = GeoTIFFInspectionRequest(
            file_path=str(self.multi_t2_path),
            compare_with=str(self.multi_t1_path),
            calculate_statistics=True
        )
        res = inspect_geotiff_metadata(req)
        self.assertEqual(res["status"], "success")
        self.assertTrue(res["quality"]["is_valid_for_ml"])
        self.assertTrue(res["compatibility"]["pixelwise_operation_ready"])

    def test_04_temporal_differential_change_detection(self):
        """Verify Tool 7 detects drop in NBR in the upper-left quadrant."""
        req_t1 = VegetationIndicesRequest(file_path=str(self.multi_t1_path), indices=["NBR"], output_dir=str(self.test_dir))
        res_t1 = compute_vegetation_indices(req_t1)
        req_t2 = VegetationIndicesRequest(file_path=str(self.multi_t2_path), indices=["NBR"], output_dir=str(self.test_dir))
        res_t2 = compute_vegetation_indices(req_t2)
        
        t7_req = TemporalChangeRequest(
            raster_before_path=res_t1["data"]["file_path"],
            raster_after_path=res_t2["data"]["file_path"],
            threshold_type="absolute",
            threshold_value=0.10,
            mask_encoding="severity_5class",
            output_dir=str(self.test_dir)
        )
        t7_res = analyze_temporal_change(t7_req)
        self.assertEqual(t7_res["status"], "success")
        self.assertGreater(t7_res["severity_distribution"]["major_decrease"]["pixel_count"], 900)

    def test_05_zonal_landcover_terrain_handshake(self):
        """Verify Tool 8 correctly cross-tabulates change mask against LULC and DEM."""
        req_t1 = VegetationIndicesRequest(file_path=str(self.multi_t1_path), indices=["NBR"], output_dir=str(self.test_dir))
        res_t1 = compute_vegetation_indices(req_t1)
        req_t2 = VegetationIndicesRequest(file_path=str(self.multi_t2_path), indices=["NBR"], output_dir=str(self.test_dir))
        res_t2 = compute_vegetation_indices(req_t2)
        
        t7_req = TemporalChangeRequest(
            raster_before_path=res_t1["data"]["file_path"],
            raster_after_path=res_t2["data"]["file_path"],
            threshold_value=0.10,
            mask_encoding="severity_5class",
            output_dir=str(self.test_dir)
        )
        t7_res = analyze_temporal_change(t7_req)
        
        t8_req = SpatialLandcoverTerrainRequest(
            lulc_raster_path=str(self.lulc_path),
            dem_raster_path=str(self.dem_path),
            zone_mask_path=t7_res["generated_products"]["change_mask_path"],
            output_dir=str(self.test_dir)
        )
        t8_res = analyze_spatial_landcover_terrain(t8_req)
        self.assertEqual(t8_res["status"], "success")
        self.assertIn("-2", t8_res["zonal_cross_tabulation"])
        # Tree cover should dominate the high severity loss zone
        tree_impact = t8_res["zonal_cross_tabulation"]["-2"]["landcover_impact_breakdown"]["Tree cover"]
        self.assertEqual(tree_impact["percentage_of_zone"], 100.0)

    def test_06_pipeline_a_wildfire_burn_severity_workflow(self):
        """Verify end-to-end execution of Pipeline A."""
        res = workflow_wildfire_burn_severity(
            pre_raster_path=str(self.multi_t1_path),
            post_raster_path=str(self.multi_t2_path),
            lulc_raster_path=str(self.lulc_path),
            dem_raster_path=str(self.dem_path),
            output_dir=str(self.test_dir / "pipeline_a_demo")
        )
        self.assertEqual(res["status"], "success")
        self.assertGreater(res["executive_summary"]["affected_forest_hectares"], 0.0)
        self.assertEqual(len(res["audit_trail"]), 5)

    def test_07_pipeline_b_flood_inundation_workflow(self):
        """Verify end-to-end execution of Pipeline B."""
        weather_req = WeatherEnvironmentRequest(
            latitude=28.61,
            longitude=77.20,
            start_date="2025-07-01",
            end_date="2025-07-10"
        )
        res = workflow_flood_inundation_impact(
            sar_pre_raster_path=str(self.sar_t1_path),
            sar_post_raster_path=str(self.sar_t2_path),
            lulc_raster_path=str(self.lulc_path),
            weather_request=weather_req,
            dem_raster_path=str(self.dem_path),
            output_dir=str(self.test_dir / "pipeline_b_demo")
        )
        self.assertEqual(res["status"], "success")
        self.assertGreater(res["executive_summary"]["total_flood_inundation_km2"], 0.0)

    def test_08_pipeline_c_agricultural_drought_workflow(self):
        """Verify end-to-end execution of Pipeline C."""
        weather_req = WeatherEnvironmentRequest(
            latitude=28.61,
            longitude=77.20,
            start_date="2025-05-01",
            end_date="2025-05-20"
        )
        res = workflow_agricultural_drought_canopy_stress(
            multispectral_raster_path=str(self.multi_t1_path),
            weather_request=weather_req,
            output_dir=str(self.test_dir / "pipeline_c_demo")
        )
        self.assertEqual(res["status"], "success")
        self.assertIn("drought_risk_tier", res["executive_summary"])


if __name__ == "__main__":
    unittest.main()
