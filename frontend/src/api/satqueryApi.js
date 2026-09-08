/**
 * SatQuery API client.
 * Only talks to GET /health and POST /api/v1/query.
 * Never throws on a QueryResponse-shaped HTTP error — 400 clarify is a
 * normal product state and must be returned to the shared handler.
 */

const API_BASE = (typeof window !== 'undefined' && window.location.port && window.location.port !== '8000')
  ? 'http://localhost:8000'
  : '';

/** Exact QueryRequest keys from backend/api/models.py — do not rename. */
const QUERY_REQUEST_KEYS = [
  'query',
  'bbox',
  'latitude',
  'longitude',
  'start_date',
  'end_date',
  'post_start_date',
  'post_end_date',
  'bands',
  'max_cloud_cover',
  'width',
  'height',
  'polarization',
  'orbit_direction',
  'scene_selection',
  'input_file',
  'indices',
  'band_mapping',
  'calculate_heuristic_classification',
  'compare_with',
  'calculate_statistics',
  'calculate_histogram',
  'raster_before_path',
  'raster_after_path',
  'band_selection',
  'threshold_type',
  'threshold_value',
  'relative_change_threshold_percent',
  'mask_encoding',
  'analysis_output_dir',
  'generate_difference_raster',
  'generate_change_mask',
  'lulc_raster_path',
  'dem_raster_path',
  'zone_mask_path',
  'calculate_fragmentation'
];

function isEmpty(value) {
  if (value === undefined || value === null) return true;
  if (typeof value === 'string' && value.trim() === '') return true;
  if (Array.isArray(value) && value.length === 0) return true;
  return false;
}

/**
 * Build a POST /api/v1/query body from a flat fields object.
 * Drops unknown keys (including the invalid `orbit` alias).
 */
export function buildQueryPayload(fields = {}) {
  const payload = {};
  for (const key of QUERY_REQUEST_KEYS) {
    if (!Object.prototype.hasOwnProperty.call(fields, key)) continue;
    const value = fields[key];
    if (isEmpty(value)) continue;
    payload[key] = value;
  }
  return payload;
}

export async function checkHealth() {
  const startTime = performance.now();
  try {
    const res = await fetch(`${API_BASE}/health`, { method: 'GET' });
    const latency = Math.round(performance.now() - startTime);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return { ok: true, data, latency };
  } catch (err) {
    return { ok: false, error: err.message, latency: Math.round(performance.now() - startTime) };
  }
}

/**
 * POST /api/v1/query.
 * Returns { httpStatus, body } for every HTTP code, including 400/404/502/500.
 * Network failures return { networkError: true, error }.
 */
export async function runSatelliteQuery(fields) {
  const payload = buildQueryPayload(fields);

  let res;
  try {
    res = await fetch(`${API_BASE}/api/v1/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  } catch (err) {
    return {
      networkError: true,
      error: err.message || 'Network error',
      httpStatus: 0,
      body: null
    };
  }

  let body = null;
  try {
    body = await res.json();
  } catch {
    body = {
      status: 'error',
      final_answer: 'The server returned a non-JSON response.',
      plan: null,
      tool_results: [],
      errors: [`HTTP ${res.status}`],
      execution_trace: []
    };
  }

  return { networkError: false, httpStatus: res.status, body };
}
