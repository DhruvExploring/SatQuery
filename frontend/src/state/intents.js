/**
 * Intent chips, progressive-form metadata, and QueryRequest payload mapping.
 * Field names match backend/api/models.py exactly (orbit_direction, not orbit).
 */

export const ALL_INDICES = [
  'NDVI', 'EVI', 'SAVI', 'GNDVI', 'NDRE_B5', 'NDRE_B7', 'NDMI', 'NDWI', 'MSAVI', 'NBR'
];

export const LOCATION_PRESETS = {
  delhi: {
    id: 'delhi',
    name: 'Delhi NCR',
    bbox: [77.10, 28.50, 77.30, 28.70],
    coords: '28.6139° N, 77.2090° E'
  },
  mumbai: {
    id: 'mumbai',
    name: 'Mumbai coastal',
    bbox: [72.80, 18.90, 73.00, 19.10],
    coords: '19.0760° N, 72.8777° E'
  },
  amazon: {
    id: 'amazon',
    name: 'Amazon AOI',
    bbox: [-62.20, -9.50, -62.00, -9.30],
    coords: '9.4000° S, 62.1000° W'
  }
};

function isoDate(date) {
  return date.toISOString().slice(0, 10);
}

export function lastNDays(n = 30, end = new Date()) {
  const endDate = new Date(end);
  const startDate = new Date(endDate);
  startDate.setDate(endDate.getDate() - n);
  return { start_date: isoDate(startDate), end_date: isoDate(endDate) };
}

/** T1 = 60–31 days ago, T2 = last 30 days — both explicit, never omitted. */
export function defaultTemporalWindows(end = new Date()) {
  const t2 = lastNDays(30, end);
  const t2Start = new Date(t2.start_date);
  const t1End = new Date(t2Start);
  t1End.setDate(t1End.getDate() - 1);
  const t1 = lastNDays(30, t1End);
  return {
    start_date: t1.start_date,
    end_date: t1.end_date,
    post_start_date: t2.start_date,
    post_end_date: t2.end_date
  };
}

export function createDefaultForm() {
  const t1 = lastNDays(30);
  return {
    intent: null,
    query: '',
    locationPreset: 'delhi',
    min_lon: '77.10',
    min_lat: '28.50',
    max_lon: '77.30',
    max_lat: '28.70',
    latitude: '',
    longitude: '',
    start_date: t1.start_date,
    end_date: t1.end_date,
    post_start_date: '',
    post_end_date: '',
    max_cloud_cover: 30,
    width: 512,
    height: 512,
    polarization: ['VV', 'VH'],
    orbit_direction: 'BOTH',
    input_file: '',
    compare_with: '',
    raster_before_path: '',
    raster_after_path: '',
    lulc_raster_path: '',
    dem_raster_path: '',
    zone_mask_path: '',
    indices: [...ALL_INDICES],
    threshold_type: 'absolute',
    threshold_value: 0.15,
    relative_change_threshold_percent: '',
    mask_encoding: 'bipolar_3class',
    showAdvanced: false
  };
}

