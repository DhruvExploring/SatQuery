import React, { useEffect, useRef, useState } from 'react';
import { rasterDownloadUrl, rasterPreviewUrl } from '../api/rasters';

export default function RasterViewer({
  rasters = [],
  isRunning = false,
  emptyLabel = 'No imagery yet — run an optical, SAR, indices, or change query.'
}) {
  const [activeIdx, setActiveIdx] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [failed, setFailed] = useState({});
  const containerRef = useRef(null);

  useEffect(() => {
    setActiveIdx(0);
    setZoom(1);
    setPan({ x: 0, y: 0 });
    setFailed({});
  }, [rasters.map((r) => r.path).join('|')]);

  const active = rasters[Math.min(activeIdx, Math.max(rasters.length - 1, 0))] || null;

  const handleWheel = (e) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.15 : 0.15;
    setZoom((prev) => Math.min(Math.max(prev + delta, 0.5), 3.5));
  };

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.addEventListener('wheel', handleWheel, { passive: false });
    return () => el.removeEventListener('wheel', handleWheel);
  }, []);

  return (
    <div className="card viewer-card">
      <div className="viewer-topbar">
        <div className="viewer-file-info">
          <span className="badge badge-format">{active ? 'GeoTIFF' : 'AOI'}</span>
          <span>{active?.name || 'No raster'}</span>
          {active?.tool ? (
            <span className="badge badge-tag">{String(active.tool).replace(/_/g, ' ')}</span>
          ) : null}
        </div>
        <div className="viewer-file-stats">
          {active ? (
            <a className="btn-secondary" href={rasterDownloadUrl(active.path)} style={{ padding: '0.35rem 0.7rem' }}>
              ⬇ Download
            </a>
          ) : (
            <span>Waiting for imagery</span>
          )}
        </div>
      </div>

      <div
        className="viewport-container"
        ref={containerRef}
        onMouseDown={(e) => {
          if (e.button !== 0) return;
          setIsDragging(true);
          setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
        }}
        onMouseMove={(e) => {
          if (!isDragging) return;
          setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
        }}
        onMouseUp={() => setIsDragging(false)}
        onMouseLeave={() => setIsDragging(false)}
        style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
      >
        {isRunning && (
          <div className="raster-running">Fetching / rendering imagery…</div>
        )}
        {active && !failed[active.path] ? (
          <img
            src={rasterPreviewUrl(active.path, 1280)}
            alt={active.name}
            className="viewer-image raster-image"
            draggable="false"
            onError={() => setFailed((prev) => ({ ...prev, [active.path]: true }))}
            style={{
              objectFit: 'contain',
              transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
              transformOrigin: 'center center',
              transition: isDragging ? 'none' : 'transform 0.15s ease-out'
            }}
          />
        ) : (
          <div className="raster-empty">
            {active && failed[active.path]
              ? 'Preview could not be rendered. Use Download for the GeoTIFF.'
              : emptyLabel}
          </div>
        )}

        <div className="viewer-controls-bar">
          <button type="button" className="control-btn" onClick={() => setZoom((z) => Math.min(z + 0.25, 3.5))}>+</button>
          <button type="button" className="control-btn" onClick={() => setZoom((z) => Math.max(z - 0.25, 0.5))}>−</button>
          <button type="button" className="control-btn" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}>⛶</button>
        </div>
      </div>

      {rasters.length > 1 && (
        <div className="layer-carousel-container">
          {rasters.map((item, idx) => (
            <button
              key={`${item.path}-${idx}`}
              type="button"
              className={`layer-thumbnail-card ${idx === activeIdx ? 'active' : ''}`}
              onClick={() => { setActiveIdx(idx); setZoom(1); setPan({ x: 0, y: 0 }); }}
            >
              <img
                src={rasterPreviewUrl(item.path, 256)}
                alt={item.name}
                className="layer-thumb-preview"
                onError={(e) => { e.currentTarget.style.display = 'none'; }}
              />
              <span className="layer-thumb-title">{item.label || item.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function RasterThumb({ path, label }) {
  const [failed, setFailed] = useState(false);
  if (!path) return null;
  return (
    <div className="raster-thumb-wrap">
      {failed ? (
        <div className="raster-thumb-fallback">Preview unavailable</div>
      ) : (
        <img
          src={rasterPreviewUrl(path, 640)}
          alt={label || 'raster'}
          className="raster-thumb-img"
          onError={() => setFailed(true)}
        />
      )}
    </div>
  );
}
