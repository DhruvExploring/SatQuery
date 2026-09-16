/**
 * Human-readable display names for tool_results[].tool, for the green tool
 * badges in the chat log. Falls back to the raw tool name for anything
 * (e.g. a future Tool 9) not listed here.
 */
const LABELS = {
  fetch_optical_imagery: 'Fetch optical (Sentinel-2)',
  fetch_satellite_imagery: 'Fetch optical (Sentinel-2)',
  fetch_multispectral_imagery: 'Fetch multispectral (Sentinel-2)',
  fetch_sar_imagery: 'Fetch SAR (Sentinel-1)',
  fetch_sar: 'Fetch SAR (Sentinel-1)',
  fetch_weather_environment: 'Weather / environment',
  compute_vegetation_indices: 'Vegetation indices',
  inspect_geotiff_metadata: 'GeoTIFF inspection',
  analyze_temporal_change: 'Temporal change',
  analyze_spatial_landcover_terrain: 'Land cover / terrain',
  analyze_imagery_vlm: 'Vision analysis',
  mark_region_in_image: 'Mark region',
  compare_images_visually: 'Visual comparison',
  workflow_wildfire_burn_severity: 'Wildfire burn severity',
  workflow_flood_inundation_impact: 'Flood inundation',
  workflow_agricultural_drought_canopy_stress: 'Drought / canopy stress',
  get_place_name_from_coordinates: 'Reverse geocode',
  fetch_web_intelligence: 'Web search',
  geocode_place_to_coordinates: 'Forward geocode',
  resolve_scene_identity: 'Scene identity',
  discover_points_of_interest: 'Points of interest',
  deterministic_affine_markup: 'Precise coordinate markup',
  describe_marked_region: 'Describe marked region'
};

export function toolLabel(toolName) {
  return LABELS[toolName] || toolName;
}
