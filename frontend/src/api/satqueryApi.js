/**
 * SatQuery AI — API Client
 * Interfaces with FastAPI endpoints (/api/v1/query, /health)
 */

const API_BASE = (typeof window !== 'undefined' && window.location.port && window.location.port !== '8000')
  ? 'http://localhost:8000'
  : '';

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

export async function runSatelliteQuery({ query, bbox, latitude, longitude, orbit, polarization }) {
  const payload = {
    query,
    ...(bbox ? { bbox } : {}),
    ...(latitude !== undefined ? { latitude } : {}),
    ...(longitude !== undefined ? { longitude } : {}),
    ...(orbit ? { orbit } : {}),
    ...(polarization ? { polarization } : {})
  };

  const res = await fetch(`${API_BASE}/api/v1/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  const data = await res.json();
  if (!res.ok) {
    const errDetail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data);
    throw new Error(errDetail || `Request failed with HTTP ${res.status}`);
  }

  return data;
}
