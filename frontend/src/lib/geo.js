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

export function formatLat(lat) {
  if (lat == null || Number.isNaN(Number(lat))) return '';
  const n = Number(lat);
  return `${Math.abs(n).toFixed(4)}°${n >= 0 ? 'N' : 'S'}`;
}

export function formatLon(lon) {
  if (lon == null || Number.isNaN(Number(lon))) return '';
  const n = Number(lon);
  return `${Math.abs(n).toFixed(4)}°${n >= 0 ? 'E' : 'W'}`;
}

export function computeApproxAreaKm2(bounds) {
  if (!bounds || bounds.min_lat == null || bounds.max_lat == null || bounds.min_lon == null || bounds.max_lon == null) {
    return null;
  }
  const latMid = (bounds.min_lat + bounds.max_lat) / 2.0;
  const latRad = (latMid * Math.PI) / 180.0;
  const degToMLat = 111132.954 - 559.822 * Math.cos(2 * latRad) + 1.175 * Math.cos(4 * latRad);
  const degToMLon = 111412.84 * Math.cos(latRad) - 93.5 * Math.cos(3 * latRad);
  const widthM = Math.abs(bounds.max_lon - bounds.min_lon) * degToMLon;
  const heightM = Math.abs(bounds.max_lat - bounds.min_lat) * degToMLat;
  const km2 = (widthM * heightM) / 1e6;
  return km2 < 0.01 ? '<0.01' : km2.toFixed(2);
}