export const INTENTS = [
  {
    id: 'rgb',
    label: 'RGB',
    trigger: 'Fetch Sentinel-2 optical RGB imagery',
    badge: 'Optical RGB',
    desc: 'Tool 1 — Sentinel-2 visual. Auto-escalates to SAR if clouds block the scene.',
    must: ['bbox'],
    nice: ['dates', 'cloud', 'size']
  },
  {
    id: 'multispectral',
    label: 'Multispectral',
    trigger: 'Fetch Sentinel-2 multispectral imagery for crop health',
    badge: 'Multispectral',
    desc: 'Tool 2 — 8 analytical bands. Required before vegetation indices if you have no file.',
    must: ['bbox'],
    nice: ['dates', 'cloud', 'size']
  },
  {
    id: 'sar',
    label: 'SAR',
    trigger: 'Get Sentinel-1 SAR radar imagery',
    badge: 'SAR',
    desc: 'Tool 3 — radar backscatter. Flood missions are a separate form (two scenes + LULC).',
    must: ['bbox'],
    nice: ['dates', 'sar']
  },
  {
    id: 'weather',
    label: 'Weather',
    trigger: 'Get weather and rainfall for this location',
    badge: 'Weather',
    desc: 'Tool 4 — Open-Meteo. Needs a bbox or a lat/lon point.',
    must: ['location'],
    nice: ['dates']
  },
  {
    id: 'indices',
    label: 'NDVI',
    trigger: 'Compute NDVI vegetation indices',
    badge: 'Vegetation indices',
    desc: 'Tool 5 — 8-band multispectral GeoTIFF required, not an RGB optical export.',
    must: ['input_or_bbox'],
    nice: ['dates', 'cloud', 'indices']
  },
  {
    id: 'inspect',
    label: 'Inspect Raster',
    trigger: 'Inspect this GeoTIFF and run raster QA',
    badge: 'Raster QA',
    desc: 'Tool 6 — CRS, nodata, ML readiness, optional grid-alignment check.',
    must: ['input_file'],
    nice: ['compare']
  },
  {
    id: 'change',
    label: 'Change / Deforestation',
    trigger: 'Detect deforestation and vegetation loss before and after',
    badge: 'Temporal change',
    desc: 'Two files, or bbox plus a T2 date window. LULC is optional but enables Tool 8.',
    must: ['pair'],
    nice: ['lulc', 'advanced']
  },
  {
    id: 'wildfire',
    label: 'Wildfire',
    trigger: 'Map wildfire burn severity and fire scar',
    badge: 'Wildfire mission',
    desc: 'Two multispectral scenes (files or bbox+T1+T2) and an LULC raster.',
    must: ['pair', 'lulc'],
    nice: ['dem', 'advanced']
  },
  {
    id: 'flood',
    label: 'Flood',
    trigger: 'Assess flood inundation impact',
    badge: 'Flood mission',
    desc: 'Two SAR scenes plus LULC — not a single SAR fetch. Typing “flood” routes here.',
    must: ['pair', 'lulc'],
    nice: ['sar', 'dem']
  },
  {
    id: 'drought',
    label: 'Drought',
    trigger: 'Analyze agricultural drought and canopy stress',
    badge: 'Drought mission',
    desc: 'Weather location plus an 8-band multispectral raster (file or fetchable bbox).',
    must: ['location', 'input_or_bbox'],
    nice: ['dates', 'cloud']
  },
  {
    id: 'landcover',
    label: 'Land Cover',
    trigger: 'Analyze land cover and terrain for this WorldCover raster',
    badge: 'Land cover',
    desc: 'Tool 8 — LULC raster is required. DEM and a Tool 7 change mask are optional.',
    must: ['lulc'],
    nice: ['dem', 'zone']
  }
];

export function getIntent(id) {
  return INTENTS.find((item) => item.id === id) || null;
}

function hasAny(query, needles) {
  return needles.some((n) => query.includes(n));
}

/**
 * Mirror backend handshake.classify_intent, then single-tool keywords.
 * Flood beats SAR so chips/autocomplete never drop a flood query into §5C.
 */
export function inferIntentFromQuery(query) {
  const q = (query || '').toLowerCase().trim();
  if (!q) return null;
  if (hasAny(q, ['wildfire', 'wild fire', 'burn severity', 'burn scar', 'fire scar', 'forest fire', 'pre-fire', 'post-fire'])) {
    return 'wildfire';
  }
  if (hasAny(q, ['flood', 'inundation', 'monsoon flood'])) return 'flood';
  if (hasAny(q, ['drought', 'canopy stress', 'agricultural drought', 'crop water stress'])) return 'drought';
  if (hasAny(q, ['deforestation', 'change detection', 'change between', 'before and after', 'vegetation loss', 'vegetation gain', 'temporal change'])) {
    return 'change';
  }
  if (hasAny(q, ['ndvi', 'evi', 'savi', 'gndvi', 'ndre', 'ndmi', 'ndwi', 'msavi', 'nbr', 'vegetation index', 'vegetation indices', 'compute indices'])) {
    return 'indices';
  }
  if (hasAny(q, ['inspect geotiff', 'inspect tiff', 'inspect raster', 'geotiff metadata', 'raster metadata', 'raster qa', 'quality check', 'check raster'])) {
    return 'inspect';
  }
  if (hasAny(q, ['land cover', 'landcover', 'lulc', 'worldcover', 'terrain', 'slope'])) return 'landcover';
  if (hasAny(q, ['weather', 'rainfall', 'temperature', 'precipitation'])) return 'weather';
  if (hasAny(q, ['multispectral', 'spectral bands', 'crop health'])) return 'multispectral';
  if (hasAny(q, ['sar', 'radar', 'sentinel-1', 'sentinel1', 'backscatter'])) return 'sar';
  if (hasAny(q, ['optical', 'sentinel-2', 'sentinel2', 'rgb', 'satellite imagery', 'fetch imagery'])) return 'rgb';
  return null;
}

