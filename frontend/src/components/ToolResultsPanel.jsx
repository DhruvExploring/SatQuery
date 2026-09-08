import React, { useState } from 'react';
import { rasterDownloadUrl } from '../api/rasters';
import { RasterThumb } from './RasterViewer';

function unwrap(entry) {
  const result = entry?.result && typeof entry.result === 'object' ? entry.result : (entry || {});
  const data = result.data && typeof result.data === 'object' ? result.data : {};
  return { tool: entry?.tool || result.tool, result, data, duration: entry?.duration_ms };
}

function collectGeoTiffPaths(obj, acc = [], prefix = '') {
  if (!obj || typeof obj !== 'object') return acc;
  for (const [key, value] of Object.entries(obj)) {
    const pathKey = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string' && /path|file/i.test(key) && /\.(tif|tiff)$/i.test(value)) {
      acc.push({ key: pathKey, path: value });
    } else if (value && typeof value === 'object' && !Array.isArray(value)) {
      collectGeoTiffPaths(value, acc, pathKey);
    }
  }
  return acc;
}

function GeoTiffPath({ label, path }) {
  const [copied, setCopied] = useState(false);
  if (!path) return null;
  const name = String(path).split(/[/\\]/).pop();
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(path);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };
  return (
    <div className="geotiff-block">
      <RasterThumb path={path} label={label} />
      <div className="geotiff-row">
        <div>
          <div className="meta-label">{label}</div>
          <div className="geotiff-name">{name}</div>
          <div className="geotiff-path">{path}</div>
        </div>
        <div className="geotiff-actions">
          <a className="btn-secondary" href={rasterDownloadUrl(path)}>⬇ GeoTIFF</a>
          <button type="button" className="btn-secondary" onClick={copy}>
            {copied ? 'Copied' : 'Copy path'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  if (value === undefined || value === null || value === '') return null;
  const display = typeof value === 'object' ? JSON.stringify(value) : String(value);
  return (
    <div className="meta-item">
      <span className="meta-label">{label}</span>
      <span className="meta-value">{display}</span>
    </div>
  );
}

function FetchCard({ entry }) {
  const { tool, result, data, duration } = unwrap(entry);
  const filePath = data.file_path || result.file_path || result.file?.file_path;
  return (
    <div className="tool-result-card">
      <div className="tool-result-header">
        <span className="badge badge-format">{tool}</span>
        {duration != null && <span className="form-hint">{Number(duration).toFixed(0)} ms</span>}
      </div>
      <GeoTiffPath label="file_path" path={filePath} />
      <div className="metadata-grid">
        <Stat label="status" value={result.status} />
        <Stat label="scene" value={data.scene_id || data.product_id} />
        <Stat label="cloud" value={data.cloud_cover} />
        <Stat label="orbit_used" value={data.orbit_used || result.orbit_used} />
      </div>
    </div>
  );
}

function IndicesCard({ entry }) {
  const { tool, result, data, duration } = unwrap(entry);
  const filePath = data.file_path || result.file_path;
  const heuristic = result.heuristic_classification || data.heuristic_classification;
  return (
    <div className="tool-result-card">
      <div className="tool-result-header">
        <span className="badge badge-success">{tool}</span>
        {duration != null && <span className="form-hint">{Number(duration).toFixed(0)} ms</span>}
      </div>
      <GeoTiffPath label="indices GeoTIFF" path={filePath} />
      {heuristic && (
        <div className="detected-classes-section">
          <div className="detected-classes-title"><span>HEURISTIC VEGETATION CLASSES</span></div>
          <div className="classes-pills-wrap">
            {Object.entries(heuristic.classes || heuristic).filter(([, v]) => v && typeof v === 'object').map(([name, info]) => (
              <span key={name} className="class-pill class-agri">
                ● {name}{info.area_km2 != null ? ` (${info.area_km2} km²)` : ''}
              </span>
            ))}
            {!heuristic.classes && typeof heuristic === 'object' && Object.entries(heuristic)
              .filter(([, v]) => typeof v !== 'object')
              .map(([k, v]) => (
                <span key={k} className="class-pill class-forest">● {k}: {String(v)}</span>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

function InspectCard({ entry }) {
  const { tool, result, duration } = unwrap(entry);
  const raster = result.raster || {};
  const spatial = result.spatial || {};
  const quality = result.quality || {};
  const compatibility = result.compatibility;
  const filePath = result.file?.file_path;
  const pixelwise = compatibility?.pixelwise_operation_ready;
  return (
    <div className="tool-result-card">
      <div className="tool-result-header">
        <span className="badge badge-format">{tool}</span>
        {duration != null && <span className="form-hint">{Number(duration).toFixed(0)} ms</span>}
      </div>
      <GeoTiffPath label="inspected file" path={filePath} />
      <div className="metadata-grid">
        <Stat label="size" value={raster.width && raster.height ? `${raster.width} × ${raster.height}` : null} />
        <Stat label="bands" value={raster.band_count} />
        <Stat label="CRS" value={spatial.crs} />
        <Stat label="quality.is_valid_for_ml" value={quality.is_valid_for_ml === true ? 'true' : quality.is_valid_for_ml === false ? 'false' : null} />
      </div>
      {compatibility && (
        <div className={`qa-callout ${pixelwise ? 'ok' : 'warn'}`}>
          {pixelwise
            ? 'compatibility.pixelwise_operation_ready is true — grids are aligned for change detection.'
            : 'compatibility.pixelwise_operation_ready is false — this is why a downstream change-detection step was skipped. Re-project or re-grid the pair before retrying Tool 7.'}
        </div>
      )}
    </div>
  );
}

function ChangeCard({ entry }) {
  const { tool, result, duration } = unwrap(entry);
  const summary = result.change_summary || {};
  const products = result.generated_products || {};
  const loss = summary.significant_decrease?.area_km2;
  const gain = summary.significant_increase?.area_km2;
  return (
    <div className="tool-result-card">
      <div className="tool-result-header">
        <span className="badge badge-success">{tool}</span>
        {duration != null && <span className="form-hint">{Number(duration).toFixed(0)} ms</span>}
      </div>
      <div className="metadata-grid">
        <Stat label="loss km²" value={loss} />
        <Stat label="gain km²" value={gain} />
        <Stat label="net km²" value={summary.net_change_area_km2} />
      </div>
      <GeoTiffPath label="generated_products.difference_raster_path" path={products.difference_raster_path} />
      <GeoTiffPath label="change_mask_path" path={products.change_mask_path} />
    </div>
  );
}

function LandCoverCard({ entry }) {
  const { tool, result, duration } = unwrap(entry);
  const dominant = result.dominant_landcover || {};
  const patches = result.patch_statistics || result.fragmentation || result.patch_stats;
  return (
    <div className="tool-result-card">
      <div className="tool-result-header">
        <span className="badge badge-format">{tool}</span>
        {duration != null && <span className="form-hint">{Number(duration).toFixed(0)} ms</span>}
      </div>
      <div className="metadata-grid">
        <Stat label="dominant_landcover" value={dominant.name || dominant.class_name} />
        <Stat label="percentage" value={dominant.percentage} />
      </div>
      {patches && (
        <pre className="json-block">{JSON.stringify(patches, null, 2)}</pre>
      )}
    </div>
  );
}

function MissionCard({ entry }) {
  const { tool, result, duration } = unwrap(entry);
  const summary = result.executive_summary || {};
  const pipeline = result.pipeline;
  const paths = collectGeoTiffPaths(result);
  return (
    <div className="tool-result-card">
      <div className="tool-result-header">
        <span className="badge badge-success">{tool}</span>
        {duration != null && <span className="form-hint">{Number(duration).toFixed(0)} ms</span>}
      </div>
      {pipeline && (
        <div className="form-hint" style={{ marginBottom: '0.5rem' }}>
          pipeline: {typeof pipeline === 'string' ? pipeline : JSON.stringify(pipeline)}
        </div>
      )}
      {summary && Object.keys(summary).length > 0 && (
        <div className="metadata-grid">
          {Object.entries(summary).slice(0, 12).map(([k, v]) => (
            <Stat key={k} label={k} value={typeof v === 'object' ? JSON.stringify(v) : v} />
          ))}
        </div>
      )}
      {paths.map((item) => (
        <GeoTiffPath key={item.key} label={item.key} path={item.path} />
      ))}
    </div>
  );
}

function GenericCard({ entry }) {
  const { tool, result, data, duration } = unwrap(entry);
  const paths = collectGeoTiffPaths(result);
  const filePath = data.file_path || result.file_path;
  return (
    <div className="tool-result-card">
      <div className="tool-result-header">
        <span className="badge badge-tag">{tool || 'tool'}</span>
        {duration != null && <span className="form-hint">{Number(duration).toFixed(0)} ms</span>}
      </div>
      <GeoTiffPath label="file_path" path={filePath} />
      {paths.filter((p) => p.path !== filePath).map((item) => (
        <GeoTiffPath key={item.key} label={item.key} path={item.path} />
      ))}
      {result.status && result.status !== 'success' && (
        <div className="qa-callout warn">{result.error?.message || result.status}</div>
      )}
    </div>
  );
}

const FETCH_TOOLS = new Set([
  'fetch_optical_imagery',
  'fetch_satellite_imagery',
  'fetch_multispectral_imagery',
  'fetch_sar_imagery',
  'fetch_sar',
  'fetch_weather_environment',
  'fetch_weather'
]);

export default function ToolResultsPanel({ toolResults = [], kind }) {
  if (!toolResults.length) {
    if (kind === 'ok') return null;
    return <p className="form-hint">No tool results.</p>;
  }

  return (
    <div className="tool-results-list">
      {toolResults.map((entry, idx) => {
        const tool = entry?.tool || '';
        const key = `${tool}-${idx}`;
        if (FETCH_TOOLS.has(tool) || tool.startsWith('fetch_')) {
          return <FetchCard key={key} entry={entry} />;
        }
        if (tool === 'compute_vegetation_indices') return <IndicesCard key={key} entry={entry} />;
        if (tool === 'inspect_geotiff_metadata') return <InspectCard key={key} entry={entry} />;
        if (tool === 'analyze_temporal_change') return <ChangeCard key={key} entry={entry} />;
        if (tool === 'analyze_spatial_landcover_terrain') return <LandCoverCard key={key} entry={entry} />;
        if (String(tool).startsWith('workflow_')) return <MissionCard key={key} entry={entry} />;
        return <GenericCard key={key} entry={entry} />;
      })}
    </div>
  );
}
