import React, { useEffect, useRef, useState } from 'react';
import { rasterPreviewUrl, uploadRasterFile } from '../api/rasters';
import { computeApproxAreaKm2, formatBbox, formatLat, formatLon, roiBoxToBbox } from '../lib/geo';
import { inspectGeotiff } from '../lib/inspectGeotiff';

const clamp01 = (v) => Math.min(1, Math.max(0, v));

/**
 * One image upload+preview slot: file picker, server-side upload, a rendered
 * preview with a draggable region-of-interest box, and a quiet background
 * inspect_geotiff_metadata call (for the info chip and for converting the
 * drawn box into real coordinates).
 *
 * `onChange` receives a *patch* (merged onto the latest state by the parent
 * via functional setState) rather than a full replacement object -- an
 * earlier version spread the `slot` prop directly, which is a stale closure
 * across an `await`: a second update after the upload finished would revert
 * whatever the first update (before the upload started) had just cleared.
 * `onReset` fully clears the slot (a patch/merge can't remove keys).
 */
export default function ImageSlot({ label, slot, onChange, onReset, disabled, onOpenModal }) {
  const fileInputRef = useRef(null);
  const imgWrapRef = useRef(null);
  const uploadTokenRef = useRef(0);
  const [dragStart, setDragStart] = useState(null);
  const [dragCurrent, setDragCurrent] = useState(null);
  const [imgFailed, setImgFailed] = useState(false);
  const [copiedBbox, setCopiedBbox] = useState(false);

  useEffect(() => {
    setImgFailed(false);
  }, [slot.uploadedPath]);

  const handleFilePick = async (e) => {
    const picked = e.target.files?.[0] || null;
    e.target.value = '';
    if (!picked) return;
    if (!/\.(tif|tiff)$/i.test(picked.name)) {
      onChange({ error: 'Only .tif/.tiff GeoTIFF files are accepted.' });
      return;
    }

    const myToken = ++uploadTokenRef.current;
    onChange({
      uploading: true,
      error: null,
      uploadedPath: null,
      originalFilename: picked.name,
      boundsWgs84: null,
      info: null,
      roi: null,
      modelBbox: null,
      modelPolygon: null,
      knowledgeBase: null
    });

    const uploaded = await uploadRasterFile(picked);
    if (myToken !== uploadTokenRef.current) return;

    if (!uploaded.ok) {
      onChange({ uploading: false, error: uploaded.error });
      return;
    }

    onChange({
      uploading: false,
      uploadedPath: uploaded.path,
      originalFilename: picked.name,
      knowledgeBase: uploaded.knowledgeBase
    });
    runInspection(uploaded.path, myToken);
  };

  const runInspection = async (path, myToken) => {
    onChange({ inspecting: true });
    const patch = await inspectGeotiff(path);
    if (myToken !== uploadTokenRef.current) return;
    onChange({ inspecting: false, ...(patch || {}) });
  };

  const clearSlot = () => {
    uploadTokenRef.current += 1;
    onReset();
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const fracFromEvent = (e) => {
    const rect = imgWrapRef.current.getBoundingClientRect();
    return {
      x: clamp01((e.clientX - rect.left) / rect.width),
      y: clamp01((e.clientY - rect.top) / rect.height)
    };
  };

  const handlePointerDown = (e) => {
    if (!slot.uploadedPath || disabled) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture?.(e.pointerId);
    const point = fracFromEvent(e);
    setDragStart(point);
    setDragCurrent(point);
  };

  const handlePointerMove = (e) => {
    if (!dragStart) return;
    setDragCurrent(fracFromEvent(e));
  };

  const finishDrag = () => {
    if (!dragStart || !dragCurrent) return;
    const x = Math.min(dragStart.x, dragCurrent.x);
    const y = Math.min(dragStart.y, dragCurrent.y);
    const w = Math.abs(dragCurrent.x - dragStart.x);
    const h = Math.abs(dragCurrent.y - dragStart.y);
    setDragStart(null);
    setDragCurrent(null);
    if (w < 0.02 || h < 0.02) return;
    onChange({ roi: { x, y, w, h } });
  };

  const liveBox = dragStart && dragCurrent
    ? {
        x: Math.min(dragStart.x, dragCurrent.x),
        y: Math.min(dragStart.y, dragCurrent.y),
        w: Math.abs(dragCurrent.x - dragStart.x),
        h: Math.abs(dragCurrent.y - dragStart.y)
      }
    : slot.roi;

  const bounds = slot.boundsWgs84 || slot.info?.boundsWgs84 || null;
  const roiBbox = slot.roi && bounds ? roiBoxToBbox(slot.roi, bounds) : null;
  const approxArea = slot.info?.approxAreaKm2 || computeApproxAreaKm2(bounds);
  const centerLat = bounds ? (bounds.min_lat + bounds.max_lat) / 2 : null;
  const centerLon = bounds ? (bounds.min_lon + bounds.max_lon) / 2 : null;

  const copyBbox = () => {
    if (!bounds) return;
    const bboxStr = `[${bounds.min_lon.toFixed(4)}, ${bounds.min_lat.toFixed(4)}, ${bounds.max_lon.toFixed(4)}, ${bounds.max_lat.toFixed(4)}]`;
    navigator.clipboard?.writeText(bboxStr);
    setCopiedBbox(true);
    setTimeout(() => setCopiedBbox(false), 2000);
  };

  return (
    <div className="sat-visualizer-slot">
      {/* Top Header Row */}
      <div className="sat-slot-header">
        <div className="slot-title-group">
          <span className="slot-role-tag">{label}</span>
          {slot.originalFilename && (
            <span className="slot-filename" title={slot.originalFilename}>
              {slot.originalFilename}
            </span>
          )}
        </div>

        <div className="slot-header-actions">
          {slot.uploadedPath && onOpenModal && (
            <button
              type="button"
              className="slot-action-btn"
              onClick={() => onOpenModal({ path: slot.uploadedPath, label: slot.originalFilename })}
              title="Inspect Fullscreen (1536px)"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
              </svg>
              <span>Expand</span>
            </button>
          )}

          {slot.uploadedPath && (
            <button
              type="button"
              className="slot-action-btn btn-danger-soft btn-remove-tiff"
              onClick={clearSlot}
              disabled={disabled}
              title="Remove currently loaded TIFF"
              id="btn-remove-tiff"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
              <span>Remove TIFF</span>
            </button>
          )}
        </div>
      </div>

      {/* Main Viewport or Dropzone */}
      {!slot.uploadedPath ? (
        <label className={`sat-dropzone ${slot.uploading ? 'uploading' : ''}`}>
          <input
            ref={fileInputRef}
            type="file"
            accept=".tif,.tiff"
            onChange={handleFilePick}
            disabled={disabled || slot.uploading}
            hidden
          />
          <div className="dropzone-content">
            <div className="dropzone-icon-ring">
              {slot.uploading ? (
                <div className="radar-spinner-pulse" />
              ) : (
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
              )}
            </div>
            <div className="dropzone-text-block">
              <span className="dropzone-primary-text">
                {slot.uploading ? 'Uploading & Ingesting GeoTIFF…' : 'Drop satellite GeoTIFF or click to browse'}
              </span>
              <span className="dropzone-secondary-text">
                Sentinel-1 SAR, Sentinel-2 Optical/MSI, Landsat, or custom GeoTIFFs (.tif, .tiff)
              </span>
            </div>
          </div>
        </label>
      ) : (
        <div className="sat-viewport-frame">
          <div
            className="sat-image-canvas"
            ref={imgWrapRef}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={finishDrag}
            onPointerLeave={finishDrag}
          >
            {!imgFailed ? (
              <img
                src={rasterPreviewUrl(slot.uploadedPath, 1200)}
                alt={slot.originalFilename}
                draggable={false}
                onError={() => setImgFailed(true)}
              />
            ) : (
              <div className="sat-preview-failed">
                <span>⚠️ Could not render raster preview</span>
              </div>
            )}

            {/* ROI Drag Box */}
            {liveBox && (
              <div
                className="sat-roi-rect"
                style={{
                  left: `${liveBox.x * 100}%`,
                  top: `${liveBox.y * 100}%`,
                  width: `${liveBox.w * 100}%`,
                  height: `${liveBox.h * 100}%`
                }}
              >
                <span className="roi-rect-tag">ROI Focus</span>
              </div>
            )}

            {/* AI Model Detections */}
            {slot.modelPolygon ? (
              <svg className="sat-model-polygon" viewBox="0 0 100 100" preserveAspectRatio="none">
                <polygon points={slot.modelPolygon.map(([x, y]) => `${x * 100},${y * 100}`).join(' ')} />
              </svg>
            ) : (
              slot.modelBbox && (
                <div
                  className="sat-model-bbox"
                  style={{
                    left: `${slot.modelBbox[0] * 100}%`,
                    top: `${slot.modelBbox[1] * 100}%`,
                    width: `${(slot.modelBbox[2] - slot.modelBbox[0]) * 100}%`,
                    height: `${(slot.modelBbox[3] - slot.modelBbox[1]) * 100}%`
                  }}
                >
                  <span className="model-bbox-tag">AI Detection</span>
                </div>
              )
            )}

            {/* Hint overlay */}
            <div className="sat-canvas-hint">Drag a box on the image to focus your query</div>
          </div>
        </div>
      )}

      {/* 1. User Marked ROI Status Readout */}
      {slot.uploadedPath && slot.roi && (
        <div className="sat-roi-chip-bar">
          <div className="roi-details-wrap">
            <span className="roi-active-label">
              🎯 <strong>Focused ROI:</strong> {roiBbox ? formatBbox(roiBbox) : 'Custom Region Marked'}
            </span>
            {roiBbox && (
              <span className="roi-center-sub">
                (Center: {formatLat((roiBbox.min_lat + roiBbox.max_lat) / 2)}, {formatLon((roiBbox.min_lon + roiBbox.max_lon) / 2)})
              </span>
            )}
          </div>
          <button
            type="button"
            className="btn-roi-clear"
            onClick={() => onChange({ roi: null })}
            disabled={disabled}
          >
            Clear Region
          </button>
        </div>
      )}

      {/* 2. AI Identified Region Overlay */}
      {slot.uploadedPath && (slot.modelPolygon || slot.modelBbox) && (
        <div className="sat-roi-chip-bar ai-detected">
          <span className="roi-active-label">
            ✨ AI identified region from analysis
          </span>
          <button
            type="button"
            className="btn-roi-clear"
            onClick={() => onChange({ modelBbox: null, modelPolygon: null })}
            disabled={disabled}
          >
            Clear AI Overlay
          </button>
        </div>
      )}

      {/* 3. Comprehensive GeoTIFF Spatial & Raster Metadata Panel */}
      {slot.uploadedPath && (bounds || slot.info) && (
        <div className="sat-image-metadata-card">
          <div className="metadata-card-header">
            <div className="meta-header-title">
              <span className="meta-icon">🛰️</span>
              <span>SCENE SPATIAL METADATA</span>
            </div>
            <div className="meta-header-badges">
              <span className={`meta-geo-badge ${slot.info?.georeferenced !== false ? 'geo-ok' : 'geo-none'}`}>
                {slot.info?.georeferenced !== false ? '✓ Georeferenced' : '⚠️ Unreferenced'}
              </span>
              {slot.info?.crs && (
                <span className="meta-crs-badge">{slot.info.crs}</span>
              )}
            </div>
          </div>

          <div className="sat-metadata-grid">
            {/* Latitude Range & Center */}
            {bounds && (
              <div className="meta-data-cell highlight-coord">
                <span className="cell-label">Latitude (Lat)</span>
                <span className="cell-val">
                  {formatLat(bounds.min_lat)} to {formatLat(bounds.max_lat)}
                </span>
                {centerLat != null && (
                  <span className="cell-subval">Center: {formatLat(centerLat)}</span>
                )}
              </div>
            )}

            {/* Longitude Range & Center */}
            {bounds && (
              <div className="meta-data-cell highlight-coord">
                <span className="cell-label">Longitude (Lon)</span>
                <span className="cell-val">
                  {formatLon(bounds.min_lon)} to {formatLon(bounds.max_lon)}
                </span>
                {centerLon != null && (
                  <span className="cell-subval">Center: {formatLon(centerLon)}</span>
                )}
              </div>
            )}

            {/* Bounding Box Array with Copy Action */}
            {bounds && (
              <div className="meta-data-cell cell-bbox">
                <div className="bbox-cell-head">
                  <span className="cell-label">Bounding Box (BBox)</span>
                  <button
                    type="button"
                    className="btn-copy-bbox"
                    onClick={copyBbox}
                    title="Copy bounding box array to clipboard"
                  >
                    {copiedBbox ? '✓ Copied' : '📋 Copy'}
                  </button>
                </div>
                <code className="cell-code">
                  [{bounds.min_lon.toFixed(4)}, {bounds.min_lat.toFixed(4)}, {bounds.max_lon.toFixed(4)}, {bounds.max_lat.toFixed(4)}]
                </code>
              </div>
            )}

            {/* Dimensions */}
            {slot.info?.width && (
              <div className="meta-data-cell">
                <span className="cell-label">Dimensions</span>
                <span className="cell-val">{slot.info.width} × {slot.info.height} px</span>
              </div>
            )}

            {/* Bands */}
            {slot.info?.bandCount && (
              <div className="meta-data-cell">
                <span className="cell-label">Bands</span>
                <span className="cell-val">{slot.info.bandCount} band{slot.info.bandCount > 1 ? 's' : ''}</span>
              </div>
            )}

            {/* Approx Area */}
            {approxArea && (
              <div className="meta-data-cell">
                <span className="cell-label">Coverage Area</span>
                <span className="cell-val">{approxArea} km²</span>
              </div>
            )}

            {/* Ground Sampling Distance / Pixel Size */}
            {slot.info?.pixelSizeWgs84Degrees && (
              <div className="meta-data-cell">
                <span className="cell-label">Resolution (GSD)</span>
                <span className="cell-val">
                  {slot.info.pixelSizeWgs84Degrees.lon_per_pixel.toExponential(2)}°/px
                </span>
              </div>
            )}

            {/* Format & Size */}
            {(slot.info?.driver || slot.info?.fileSizeBytes) && (
              <div className="meta-data-cell">
                <span className="cell-label">Format & Size</span>
                <span className="cell-val">
                  {slot.info.driver || 'GTiff'}
                  {slot.info.fileSizeBytes ? ` · ${(slot.info.fileSizeBytes / (1024 * 1024)).toFixed(2)} MB` : ''}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 4. Background Ingestion & Inspection Banner */}
      {slot.inspecting && (
        <div className="sat-inspecting-banner">
          <span className="radar-mini-pulse" />
          <span>Inspecting GeoTIFF metadata & extracting coordinates…</span>
        </div>
      )}

      {slot.error && <div className="sat-slot-error">{slot.error}</div>}
    </div>
  );
}