/**
 * Bare "vegetation" (e.g. "vegetation in Delhi"): the product brief expects
 * status: ok (chat). Live POST /api/v1/query currently routes it to
 * fetch_multispectral_imagery and 400-clarify for bbox when the LLM planner
 * is on. Do not "fix" the backend from this UI. Intercept client-side and
 * let the user pick NDVI / crop health / land cover / change, or send as chat.
 */
export function isAmbiguousVegetationQuery(query) {
  const q = (query || '').toLowerCase().trim();
  if (!/\bvegetation\b/.test(q)) return false;
  const specific = hasAny(q, [
    'ndvi', 'evi', 'savi', 'ndwi', 'ndmi', 'nbr', 'gndvi', 'msavi', 'ndre',
    'vegetation index', 'vegetation indices', 'crop health',
    'deforestation', 'vegetation loss', 'vegetation gain',
    'land cover', 'landcover', 'lulc',
    'change detection', 'before and after', 'wildfire', 'flood', 'drought'
  ]);
  return !specific;
}

export const VEGETATION_CHOICES = [
  { id: 'indices', label: 'NDVI indices', query: 'Compute NDVI vegetation indices' },
  { id: 'multispectral', label: 'Crop health', query: 'Fetch Sentinel-2 multispectral imagery for crop health' },
  { id: 'landcover', label: 'Land cover', query: 'Analyze land cover and terrain for this WorldCover raster' },
  { id: 'change', label: 'Change over time', query: 'Detect deforestation and vegetation loss before and after' }
];

export function parseBbox(form) {
  const nums = [form.min_lon, form.min_lat, form.max_lon, form.max_lat].map((v) => Number(v));
  if (nums.every((n) => Number.isFinite(n))) return nums;
  return null;
}

export function hasLatLon(form) {
  const lat = Number(form.latitude);
  const lon = Number(form.longitude);
  return Number.isFinite(lat) && Number.isFinite(lon);
}

export function hasPairFiles(form) {
  return Boolean(form.raster_before_path?.trim() && form.raster_after_path?.trim());
}

export function hasPostWindow(form) {
  return Boolean(form.post_start_date && form.post_end_date);
}

export function hasLocation(form) {
  return Boolean(parseBbox(form) || hasLatLon(form));
}

/**
 * Client-side "Must" gaps for the selected intent.
 * Blocking submit here avoids a clarify round-trip the backend would send anyway.
 */
export function missingMustFields(form) {
  const intent = getIntent(form.intent);
  if (!intent) return [];
  const missing = [];
  const bbox = parseBbox(form);
  const pairOk = hasPairFiles(form) || (bbox && hasPostWindow(form));

  for (const rule of intent.must) {
    if (rule === 'bbox' && !bbox) missing.push('bbox');
    if (rule === 'location' && !hasLocation(form)) {
      missing.push('bbox', 'latitude', 'longitude');
    }
    if (rule === 'input_file' && !form.input_file?.trim()) missing.push('input_file');
    if (rule === 'input_or_bbox' && !form.input_file?.trim() && !bbox) {
      missing.push('input_file', 'bbox');
    }
    if (rule === 'lulc' && !form.lulc_raster_path?.trim()) missing.push('lulc_raster_path');
    if (rule === 'pair' && !pairOk) {
      missing.push('raster_before_path', 'raster_after_path', 'bbox', 'post_start_date', 'post_end_date');
    }
  }
  return [...new Set(missing)];
}

export function mustFieldMessage(form) {
  const missing = missingMustFields(form);
  if (!missing.length) return '';
  const intent = getIntent(form.intent);
  const labels = {
    bbox: 'bbox [min_lon, min_lat, max_lon, max_lat]',
    latitude: 'latitude',
    longitude: 'longitude',
    input_file: 'an 8-band multispectral GeoTIFF path (input_file)',
    lulc_raster_path: 'lulc_raster_path',
    raster_before_path: 'raster_before_path',
    raster_after_path: 'raster_after_path',
    post_start_date: 'post_start_date',
    post_end_date: 'post_end_date'
  };
  const named = [...new Set(missing.map((f) => labels[f] || f))];
  return `${intent?.badge || 'This analysis'} still needs: ${named.join(', ')}.`;
}

