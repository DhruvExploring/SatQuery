import { runQuery } from '../api/satqueryApi';

/**
 * Runs the same quiet background inspect_geotiff_metadata call ImageSlot
 * already does after a user-picked upload, for any GeoTIFF path -- uploaded
 * or freshly fetched by a tool call server-side (see App.jsx's fetch-tool
 * slot adoption). Returns the slot-state patch (boundsWgs84 + the info chip
 * fields) to merge in, or null if the inspection didn't succeed.
 */
export async function inspectGeotiff(path) {
  const { networkError, body } = await runQuery({
    query: 'Inspect this GeoTIFF.',
    input_file: path
  });
  if (networkError || !body) return null;

  const inspectResult = (body.tool_results || []).find(
    (r) => r.tool === 'inspect_geotiff_metadata'
  )?.result;
  if (!inspectResult || inspectResult.status !== 'success') return null;

  return {
    rawMetadata: inspectResult,
    boundsWgs84: inspectResult.spatial?.bounds_wgs84 || null,
    info: {
      width: inspectResult.raster?.width,
      height: inspectResult.raster?.height,
      bandCount: inspectResult.raster?.band_count,
      crs: inspectResult.spatial?.crs,
      georeferenced: inspectResult.quality?.is_georeferenced,
      pixelSizeWgs84Degrees: inspectResult.spatial?.pixel_size_wgs84_degrees || null,
      boundsWgs84: inspectResult.spatial?.bounds_wgs84 || null,
      approxAreaKm2: inspectResult.spatial?.approx_area_km2 || null,
      cornersWgs84: inspectResult.spatial?.corners_wgs84 || null,
      resolution: inspectResult.spatial?.resolution || null,
      driver: inspectResult.file?.driver || null,
      fileSizeBytes: inspectResult.file?.file_size_bytes || null,
      compression: inspectResult.raster?.compression || null
    }
  };
}
