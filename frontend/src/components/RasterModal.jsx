import React, { useEffect } from 'react';
import { rasterDownloadUrl, rasterPreviewUrl } from '../api/rasters';

export default function RasterModal({ raster, onClose }) {
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  if (!raster) return null;

  const preview = rasterPreviewUrl(raster.path, 1536);
  const download = rasterDownloadUrl(raster.path);
  const filename = raster.path.split(/[/\\]/).pop();

  return (
    <div className="raster-modal-backdrop" onClick={onClose}>
      <div className="raster-modal-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="raster-modal-head">
          <div className="raster-modal-title">
            <span className="raster-icon">🗺️</span>
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
          <div className="raster-view-frame">
            <img src={preview} alt={raster.label || filename} />
          </div>
        </div>

        <div className="raster-modal-footer">
          <span className="footer-meta">Full 1536px preview rendering. Inspect details and download raw uncompressed raster.</span>
          <button type="button" className="btn-glass btn-sm" onClick={onClose}>
            Close Preview
          </button>
        </div>
      </div>
    </div>
  );
}
