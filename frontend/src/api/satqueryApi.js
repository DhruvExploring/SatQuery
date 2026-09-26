/**
 * SatQuery API client.
 * Talks to GET /health and POST /api/v1/query only — file upload lives in
 * api/rasters.js next to the other raster-file concerns.
 */

/**
 * Resolution order: the runtime env-config.js injected by the Docker/prod
 * frontend container (window.__SATQUERY_CONFIG__.API_BASE_URL) > same-origin
 * (empty string, the production default when nginx/uvicorn serves both) > the
 * plain `vite dev` convenience guess of a backend on localhost:8000.
 */
export const API_BASE = (() => {
  if (typeof window === 'undefined') return '';
  const configured = window.__SATQUERY_CONFIG__?.API_BASE_URL;
  if (configured) return configured;
  if (window.__SATQUERY_CONFIG__) return ''; // env-config.js loaded, deliberately same-origin
  if (window.location.port && window.location.port !== '8000') return 'http://localhost:8000';
  return '';
})();

export async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`, { method: 'GET' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message };
  }
}

export async function fetchModelsStatus() {
  try {
    const res = await fetch(`${API_BASE}/api/v1/models`, { method: 'GET' });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/**
 * POST /api/v1/query with a raw payload matching the backend's QueryRequest
 * fields directly (query, input_file, raster_before_path, bbox, latitude,
 * longitude, ...). Returns { httpStatus, body } for every HTTP code,
 * including 400/404/502/500. Network failures return
 * { networkError: true, error }.
 */
export async function runQuery(payload) {
  let res;
  try {
    res = await fetch(`${API_BASE}/api/v1/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  } catch (err) {
    return { networkError: true, error: err.message || 'Network error', httpStatus: 0, body: null };
  }

  let body = null;
  try {
    body = await res.json();
  } catch {
    body = {
      status: 'error',
      final_answer: 'The server returned a non-JSON response.',
      tool_results: [],
      errors: [`HTTP ${res.status}`]
    };
  }

  return { networkError: false, httpStatus: res.status, body };
}

export async function resetConversationApi({ sessionId, tempFiles = [] } = {}) {
  try {
    const res = await fetch(`${API_BASE}/api/v1/conversation/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId || null,
        temp_files: tempFiles || []
      })
    });
    if (!res.ok) {
      return { ok: false, status: res.status };
    }
    const data = await res.json().catch(() => ({ status: 'ok' }));
    return { ok: true, data };
  } catch (err) {
    return { ok: false, error: err.message || 'Network error' };
  }
}

/**
 * POST /api/v1/query/stream: same payload as runQuery, but the backend
 * pushes one Server-Sent Event per LangGraph node as it actually completes
 * ({type:'step', step:{node,timestamp,summary}}), then a closing
 * {type:'final', ...same shape as runQuery's body} event. Native
 * EventSource can't send a POST body, so this parses the stream manually.
 *
 * onStep(step) fires for each step event, in order, as it arrives.
 * Resolves with the final event's payload once the stream closes; resolves
 * with { networkError: true, error } instead if the request itself fails.
 * Supports AbortSignal via opts.signal to immediately cancel and discard streams.
 */
export async function runQueryStream(payload, { onStep, signal } = {}) {
  let res;
  try {
    res = await fetch(`${API_BASE}/api/v1/query/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal
    });
  } catch (err) {
    if (err?.name === 'AbortError' || signal?.aborted) {
      return { aborted: true, networkError: false };
    }
    return { networkError: true, error: err.message || 'Network error' };
  }

  if (!res.ok || !res.body) {
    return { networkError: true, error: `HTTP ${res.status}` };
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let final = null;
  let streamError = null;

  try {
    while (true) {
      if (signal?.aborted) {
        try { reader.cancel(); } catch { /* ignore */ }
        return { aborted: true, networkError: false };
      }

      const { done, value } = await reader.read();
      if (done) break;

      if (signal?.aborted) {
        return { aborted: true, networkError: false };
      }

      buffer += decoder.decode(value, { stream: true });

      let boundary;
      while ((boundary = buffer.indexOf('\n\n')) !== -1) {
        if (signal?.aborted) {
          return { aborted: true, networkError: false };
        }

        const rawEvent = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const dataLine = rawEvent.split('\n').find((line) => line.startsWith('data: '));
        if (!dataLine) continue;

        let event;
        try {
          event = JSON.parse(dataLine.slice(6));
        } catch {
          continue;
        }

        if (event.type === 'step') onStep?.(event.step);
        else if (event.type === 'final') final = event;
        else if (event.type === 'error') streamError = event.message;
      }
    }
  } catch (err) {
    if (err?.name === 'AbortError' || signal?.aborted) {
      return { aborted: true, networkError: false };
    }
    return { networkError: true, error: err.message || 'Stream read error' };
  }

  if (signal?.aborted) {
    return { aborted: true, networkError: false };
  }

  if (final) return { networkError: false, body: final };
  return { networkError: true, error: streamError || 'Stream ended without a final result.' };
}
