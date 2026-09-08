/**
 * Shared QueryResponse handler — every screen funnels through this.
 *
 * Contract (always this shape, including on 400/404/502/500):
 *   status, final_answer, plan, tool_results, errors, execution_trace
 *
 * Do not read res.response or res.tool_name — those keys do not exist.
 */

const EMPTY_BODY = {
  status: 'error',
  final_answer: '',
  plan: null,
  tool_results: [],
  errors: [],
  execution_trace: []
};

function latestToolError(body) {
  const results = body?.tool_results || [];
  if (!results.length) return null;
  const last = results[results.length - 1] || {};
  return last.result?.error || last.error || null;
}

function joinedText(body) {
  const errors = Array.isArray(body?.errors) ? body.errors.join(' ') : '';
  const toolErr = latestToolError(body);
  const toolMsg = typeof toolErr === 'string'
    ? toolErr
    : [toolErr?.message, toolErr?.detail, toolErr?.type].filter(Boolean).join(' ');
  return `${body?.final_answer || ''} ${body?.plan?.reason || ''} ${errors} ${toolMsg}`;
}

function parseSuggestedOrbit(text) {
  const match = String(text || '').match(/orbit_direction\s*=\s*(ASCENDING|DESCENDING|BOTH)/i)
    || String(text || '').match(/Retry with orbit_direction=([A-Z]+)/i)
    || String(text || '').match(/none are (ASCENDING|DESCENDING)/i);
  if (!match) {
    const available = String(text || '').match(/\b(ASCENDING|DESCENDING)\b/g);
    if (available && available.length) return available[available.length - 1].toUpperCase();
    return null;
  }
  return match[1].toUpperCase();
}

/**
 * Map a clarify reason onto form widget names so the UI can highlight them.
 * Surfaces every named gap at once (bbox + T2 + LULC, etc.).
 */
export function parseMissingFields(reason = '', extra = '') {
  const text = `${reason} ${extra}`.toLowerCase();
  const fields = new Set();

  if (/\bbbox\b/.test(text)) fields.add('bbox');
  if (/latitude/.test(text)) fields.add('latitude');
  if (/longitude/.test(text)) fields.add('longitude');
  if (/lat\/lon|lat-lon|latitude and longitude/.test(text)) {
    fields.add('latitude');
    fields.add('longitude');
    fields.add('bbox');
  }
  if (/post_start_date/.test(text)) fields.add('post_start_date');
  if (/post_end_date/.test(text)) fields.add('post_end_date');
  if (/start_date/.test(text) && !/post_start_date/.test(text)) fields.add('start_date');
  if (/end_date/.test(text) && !/post_end_date/.test(text)) fields.add('end_date');
  if (/input_file|geotiff input file/.test(text)) fields.add('input_file');
  if (/lulc_raster_path|lulc/.test(text)) fields.add('lulc_raster_path');
  if (/raster_before_path|two scenes|before\/after|before and after/.test(text)) {
    fields.add('raster_before_path');
  }
  if (/raster_after_path|two scenes|before\/after|before and after/.test(text)) {
    fields.add('raster_after_path');
  }
  if (/post_start_date and post_end_date|t2 fetch|two scenes/.test(text)) {
    fields.add('bbox');
    fields.add('post_start_date');
    fields.add('post_end_date');
    fields.add('raster_before_path');
    fields.add('raster_after_path');
  }
  if (/compare_with/.test(text)) fields.add('compare_with');
  if (/dem_raster_path/.test(text)) fields.add('dem_raster_path');
  if (/zone_mask_path/.test(text)) fields.add('zone_mask_path');
  if (/orbit/.test(text)) fields.add('orbit_direction');

  return [...fields];
}

function errorCopy(httpStatus, body) {
  const errors = Array.isArray(body?.errors) ? body.errors : [];
  const firstError = errors[0] || '';
  const text = joinedText(body);
  const toolErr = latestToolError(body);
  const errType = toolErr?.type || '';
  const suggestedOrbit = parseSuggestedOrbit(text);
  const isSar = /sar|orbit|ascending|descending|sentinel-1|backscatter/.test(text.toLowerCase());

  if (httpStatus === 404 || errType === 'no_suitable_scene' || errType === 'no_data') {
    if (isSar) {
      return {
        title: 'No matching SAR scene',
        message: suggestedOrbit && suggestedOrbit !== 'BOTH'
          ? `No matching scene was found for this area/date range with the requested orbit. The catalog has ${suggestedOrbit} scenes instead. Try ${suggestedOrbit}, BOTH, or a wider date range.`
          : 'No matching scene was found for this area/date range. Try widening the dates or switching orbit direction, for SAR.',
        actions: [
          { id: 'widen_dates', label: 'Widen date range (±30 days)' },
          ...(suggestedOrbit
            ? [{ id: `orbit:${suggestedOrbit}`, label: `Use ${suggestedOrbit} instead` }]
            : [
                { id: 'orbit:DESCENDING', label: 'Use DESCENDING instead' },
                { id: 'orbit:ASCENDING', label: 'Use ASCENDING instead' }
              ]),
          { id: 'orbit:BOTH', label: 'Use BOTH orbits' }
        ]
      };
    }
    return {
      title: 'No matching scene',
      message: 'No matching scene was found for this area/date range. Try widening the dates.',
      actions: [{ id: 'widen_dates', label: 'Widen date range (±30 days)' }]
    };
  }

  if (httpStatus === 502 || errType === 'service_error') {
    return {
      title: 'Provider unavailable',
      message: 'The satellite data provider is temporarily unavailable. Please retry in a moment.',
      actions: [{ id: 'retry', label: 'Retry request' }]
    };
  }

  if (httpStatus === 500 || errType === 'import_error' || errType === 'unknown_tool') {
    return {
      title: 'Something went wrong on our end.',
      message: body?.final_answer || 'Something went wrong on our end.',
      actions: []
    };
  }

  // 400 invalid input (not clarify), or FastAPI 422
  const detail = formatPydanticDetail(body);
  return {
    title: 'There is a problem with the input',
    message: `There's a problem with the input: ${firstError || detail || body?.final_answer || 'invalid request'}.`,
    actions: []
  };
}

