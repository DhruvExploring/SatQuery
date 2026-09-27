import React, { useEffect, useRef, useState } from 'react';
import { rasterDownloadUrl, rasterPreviewUrl } from '../api/rasters';

export default function RasterModal({ raster, onClose }) {
  const [zoom, setZoom] = useState(1.0);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const viewportRef = useRef(null);
  const panStartRef = useRef({ x: 0, y: 0 });
  const panOriginRef = useRef({ x: 0, y: 0 });

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const handleWheel = (e) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.15 : 0.87;
      setZoom((prev) => {
        const next = Math.min(8.0, Math.max(0.5, Number((prev * factor).toFixed(2))));
        if (Math.abs(next - 1.0) < 0.05) {
          setPan({ x: 0, y: 0 });
          return 1.0;
        }
        return next;
      });
    };
    el.addEventListener('wheel', handleWheel, { passive: false });
    return () => el.removeEventListener('wheel', handleWheel);
  }, []);

  if (!raster) return null;

  const preview = rasterPreviewUrl(raster.path, 1536);
  const download = rasterDownloadUrl(raster.path);
  const filename = raster.path.split(/[/\\]/).pop();

  const handleZoomIn = () => setZoom((z) => Math.min(8.0, Number((z * 1.25).toFixed(2))));
  const handleZoomOut = () =>
    setZoom((z) => {
      const next = Math.max(0.5, Number((z / 1.25).toFixed(2)));
      if (next <= 1.05) {
        setPan({ x: 0, y: 0 });
        return 1.0;
      }
      return next;
    });
  const handleResetFit = () => {
    setZoom(1.0);
    setPan({ x: 0, y: 0 });
  };
  const handleDoubleClick = () => {
    if (zoom > 1.05) {
      handleResetFit();
    } else {
      setZoom(2.0);
    }
  };

  const handlePointerDown = (e) => {
    if (e.button === 0 || e.button === 1) {
      e.preventDefault();
      e.currentTarget.setPointerCapture?.(e.pointerId);
      setIsPanning(true);
      panStartRef.current = { x: e.clientX, y: e.clientY };
      panOriginRef.current = { ...pan };
    }
  };

  const handlePointerMove = (e) => {
    if (isPanning) {
      const dx = e.clientX - panStartRef.current.x;
      const dy = e.clientY - panStartRef.current.y;
      setPan({
        x: panOriginRef.current.x + dx,
        y: panOriginRef.current.y + dy
      });
    }
  };

  const handlePointerUp = () => {
    setIsPanning(false);
  };

  return (
    <div className="raster-modal-backdrop" onClick={onClose}>
      <div className="raster-modal-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="raster-modal-head">
          <div className="raster-modal-title">
            <div>
              <h3>{raster.label || filename}</h3>
              <code className="raster-path">{raster.path}</code>
            </div>
          </div>
          <div className="modal-head-actions">
            <a
              href={download}
              target="_blank"
              rel="noreferrer"
              className="btn-cyan btn-sm"
              download
            >
              Download GeoTIFF
            </a>
            <button type="button" className="btn-close-modal" onClick={onClose}>
              ✕
            </button>
          </div>
        </div>

        <div className="raster-modal-body">
          <div className="raster-view-frame" ref={viewportRef}>
            <div
              className="raster-view-canvas"
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerCancel={handlePointerUp}
              onDoubleClick={handleDoubleClick}
              style={{
                transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
                transformOrigin: 'center center',
                transition: isPanning ? 'none' : 'transform 0.15s ease-out',
                cursor: isPanning ? 'grabbing' : (zoom > 1.0 ? 'grab' : 'default')
              }}
            >
              <img src={preview} alt={raster.label || filename} draggable={false} />
            </div>

            {/* Floating Modal Toolbar */}
            <div className="raster-modal-toolbar">
              <button
                type="button"
                className="v-zoom-btn"
                onClick={handleZoomOut}
                disabled={zoom <= 0.5}
                title="Zoom Out (−)"
              >
                −
              </button>
              <button
                type="button"
                className="v-zoom-display"
                onClick={handleResetFit}
                title="Click to Reset to Fit"
              >
                {zoom === 1 ? 'Fit' : `${Math.round(zoom * 100)}%`}
              </button>
              <button
                type="button"
                className="v-zoom-btn"
                onClick={handleZoomIn}
                disabled={zoom >= 8.0}
                title="Zoom In (+)"
              >
                +
              </button>
              <div className="toolbar-divider" />
              <button
                type="button"
                className={`v-preset-btn ${zoom === 1 ? 'active' : ''}`}
                onClick={handleResetFit}
              >
                Fit
              </button>
              <button
                type="button"
                className={`v-preset-btn ${zoom === 2 ? 'active' : ''}`}
                onClick={() => setZoom(2.0)}
              >
                2×
              </button>
            </div>
          </div>
        </div>

        <div className="raster-modal-footer">
          <span className="footer-meta">
            {zoom > 1.05
              ? `Zoom: ${Math.round(zoom * 100)}% • Drag to pan • Scroll wheel to zoom`
              : 'Full 1536px preview rendering. Scroll or click + to zoom in, inspect details, and download raw uncompressed raster.'}
          </span>
          <button type="button" className="btn-glass btn-sm" onClick={onClose}>
            Close Preview
          </button>
        </div>
      </div>
    </div>
  );
}
