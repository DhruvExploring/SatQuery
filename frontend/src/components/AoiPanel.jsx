import React from 'react';
import RasterViewer from './RasterViewer';
import { LOCATION_PRESETS, parseBbox } from '../state/intents';

function LocationMeta({ form, bbox, patch }) {
  return (
    <div className="metadata-panel">
      <div className="panel-header">
        <span>Location presets</span>
      </div>
      <div className="example-chips-wrap">
        {Object.values(LOCATION_PRESETS).map((preset) => (
          <button
            key={preset.id}
            type="button"
            className={`example-chip ${form.locationPreset === preset.id ? 'active' : ''}`}
            onClick={() => {
              const [min_lon, min_lat, max_lon, max_lat] = preset.bbox;
              patch({
                locationPreset: preset.id,
                min_lon: String(min_lon),
                min_lat: String(min_lat),
                max_lon: String(max_lon),
                max_lat: String(max_lat)
              });
            }}
          >
            {preset.name}
          </button>
        ))}
      </div>
      <div className="metadata-grid" style={{ marginTop: '1rem' }}>
        <div className="meta-item">
          <span className="meta-label">BBOX</span>
          <span className="meta-value">{bbox ? `[${bbox.join(', ')}]` : '—'}</span>
        </div>
        <div className="meta-item">
          <span className="meta-label">CLOUD COVER</span>
          <span className="meta-value">{form.max_cloud_cover}%</span>
        </div>
        <div className="meta-item">
          <span className="meta-label">T1</span>
          <span className="meta-value">{form.start_date} → {form.end_date}</span>
        </div>
        <div className="meta-item">
          <span className="meta-label">T2</span>
          <span className="meta-value">
            {form.post_start_date && form.post_end_date
              ? `${form.post_start_date} → ${form.post_end_date}`
              : 'not set'}
          </span>
        </div>
      </div>
    </div>
  );
}

export default function AoiPanel({
  form,
  onChange,
  highlightedFields = [],
  rasters = [],
  isRunning = false
}) {
  const bbox = parseBbox(form);
  const highlighted = new Set(highlightedFields);
  const patch = (partial) => onChange({ ...form, ...partial });

  const x = bbox ? ((bbox[0] + 180) / 360) * 100 : 50;
  const y = bbox ? ((90 - bbox[3]) / 180) * 100 : 40;
  const w = bbox ? ((bbox[2] - bbox[0]) / 360) * 100 : 8;
  const h = bbox ? ((bbox[3] - bbox[1]) / 180) * 100 : 6;

  if (rasters.length > 0) {
    return (
      <div className="aoi-stack">
        <RasterViewer
          rasters={rasters}
          isRunning={isRunning}
          emptyLabel="Imagery from the last query."
        />
        <div className="card">
          <LocationMeta form={form} bbox={bbox} patch={patch} />
        </div>
      </div>
    );
  }

  return (
    <div className="card viewer-card">
      <div className="viewer-topbar">
        <div className="viewer-file-info">
          <span className="badge badge-format">EPSG:4326</span>
          <span>Area of interest</span>
          <span className="badge badge-tag">bbox / lat-lon</span>
        </div>
        <div className="viewer-file-stats">
          <span>{form.width} × {form.height}</span>
          <span>{form.start_date} → {form.end_date}</span>
        </div>
      </div>

      <div className={`aoi-map ${highlighted.has('bbox') ? 'field-highlight' : ''}`} id="aoi-map">
        <svg viewBox="0 0 100 56" className="aoi-svg" preserveAspectRatio="none">
          <rect x="0" y="0" width="100" height="56" fill="#07101f" />
          <g stroke="#1b2842" strokeWidth="0.3">
            {[0, 25, 50, 75, 100].map((v) => (
              <line key={`v${v}`} x1={v} y1="0" x2={v} y2="56" />
            ))}
            {[0, 14, 28, 42, 56].map((v) => (
              <line key={`h${v}`} x1="0" y1={v} x2="100" y2={v} />
            ))}
          </g>
          {bbox && (
            <rect
              x={Math.max(0, x)}
              y={Math.max(0, (y / 100) * 56)}
              width={Math.max(1.2, w)}
              height={Math.max(1.2, (h / 100) * 56)}
              fill="rgba(56, 189, 248, 0.25)"
              stroke="#38bdf8"
              strokeWidth="0.6"
            />
          )}
        </svg>
        <div className="aoi-caption">
          {bbox
            ? `[${bbox.map((n) => n.toFixed(4)).join(', ')}]`
            : 'Enter a complete bbox to send location'}
        </div>
        {isRunning && (
          <div className="raster-running">Running query — imagery will appear here when a raster is returned.</div>
        )}
      </div>

      <LocationMeta form={form} bbox={bbox} patch={patch} />
    </div>
  );
}