export function applyLocationPreset(form, presetId) {
  const preset = LOCATION_PRESETS[presetId];
  if (!preset) return form;
  const [min_lon, min_lat, max_lon, max_lat] = preset.bbox;
  return {
    ...form,
    locationPreset: presetId,
    min_lon: String(min_lon),
    min_lat: String(min_lat),
    max_lon: String(max_lon),
    max_lat: String(max_lat)
  };
}

export function applyIntent(form, intentId, { rewriteQuery = true } = {}) {
  const intent = getIntent(intentId);
  if (!intent) return { ...form, intent: null };
  const next = { ...form, intent: intentId };
  if (rewriteQuery) next.query = intent.trigger;
  const needsT2 = intentId === 'change' || intentId === 'wildfire' || intentId === 'flood';
  if (needsT2 && !next.post_start_date) {
    const windows = defaultTemporalWindows();
    next.start_date = windows.start_date;
    next.end_date = windows.end_date;
    next.post_start_date = windows.post_start_date;
    next.post_end_date = windows.post_end_date;
  }
  return next;
}

/**
 * Convert form state → QueryRequest fields. Dates are always sent (last-30 default),
 * never omitted so the stale 2025-01 backend default is not used silently.
 */
export function formToQueryFields(form) {
  const bbox = parseBbox(form);
  const fields = {
    query: (form.query || '').trim(),
    start_date: form.start_date,
    end_date: form.end_date,
    max_cloud_cover: Number(form.max_cloud_cover),
    width: Number(form.width) || 512,
    height: Number(form.height) || 512
  };

  if (bbox) fields.bbox = bbox;
  if (hasLatLon(form)) {
    fields.latitude = Number(form.latitude);
    fields.longitude = Number(form.longitude);
  }
  if (form.post_start_date) fields.post_start_date = form.post_start_date;
  if (form.post_end_date) fields.post_end_date = form.post_end_date;

  const intent = form.intent;
  const usesSar = intent === 'sar' || intent === 'flood';
  if (usesSar) {
    fields.polarization = form.polarization?.length ? form.polarization : ['VV', 'VH'];
    fields.orbit_direction = form.orbit_direction || 'BOTH';
  }

  if (form.input_file?.trim()) fields.input_file = form.input_file.trim();
  if (form.compare_with?.trim()) fields.compare_with = form.compare_with.trim();
  if (form.raster_before_path?.trim()) fields.raster_before_path = form.raster_before_path.trim();
  if (form.raster_after_path?.trim()) fields.raster_after_path = form.raster_after_path.trim();
  if (form.lulc_raster_path?.trim()) fields.lulc_raster_path = form.lulc_raster_path.trim();
  if (form.dem_raster_path?.trim()) fields.dem_raster_path = form.dem_raster_path.trim();
  if (form.zone_mask_path?.trim()) fields.zone_mask_path = form.zone_mask_path.trim();

  if (intent === 'indices' || intent === 'drought') {
    fields.indices = form.indices?.length ? form.indices : [...ALL_INDICES];
    fields.calculate_heuristic_classification = true;
  }

  if (intent === 'change' || intent === 'wildfire') {
    fields.threshold_type = form.threshold_type || 'absolute';
    fields.threshold_value = Number(form.threshold_value);
    fields.mask_encoding = form.mask_encoding || 'bipolar_3class';
    // Relative % is meaningless on SAR dB — never send it for flood/SAR.
    if (!usesSar && form.relative_change_threshold_percent !== '') {
      const rel = Number(form.relative_change_threshold_percent);
      if (Number.isFinite(rel)) fields.relative_change_threshold_percent = rel;
    }
  }

  return fields;
}

export function widenDates(form, days = 30) {
  const shift = (value, delta) => {
    if (!value) return value;
    const d = new Date(`${value}T00:00:00`);
    d.setDate(d.getDate() + delta);
    return isoDate(d);
  };
  return {
    ...form,
    start_date: shift(form.start_date, -days),
    end_date: shift(form.end_date, days),
    post_start_date: form.post_start_date ? shift(form.post_start_date, -days) : form.post_start_date,
    post_end_date: form.post_end_date ? shift(form.post_end_date, days) : form.post_end_date
  };
}
