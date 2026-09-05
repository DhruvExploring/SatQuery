"""SatQuery Autonomous Multi-Tool Chained Workflows.

Implements high-level multi-tool scientific pipelines orchestrating Tools 1 through 8:
- Pipeline A: Wildfire Burn Severity, Slope Risk & Forest Loss (Tool 5 -> Tool 6 -> Tool 7 -> Tool 8)
- Pipeline B: Radar Flood Inundation & LULC Impact Assessment (Tool 6 -> Tool 7 -> Tool 4 -> Tool 8)
- Pipeline C: Agricultural Drought & Biophysical Canopy Stress (Tool 5 -> Tool 4 -> Correlation Engine)
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Union, Any

# Ensure Root Tools directory is accessible
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Tool_4_fetch_weather_environment.fetch_weather_environment import (
    WeatherEnvironmentRequest,
    fetch_weather_environment,
)
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


# =============================================================================
# Pipeline A: Wildfire Burn Severity & Topographic Risk Assessment
# =============================================================================

def workflow_wildfire_burn_severity(
    pre_raster_path: str,
    post_raster_path: str,
    lulc_raster_path: str,
    dem_raster_path: Optional[str] = None,
    output_dir: Optional[str] = None
) -> Dict[str, Any]:
    """Chains Tool 5 (NBR) -> Tool 6 (QA) -> Tool 7 (Delta NBR) -> Tool 8 (LULC & Slope Impact).
    
    1. Computes Normalized Burn Ratio (NBR) for both pre- and post-fire observations.
    2. Runs Tool 6 QA to confirm pixel-wise grid compatibility between NBR rasters.
    3. Runs Tool 7 differential change detection with 5-class severity encoding.
    4. Runs Tool 8 zonal cross-tabulation of burn severity against LULC and DEM slope.
    """
    workflow_start = datetime.now(timezone.utc).isoformat()
    out_path = Path(output_dir) if output_dir else ROOT_DIR / "phase2_demonstrations" / "pipeline_a_wildfire"
    out_path.mkdir(parents=True, exist_ok=True)
    
    audit_trail = []
    
    # Step 1: Tool 5 - Compute NBR on Pre-Fire Raster
    t5_pre_req = VegetationIndicesRequest(
        file_path=pre_raster_path,
        indices=["NBR"],
        output_dir=str(out_path)
    )
    t5_pre_res = compute_vegetation_indices(t5_pre_req)
    nbr_pre_file = t5_pre_res["data"]["file_path"]
    audit_trail.append({"step": "1_pre_fire_nbr", "tool": "Tool_5", "output_file": nbr_pre_file})
    
    # Step 1b: Tool 5 - Compute NBR on Post-Fire Raster
    t5_post_req = VegetationIndicesRequest(
        file_path=post_raster_path,
        indices=["NBR"],
        output_dir=str(out_path)
    )
    t5_post_res = compute_vegetation_indices(t5_post_req)
    nbr_post_file = t5_post_res["data"]["file_path"]
    audit_trail.append({"step": "1_post_fire_nbr", "tool": "Tool_5", "output_file": nbr_post_file})
    
    # Step 2: Tool 6 - Inspect Pre-Flight Compatibility
    t6_req = GeoTIFFInspectionRequest(
        file_path=nbr_post_file,
        compare_with=nbr_pre_file,
        calculate_statistics=True
    )
    t6_res = inspect_geotiff_metadata(t6_req)
    compat = t6_res.get("compatibility", {})
    audit_trail.append({"step": "2_pre_flight_qa", "tool": "Tool_6", "grid_aligned": compat.get("pixelwise_operation_ready", True)})
    
    # Step 3: Tool 7 - Differential Temporal Change on NBR (Delta NBR)
    t7_req = TemporalChangeRequest(
        raster_before_path=nbr_pre_file,
        raster_after_path=nbr_post_file,
        band_selection=1,
        threshold_type="absolute",
        threshold_value=0.10,
        mask_encoding="severity_5class",
        output_dir=str(out_path),
        generate_difference_raster=True,
        generate_change_mask=True
    )
    t7_res = analyze_temporal_change(t7_req)
    change_mask_path = t7_res["generated_products"]["change_mask_path"]
    diff_raster_path = t7_res["generated_products"]["difference_raster_path"]
    audit_trail.append({"step": "3_delta_nbr_change_detection", "tool": "Tool_7", "change_mask": change_mask_path})
    
    # Step 4: Tool 8 - Zonal Landcover & Terrain Impact (The Tool 7 -> Tool 8 Handshake)
    burn_legend = {
        -2: "High Severity Burn / Canopy Destruction",
        -1: "Moderate-Low Severity Burn",
        0: "Unburned / Stable",
        1: "Post-Fire Regrowth / Increased Vigor",
        2: "Rapid Emergence"
    }
    t8_req = SpatialLandcoverTerrainRequest(
        lulc_raster_path=lulc_raster_path,
        dem_raster_path=dem_raster_path,
        zone_mask_path=change_mask_path,
        zone_legend=burn_legend,
        calculate_fragmentation=True,
        output_dir=str(out_path)
    )
    t8_res = analyze_spatial_landcover_terrain(t8_req)
    audit_trail.append({"step": "4_zonal_landcover_terrain_cross_tab", "tool": "Tool_8", "dominant_biome": t8_res["dominant_landcover"]["name"]})
    
    # Step 5: Executive Synthesis
    high_burn_zone = t8_res.get("zonal_cross_tabulation", {}).get("-2", {})
    mod_burn_zone = t8_res.get("zonal_cross_tabulation", {}).get("-1", {})
    total_burned_km2 = round(float(high_burn_zone.get("total_area_km2", 0.0) + mod_burn_zone.get("total_area_km2", 0.0)), 4)
    total_burned_ha = round(float(high_burn_zone.get("total_area_hectares", 0.0) + mod_burn_zone.get("total_area_hectares", 0.0)), 2)
    
    return {
        "status": "success",
        "pipeline": "Pipeline_A_Wildfire_Burn_Severity_Assessment",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "workflow_execution_time": {"start": workflow_start, "completed": datetime.now(timezone.utc).isoformat()},
        "executive_summary": {
            "total_burned_area_km2": total_burned_km2,
            "total_burned_area_hectares": total_burned_ha,
            "high_severity_burn_km2": high_burn_zone.get("total_area_km2", 0.0),
            "moderate_severity_burn_km2": mod_burn_zone.get("total_area_km2", 0.0),
            "affected_forest_hectares": high_burn_zone.get("landcover_impact_breakdown", {}).get("Tree cover", {}).get("area_hectares", 0.0),
            "high_burn_mean_slope_deg": high_burn_zone.get("topography", {}).get("mean_slope_deg") if high_burn_zone.get("topography") else None,
        },
        "burn_severity_breakdown": t7_res.get("severity_distribution", {}),
        "topographic_and_landcover_impact": t8_res["zonal_cross_tabulation"],
        "generated_artifacts": {
            "pre_nbr_raster": nbr_pre_file,
            "post_nbr_raster": nbr_post_file,
            "delta_nbr_difference_raster": diff_raster_path,
            "burn_severity_mask": change_mask_path,
        },
        "audit_trail": audit_trail
    }


# =============================================================================
# Pipeline B: Radar Flood Inundation & LULC Impact Assessment
# =============================================================================

def workflow_flood_inundation_impact(
    sar_pre_raster_path: str,
    sar_post_raster_path: str,
    lulc_raster_path: str,
    weather_request: Optional[WeatherEnvironmentRequest] = None,
    dem_raster_path: Optional[str] = None,
    output_dir: Optional[str] = None
) -> Dict[str, Any]:
    """Chains Tool 6 (QA) -> Tool 7 (SAR VV backscatter drop) -> Tool 4 (ERA5 Rainfall) -> Tool 8 (LULC flood exposure)."""
    workflow_start = datetime.now(timezone.utc).isoformat()
    out_path = Path(output_dir) if output_dir else ROOT_DIR / "phase2_demonstrations" / "pipeline_b_flood"
    out_path.mkdir(parents=True, exist_ok=True)
    
    audit_trail = []
    
    # Step 1: Tool 6 - Inspect SAR rasters & verify grid alignment
    t6_req = GeoTIFFInspectionRequest(
        file_path=sar_post_raster_path,
        compare_with=sar_pre_raster_path,
        calculate_statistics=True
    )
    t6_res = inspect_geotiff_metadata(t6_req)
    audit_trail.append({"step": "1_sar_qa_check", "tool": "Tool_6", "is_valid_for_ml": t6_res.get("quality", {}).get("is_valid_for_ml", True)})
    
    # Step 2: Tool 7 - Differential change on VV_dB (Threshold: -3.0 dB drop indicative of water)
    t7_req = TemporalChangeRequest(
        raster_before_path=sar_pre_raster_path,
        raster_after_path=sar_post_raster_path,
        band_selection=1,
        threshold_type="absolute",
        threshold_value=3.0,
        mask_encoding="bipolar_3class",
        output_dir=str(out_path),
        generate_difference_raster=True,
        generate_change_mask=True
    )
    t7_res = analyze_temporal_change(t7_req)
    change_mask_path = t7_res["generated_products"]["change_mask_path"]
    diff_raster_path = t7_res["generated_products"]["difference_raster_path"]
    audit_trail.append({"step": "2_sar_flood_differential", "tool": "Tool_7", "water_inundation_mask": change_mask_path})
    
    # Step 3: Tool 4 - Meteorological Precipitaiton Context (if requested)
    weather_data = None
    if weather_request:
        try:
            weather_data = fetch_weather_environment(weather_request)
            audit_trail.append({"step": "3_meteorological_context", "tool": "Tool_4", "total_rainfall_mm": weather_data["observed_metrics"]["total_rainfall_mm"]})
        except Exception as e:
            weather_data = {"status": "warning", "message": f"Weather fetch skipped or offline: {str(e)}"}
            audit_trail.append({"step": "3_meteorological_context", "tool": "Tool_4", "status": "skipped"})
            
    # Step 4: Tool 8 - Overlay Flood Mask onto LULC & DEM
    flood_legend = {
        -1: "New Water Inundation / Flood Footprint",
        0: "Unflooded / Stable Land",
        1: "Water Recession / Drydown"
    }
    t8_req = SpatialLandcoverTerrainRequest(
        lulc_raster_path=lulc_raster_path,
        dem_raster_path=dem_raster_path,
        zone_mask_path=change_mask_path,
        zone_legend=flood_legend,
        calculate_fragmentation=True,
        output_dir=str(out_path)
    )
    t8_res = analyze_spatial_landcover_terrain(t8_req)
    audit_trail.append({"step": "4_zonal_flood_impact", "tool": "Tool_8", "total_inundated_km2": t8_res.get("zonal_cross_tabulation", {}).get("-1", {}).get("total_area_km2", 0.0)})
    
    # Step 5: Flood Impact Synthesis
    flood_zone = t8_res.get("zonal_cross_tabulation", {}).get("-1", {})
    
    return {
        "status": "success",
        "pipeline": "Pipeline_B_Radar_Flood_Inundation_Assessment",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "executive_summary": {
            "total_flood_inundation_km2": flood_zone.get("total_area_km2", 0.0),
            "total_flood_inundation_hectares": flood_zone.get("total_area_hectares", 0.0),
            "flooded_cropland_hectares": flood_zone.get("landcover_impact_breakdown", {}).get("Cropland", {}).get("area_hectares", 0.0),
            "flooded_urban_built_up_hectares": flood_zone.get("landcover_impact_breakdown", {}).get("Built-up", {}).get("area_hectares", 0.0),
            "event_total_rainfall_mm": weather_data.get("observed_metrics", {}).get("total_rainfall_mm") if weather_data and "observed_metrics" in weather_data else None,
        },
        "meteorological_context": weather_data,
        "flood_extent_and_impact": flood_zone,
        "generated_artifacts": {
            "radar_backscatter_difference_raster": diff_raster_path,
            "flood_inundation_mask": change_mask_path,
        },
        "audit_trail": audit_trail
    }


# =============================================================================
# Pipeline C: Agricultural Drought & Biophysical Canopy Stress
# =============================================================================

def workflow_agricultural_drought_canopy_stress(
    multispectral_raster_path: str,
    weather_request: WeatherEnvironmentRequest,
    output_dir: Optional[str] = None
) -> Dict[str, Any]:
    """Chains Tool 5 (NDVI, NDMI, EVI) -> Tool 4 (ERA5 Soil Moisture & ET0) -> Multi-Modal Agro-Met Correlation Engine."""
    workflow_start = datetime.now(timezone.utc).isoformat()
    out_path = Path(output_dir) if output_dir else ROOT_DIR / "phase2_demonstrations" / "pipeline_c_drought"
    out_path.mkdir(parents=True, exist_ok=True)
    
    audit_trail = []
    
    # Step 1: Tool 5 - Compute Spectral Indices (NDVI for vigor, NDMI for canopy moisture, EVI for biomass)
    t5_req = VegetationIndicesRequest(
        file_path=multispectral_raster_path,
        indices=["NDVI", "NDMI", "EVI"],
        output_dir=str(out_path)
    )
    t5_res = compute_vegetation_indices(t5_req)
    indices_raster = t5_res["data"]["file_path"]
    audit_trail.append({"step": "1_spectral_canopy_indices", "tool": "Tool_5", "indices_calculated": ["NDVI", "NDMI", "EVI"]})
    
    # Step 2: Tool 4 - Meteorological & Soil Moisture Query
    weather_res = fetch_weather_environment(weather_request)
    audit_trail.append({
        "step": "2_weather_and_soil_moisture",
        "tool": "Tool_4",
        "mean_soil_moist": weather_res["observed_metrics"]["mean_soil_moisture_0_to_7cm_m3_m3"]
    })
    
    # Step 3: Correlation Engine (Cross-referencing canopy moisture with soil moisture and ET0)
    ndvi_stats = t5_res["statistics"]["NDVI"]
    ndmi_stats = t5_res["statistics"]["NDMI"]
    evi_stats = t5_res["statistics"]["EVI"]
    
    mean_ndvi = ndvi_stats["mean"]
    mean_ndmi = ndmi_stats["mean"]
    
    soil_moisture = weather_res["observed_metrics"]["mean_soil_moisture_0_to_7cm_m3_m3"]
    water_balance = weather_res["observed_metrics"]["water_balance_mm"]
    total_rainfall = weather_res["observed_metrics"]["total_rainfall_mm"]
    et0_total = weather_res["observed_metrics"]["et0_total_mm"]
    
    # Agro-climatic stress categorization
    if mean_ndmi < 0.0 and soil_moisture < 0.18 and water_balance < -20.0:
        drought_risk_tier = "High Crop Water Stress & Emerging Agricultural Drought"
        primary_driver = "Severe soil moisture depletion coupled with elevated atmospheric evaporative demand (ET0)."
    elif mean_ndmi < 0.10 or water_balance < 0.0:
        drought_risk_tier = "Moderate Soil Moisture Deficit"
        primary_driver = "Sub-optimal soil moisture and negative water balance limiting full canopy transpiration."
    else:
        drought_risk_tier = "Optimal Hydrological Conditions"
        primary_driver = "Adequate soil water availability and favorable canopy moisture balance."
        
    return {
        "status": "success",
        "pipeline": "Pipeline_C_Agricultural_Drought_and_Canopy_Stress",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "executive_summary": {
            "drought_risk_tier": drought_risk_tier,
            "primary_driver": primary_driver,
            "mean_canopy_vigor_ndvi": mean_ndvi,
            "mean_canopy_water_index_ndmi": mean_ndmi,
            "mean_rootzone_soil_moisture_m3_m3": soil_moisture,
            "period_water_balance_mm": water_balance,
            "total_rainfall_mm": total_rainfall,
            "total_evapotranspiration_et0_mm": et0_total,
        },
        "canopy_spectral_profile": {
            "NDVI": ndvi_stats,
            "NDMI": ndmi_stats,
            "EVI": evi_stats,
            "heuristic_vegetation_coverage": t5_res.get("heuristic_classification")
        },
        "meteorological_and_soil_profile": weather_res["observed_metrics"],
        "environmental_stress_indicators": weather_res["environmental_indicators"],
        "generated_artifacts": {
            "canopy_indices_geotiff": indices_raster
        },
        "audit_trail": audit_trail
    }