function formatPydanticDetail(body) {
  const detail = body?.detail;
  if (!detail) return '';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || JSON.stringify(item)).join('; ');
  }
  return JSON.stringify(detail);
}

function hopCapHit(body) {
  const errors = body?.errors || [];
  const reason = body?.plan?.reason || '';
  return [...errors, reason].some((item) => /max hops/i.test(String(item)));
}

/**
 * Normalize a fetch result into one of: success | ok | clarify | error | network.
 * Screens should branch on `kind` only.
 */
export function handleQueryResponse({ httpStatus, body, networkError, error }) {
  if (networkError) {
    return {
      kind: 'error',
      httpStatus: 0,
      status: 'error',
      finalAnswer: 'Could not reach the SatQuery API. Check that the backend is running.',
      plan: null,
      toolResults: [],
      errors: [error || 'Network error'],
      executionTrace: [],
      missingFields: [],
      copy: {
        title: 'Connection failed',
        message: 'Could not reach the SatQuery API. Check that the backend is running on port 8000.',
        actions: [{ id: 'retry', label: 'Retry request' }]
      },
      hopCapHit: false,
      body: EMPTY_BODY
    };
  }

  const payload = body && typeof body === 'object' ? body : EMPTY_BODY;
  const status = String(payload.status || '').toLowerCase();
  const finalAnswer = payload.final_answer || '';
  const plan = payload.plan || null;
  const toolResults = Array.isArray(payload.tool_results) ? payload.tool_results : [];
  const errors = Array.isArray(payload.errors) ? payload.errors : [];
  const executionTrace = Array.isArray(payload.execution_trace) ? payload.execution_trace : [];
  const toolName = plan?.tool || toolResults[0]?.tool || null;

  const base = {
    httpStatus,
    status,
    finalAnswer,
    plan,
    toolResults,
    errors,
    executionTrace,
    toolName,
    missingFields: [],
    hopCapHit: hopCapHit(payload),
    body: payload
  };

  if (status === 'clarify' || (httpStatus === 400 && status === 'clarify')) {
    const reason = plan?.reason || finalAnswer;
    return {
      ...base,
      kind: 'clarify',
      missingFields: parseMissingFields(reason, errors.join(' ')),
      copy: {
        title: 'A few more inputs are needed',
        message: reason,
        actions: []
      }
    };
  }

  if (status === 'ok') {
    return {
      ...base,
      kind: 'ok',
      copy: {
        title: 'What SatQuery can do',
        message: finalAnswer,
        actions: []
      }
    };
  }

  if (status === 'success') {
    const steps = toolResults.length;
    const prefix = steps > 1 ? `Completed a ${steps}-step analysis. ` : '';
    return {
      ...base,
      kind: 'success',
      copy: {
        title: steps > 1 ? `Completed a ${steps}-step analysis` : 'Analysis complete',
        message: `${prefix}${finalAnswer}`.trim(),
        actions: []
      }
    };
  }

  // FastAPI 422 validation uses {detail} instead of QueryResponse
  if (payload.detail && !payload.status) {
    const missing = parseMissingFields(formatPydanticDetail(payload), '');
    const copy = errorCopy(httpStatus || 400, { ...payload, errors: [formatPydanticDetail(payload)], final_answer: formatPydanticDetail(payload) });
    return {
      ...base,
      kind: 'error',
      status: 'error',
      finalAnswer: copy.message,
      missingFields: missing,
      errors: [formatPydanticDetail(payload)],
      copy
    };
  }

  const copy = errorCopy(httpStatus || 400, payload);
  if (base.hopCapHit) {
    copy.message = `${copy.message} The analysis stopped partway (hop cap reached). Partial tool results are shown below.`;
  }

  return {
    ...base,
    kind: 'error',
    copy
  };
}
