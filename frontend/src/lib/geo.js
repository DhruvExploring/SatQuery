/**
 * Convert a region-of-interest box (fractions of the rendered image, 0-1,
 * top-left origin) into an approximate real-world sub-bbox, using the full
 * raster's own bounds_wgs84 (from inspect_geotiff_metadata). Assumes a
 * north-up image, true for every GeoTIFF this project's tools produce.
 */
export function roiBoxToBbox(roi, boundsWgs84) {
  if (!roi || !boundsWgs84) return null;
  const { min_lon, min_lat, max_lon, max_lat } = boundsWgs84;
  const lonSpan = max_lon - min_lon;
  const latSpan = max_lat - min_lat;

  const left = roi.x;
  const right = roi.x + roi.w;
  const top = roi.y;
  const bottom = roi.y + roi.h;

  return {
    min_lon: min_lon + left * lonSpan,
    max_lon: min_lon + right * lonSpan,
    // image row 0 is the north edge (max_lat), so "top" maps to max_lat.
    max_lat: max_lat - top * latSpan,
    min_lat: max_lat - bottom * latSpan
  };
}

export function formatBbox(bbox) {
  if (!bbox) return '';
  const { min_lon, min_lat, max_lon, max_lat } = bbox;
  return `${min_lon.toFixed(4)}–${max_lon.toFixed(4)}°E, ${min_lat.toFixed(4)}–${max_lat.toFixed(4)}°N`;
}
