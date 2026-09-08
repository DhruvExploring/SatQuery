import React from 'react';
import {
  ALL_INDICES,
  getIntent,
  parseBbox
} from '../state/intents';

function Field({ id, label, hint, highlighted, children }) {
  return (
    <div
      id={`field-${id}`}
      className={`form-field ${highlighted ? 'field-highlight' : ''}`}
    >
      <label className="form-label" htmlFor={id}>{label}</label>
      {children}
      {hint ? <span className="form-hint">{hint}</span> : null}
    </div>
  );
}

function PathInput({ id, value, onChange, placeholder, highlighted, label, hint }) {
  return (
    <Field id={id} label={label} hint={hint} highlighted={highlighted}>
      <input
        id={id}
        type="text"
        className="form-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        spellCheck="false"
      />
    </Field>
  );
}

export default function QueryForm({
  form,
  onChange,
  highlightedFields = [],
  showAdvanced,
  onToggleAdvanced
}) {
  const intent = getIntent(form.intent);
  const highlighted = new Set(highlightedFields);
  const is = (id) => form.intent === id;
  const showLocation = !intent || ['rgb', 'multispectral', 'sar', 'weather', 'indices', 'change', 'wildfire', 'flood', 'drought'].includes(form.intent);
  const showDates = showLocation;
  const showT2 = ['change', 'wildfire', 'flood'].includes(form.intent);
  const showCloud = !intent || ['rgb', 'multispectral', 'indices', 'change', 'wildfire', 'drought'].includes(form.intent);
  const showSize = !intent || ['rgb', 'multispectral', 'sar', 'indices', 'change', 'wildfire', 'flood', 'drought'].includes(form.intent);
  const showSar = ['sar', 'flood'].includes(form.intent);
  const showInputFile = ['indices', 'inspect', 'drought'].includes(form.intent);
  const showCompare = is('inspect');
  const showPairFiles = ['change', 'wildfire', 'flood'].includes(form.intent);
  const showLulc = ['change', 'wildfire', 'flood', 'landcover'].includes(form.intent);
  const showDem = ['wildfire', 'flood', 'landcover'].includes(form.intent);
  const showZone = is('landcover');
  const showIndices = ['indices', 'drought'].includes(form.intent);
  const showChangeAdvanced = ['change', 'wildfire'].includes(form.intent);
  const hideRelativePct = ['sar', 'flood'].includes(form.intent);
  const bboxOk = Boolean(parseBbox(form));

  const patch = (partial) => onChange({ ...form, ...partial });

  const togglePolarization = (pol) => {
    const current = form.polarization || [];
    const next = current.includes(pol)
      ? current.filter((p) => p !== pol)
      : [...current, pol];
    patch({ polarization: next.length ? next : [pol] });
  };

  const toggleIndex = (name) => {
    const current = form.indices || [];
    const next = current.includes(name)
      ? current.filter((i) => i !== name)
      : [...current, name];
    patch({ indices: next });
  };

  return (
    <div className="progressive-form">
      {intent ? (
        <div className="intent-card">
          <div className="intent-icon">✓</div>
          <div>
            <div className="intent-title">INTENT: {intent.badge}</div>
            <div className="intent-desc">{intent.desc}</div>
          </div>
        </div>
      ) : (
        <div className="intent-card intent-card-muted">
          <div className="intent-icon">?</div>
          <div>
            <div className="intent-title">Free-text query</div>
            <div className="intent-desc">
              Pick a chip above to collect the right fields, or type anything.
              Bare “vegetation” is chat unless you choose NDVI / crop health / land cover / change.
            </div>
          </div>
        </div>
      )}

      {showLocation && (
        <div className="form-section">
          <div className="section-label"><span>LOCATION</span></div>
          <div className={`form-grid-4 ${highlighted.has('bbox') ? 'field-highlight-group' : ''}`} id="field-bbox">
            <Field id="min_lon" label="min_lon" highlighted={highlighted.has('bbox')}>
              <input id="min_lon" className="form-input" type="number" step="0.0001" value={form.min_lon}
                onChange={(e) => patch({ min_lon: e.target.value, locationPreset: '' })} />
            </Field>
            <Field id="min_lat" label="min_lat" highlighted={highlighted.has('bbox')}>
              <input id="min_lat" className="form-input" type="number" step="0.0001" value={form.min_lat}
                onChange={(e) => patch({ min_lat: e.target.value, locationPreset: '' })} />
            </Field>
            <Field id="max_lon" label="max_lon" highlighted={highlighted.has('bbox')}>
              <input id="max_lon" className="form-input" type="number" step="0.0001" value={form.max_lon}
                onChange={(e) => patch({ max_lon: e.target.value, locationPreset: '' })} />
            </Field>
            <Field id="max_lat" label="max_lat" highlighted={highlighted.has('bbox')}>
              <input id="max_lat" className="form-input" type="number" step="0.0001" value={form.max_lat}
                onChange={(e) => patch({ max_lat: e.target.value, locationPreset: '' })} />
            </Field>
          </div>
          <p className="form-hint">
            bbox sent as [{bboxOk ? parseBbox(form).join(', ') : 'incomplete'}]. Numeric WGS84 only — place names are not geocoded by the backend.
          </p>
          {(is('weather') || is('drought') || highlighted.has('latitude') || highlighted.has('longitude')) && (
            <div className="form-grid-2">
              <Field id="latitude" label="latitude" highlighted={highlighted.has('latitude')}>
                <input id="latitude" className="form-input" type="number" step="0.0001" value={form.latitude}
                  onChange={(e) => patch({ latitude: e.target.value })} placeholder="e.g. 28.61" />
              </Field>
              <Field id="longitude" label="longitude" highlighted={highlighted.has('longitude')}>
                <input id="longitude" className="form-input" type="number" step="0.0001" value={form.longitude}
                  onChange={(e) => patch({ longitude: e.target.value })} placeholder="e.g. 77.21" />
              </Field>
            </div>
          )}
        </div>
      )}

      {showDates && (
        <div className="form-section">
          <div className="section-label"><span>{showT2 ? 'T1 DATE WINDOW' : 'DATE WINDOW'}</span></div>
          <div className="form-grid-2">
            <Field id="start_date" label="start_date" highlighted={highlighted.has('start_date')}>
              <input id="start_date" className="form-input" type="date" value={form.start_date}
                onChange={(e) => patch({ start_date: e.target.value })} />
            </Field>
            <Field id="end_date" label="end_date" highlighted={highlighted.has('end_date')}>
              <input id="end_date" className="form-input" type="date" value={form.end_date}
                onChange={(e) => patch({ end_date: e.target.value })} />
            </Field>
          </div>
          {showT2 && (
            <>
              <div className="section-label" style={{ marginTop: '0.75rem' }}><span>T2 DATE WINDOW</span></div>
              <div className="form-grid-2">
                <Field id="post_start_date" label="post_start_date" highlighted={highlighted.has('post_start_date')}>
                  <input id="post_start_date" className="form-input" type="date" value={form.post_start_date}
                    onChange={(e) => patch({ post_start_date: e.target.value })} />
                </Field>
                <Field id="post_end_date" label="post_end_date" highlighted={highlighted.has('post_end_date')}>
                  <input id="post_end_date" className="form-input" type="date" value={form.post_end_date}
                    onChange={(e) => patch({ post_end_date: e.target.value })} />
                </Field>
              </div>
              <p className="form-hint">T2 has no backend default. Leave both empty only if you are sending raster_before_path / raster_after_path instead.</p>
            </>
          )}
        </div>
      )}

      {(showCloud || showSize) && (
        <div className="form-section">
          <div className="section-label"><span>FETCH OPTIONS</span></div>
          {showCloud && (
            <Field id="max_cloud_cover" label={`max_cloud_cover (${form.max_cloud_cover}%)`}>
              <input
                id="max_cloud_cover"
                className="form-range"
                type="range"
                min="0"
                max="100"
                value={form.max_cloud_cover}
                onChange={(e) => patch({ max_cloud_cover: Number(e.target.value) })}
              />
            </Field>
          )}
          {showSize && (
            <div className="form-grid-2">
              <Field id="width" label="width">
                <input id="width" className="form-input" type="number" min="1" max="4096" value={form.width}
                  onChange={(e) => patch({ width: Number(e.target.value) })} />
              </Field>
              <Field id="height" label="height">
                <input id="height" className="form-input" type="number" min="1" max="4096" value={form.height}
                  onChange={(e) => patch({ height: Number(e.target.value) })} />
              </Field>
            </div>
          )}
        </div>
      )}

      {showSar && (
        <div className="form-section">
          <div className="section-label"><span>SAR OPTIONS</span></div>
          <div className="toggle-group" id="field-polarization">
            {['VV', 'VH', 'HH', 'HV'].map((pol) => (
              <button
                key={pol}
                type="button"
                className={`toggle-chip ${(form.polarization || []).includes(pol) ? 'active' : ''}`}
                onClick={() => togglePolarization(pol)}
              >
                {pol}
              </button>
            ))}
          </div>
          <Field id="orbit_direction" label="orbit_direction" highlighted={highlighted.has('orbit_direction')}
            hint="Field name is orbit_direction — never orbit. BOTH does not substitute a missing pass.">
            <select
              id="orbit_direction"
              className="form-input"
              value={form.orbit_direction}
              onChange={(e) => patch({ orbit_direction: e.target.value })}
            >
              <option value="BOTH">BOTH</option>
              <option value="ASCENDING">ASCENDING</option>
              <option value="DESCENDING">DESCENDING</option>
            </select>
          </Field>
        </div>
      )}

      {showInputFile && (
        <div className="form-section">
          <div className="section-label"><span>MULTISPECTRAL FILE</span></div>
          {/*
            Backend has no upload endpoint — QueryRequest.input_file is a filesystem
            path resolved against the SatQuery folder. A <input type="file"> cannot
            supply that path, so this is a path field, not a browser upload.
          */}
          <PathInput
            id="input_file"
            label="input_file"
            value={form.input_file}
            onChange={(v) => patch({ input_file: v })}
            highlighted={highlighted.has('input_file')}
            placeholder="Tool_2_fetch_multispectral_imagery/test_runs/sample_multispectral_output.tif"
            hint="8-band multispectral GeoTIFF required, not RGB. Relative to the SatQuery folder or an absolute path."
          />
        </div>
      )}

      {showCompare && (
        <PathInput
          id="compare_with"
          label="compare_with (optional)"
          value={form.compare_with}
          onChange={(v) => patch({ compare_with: v })}
          highlighted={highlighted.has('compare_with')}
          placeholder="Second GeoTIFF for grid-alignment QA"
          hint="Optional. If pixelwise_operation_ready is false, downstream change detection is skipped."
        />
      )}

      {showPairFiles && (
        <div className="form-section">
          <div className="section-label"><span>BEFORE / AFTER RASTERS</span></div>
          <p className="form-hint">
            Provide both paths, or leave them empty and use bbox + T1/T2 dates so the backend fetches the pair.
          </p>
          <PathInput
            id="raster_before_path"
            label="raster_before_path (T1)"
            value={form.raster_before_path}
            onChange={(v) => patch({ raster_before_path: v })}
            highlighted={highlighted.has('raster_before_path')}
            placeholder="Baseline / pre-event GeoTIFF"
          />
          <PathInput
            id="raster_after_path"
            label="raster_after_path (T2)"
            value={form.raster_after_path}
            onChange={(v) => patch({ raster_after_path: v })}
            highlighted={highlighted.has('raster_after_path')}
            placeholder="Target / post-event GeoTIFF"
          />
        </div>
      )}

      {showLulc && (
        <div className="form-section">
          <div className="section-label"><span>LULC RASTER</span></div>
          <PathInput
            id="lulc_raster_path"
            label="lulc_raster_path"
            value={form.lulc_raster_path}
            onChange={(v) => patch({ lulc_raster_path: v })}
            highlighted={highlighted.has('lulc_raster_path')}
            placeholder="Tool_8_analyze_spatial_landcover_terrain/test_runs/sample_worldcover_10m.tif"
            hint="Required for land cover, wildfire, and flood. ESA WorldCover-class GeoTIFF."
          />
        </div>
      )}

      {showDem && (
        <PathInput
          id="dem_raster_path"
          label="dem_raster_path (optional)"
          value={form.dem_raster_path}
          onChange={(v) => patch({ dem_raster_path: v })}
          highlighted={highlighted.has('dem_raster_path')}
          placeholder="Optional DEM GeoTIFF in metres"
        />
      )}

      {showZone && (
        <PathInput
          id="zone_mask_path"
          label="zone_mask_path (optional)"
          value={form.zone_mask_path}
          onChange={(v) => patch({ zone_mask_path: v })}
          highlighted={highlighted.has('zone_mask_path')}
          placeholder="Optional Tool 7 change_mask.tif"
        />
      )}

      {showIndices && (
        <div className="form-section">
          <div className="section-label"><span>INDICES (default: all 10)</span></div>
          <div className="toggle-group">
            {ALL_INDICES.map((name) => (
              <button
                key={name}
                type="button"
                className={`toggle-chip ${(form.indices || []).includes(name) ? 'active' : ''}`}
                onClick={() => toggleIndex(name)}
              >
                {name}
              </button>
            ))}
          </div>
        </div>
      )}

      {showChangeAdvanced && (
        <div className="form-section">
          <button type="button" className="advanced-toggle" onClick={onToggleAdvanced}>
            {showAdvanced ? '▾' : '▸'} Advanced — Tool 7 threshold
          </button>
          {showAdvanced && (
            <div className="advanced-body">
              <div className="form-grid-2">
                <Field id="threshold_type" label="threshold_type">
                  <select id="threshold_type" className="form-input" value={form.threshold_type}
                    onChange={(e) => patch({ threshold_type: e.target.value })}>
                    <option value="absolute">absolute</option>
                    <option value="statistical">statistical</option>
                  </select>
                </Field>
                <Field id="threshold_value" label="threshold_value">
                  <input id="threshold_value" className="form-input" type="number" step="0.01" value={form.threshold_value}
                    onChange={(e) => patch({ threshold_value: e.target.value })} />
                </Field>
              </div>
              {!hideRelativePct && (
                <Field id="relative_change_threshold_percent" label="relative_change_threshold_percent"
                  hint="Hidden for SAR/flood — dB values do not support a relative % cutoff.">
                  <input id="relative_change_threshold_percent" className="form-input" type="number" step="1"
                    value={form.relative_change_threshold_percent}
                    onChange={(e) => patch({ relative_change_threshold_percent: e.target.value })}
                    placeholder="optional" />
                </Field>
              )}
              <Field id="mask_encoding" label="mask_encoding">
                <select id="mask_encoding" className="form-input" value={form.mask_encoding}
                  onChange={(e) => patch({ mask_encoding: e.target.value })}>
                  <option value="bipolar_3class">bipolar_3class</option>
                  <option value="severity_5class">severity_5class</option>
                </select>
              </Field>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
