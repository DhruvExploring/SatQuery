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
export default function ImageSlot({
  label,
  badgeLabel,
  slot,
  onChange,
  onReset,
  disabled,
  onOpenModal,
  isStageExpanded,
  onToggleStageExpanded
}) {
  const fileInputRef = useRef(null);
  const imgWrapRef = useRef(null);
  const viewportRef = useRef(null);
  const uploadTokenRef = useRef(0);
  const [dragStart, setDragStart] = useState(null);
  const [dragCurrent, setDragCurrent] = useState(null);
  const [imgFailed, setImgFailed] = useState(false);
  const [copiedBbox, setCopiedBbox] = useState(false);

  // Interactive Zoom, Pan, Box Zoom & Auto-Fit state
  const [zoom, setZoom] = useState(1.0);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [aspectRatio, setAspectRatio] = useState(1);
  const [toolMode, setToolMode] = useState('roi'); // 'roi' | 'zoombox' | 'pan'
  const [isPanning, setIsPanning] = useState(false);
  const [isSpacePressed, setIsSpacePressed] = useState(false);
  const [isShiftPressed, setIsShiftPressed] = useState(false);
  const panStartRef = useRef({ x: 0, y: 0 });
  const panOriginRef = useRef({ x: 0, y: 0 });

  useEffect(() => {
    setImgFailed(false);
    setZoom(1.0);
    setPan({ x: 0, y: 0 });
    setToolMode('roi');
  }, [slot.uploadedPath]);

  // Spacebar temporary pan mode & Shift zoombox modifier
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (
        e.code === 'Space' &&
        !e.repeat &&
        document.activeElement?.tagName !== 'INPUT' &&
        document.activeElement?.tagName !== 'TEXTAREA'
      ) {
        setIsSpacePressed(true);
      }
      if (e.key === 'Shift') {
        setIsShiftPressed(true);
      }
    };
    const handleKeyUp = (e) => {
      if (e.code === 'Space') {
        setIsSpacePressed(false);
      }
      if (e.key === 'Shift') {
        setIsShiftPressed(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, []);

  // Cursor-anchored wheel zoom on viewport (zooms directly at cursor point)
  useEffect(() => {
    const el = viewportRef.current;
    if (!el || !slot.uploadedPath) return;

    const handleWheel = (e) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      // Mouse position relative to center of viewport
      const mouseX = e.clientX - (rect.left + rect.width / 2);
      const mouseY = e.clientY - (rect.top + rect.height / 2);

      const factor = e.deltaY < 0 ? 1.2 : 0.833;

      setZoom((prevZoom) => {
        const nextZoom = Math.min(10.0, Math.max(0.5, Number((prevZoom * factor).toFixed(3))));
        if (Math.abs(nextZoom - 1.0) < 0.04) {
          setPan({ x: 0, y: 0 });
          return 1.0;
        }

        // Adjust pan so the specific place under the cursor stays fixed under the cursor
        setPan((prevPan) => {
          const ratio = nextZoom / prevZoom;
          const nextPanX = prevPan.x * ratio + mouseX * (1 - ratio);
          const nextPanY = prevPan.y * ratio + mouseY * (1 - ratio);
          return {
            x: Number(nextPanX.toFixed(1)),
            y: Number(nextPanY.toFixed(1))
          };
        });

        return nextZoom;
      });
    };

    el.addEventListener('wheel', handleWheel, { passive: false });
    return () => el.removeEventListener('wheel', handleWheel);
  }, [slot.uploadedPath]);

  const handleImageLoad = (e) => {
    const nw = e.target.naturalWidth;
    const nh = e.target.naturalHeight;
    if (nw && nh) {
      setAspectRatio(nw / nh);
    }
  };

  const handleZoomIn = () => setZoom((z) => Math.min(10.0, Number((z * 1.25).toFixed(2))));
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

  const handleDoubleClick = (e) => {
    if (zoom > 1.05) {
      handleResetFit();
    } else {
      if (!viewportRef.current) {
        setZoom(2.5);
        return;
      }
      const rect = viewportRef.current.getBoundingClientRect();
      const mouseX = e.clientX - (rect.left + rect.width / 2);
      const mouseY = e.clientY - (rect.top + rect.height / 2);
      const targetZoom = 2.5;
      setZoom(targetZoom);
      setPan({
        x: Math.round(-mouseX * (targetZoom - 1)),
        y: Math.round(-mouseY * (targetZoom - 1))
      });
    }
  };

  const handleZoomToRoi = () => {
    if (!slot.roi || !imgWrapRef.current) return;
    const { x, y, w, h } = slot.roi;
    if (w < 0.005 || h < 0.005) return;

    const boxCenterX = x + w / 2;
    const boxCenterY = y + h / 2;
    const targetZoom = Math.min(10.0, Math.max(1.2, Number((0.85 / Math.max(w, h)).toFixed(2))));

    const rect = imgWrapRef.current.getBoundingClientRect();
    const unscaledW = rect.width / zoom;
    const unscaledH = rect.height / zoom;
    const offX = (boxCenterX - 0.5) * unscaledW;
    const offY = (boxCenterY - 0.5) * unscaledH;

    setZoom(targetZoom);
    setPan({
      x: Math.round(-offX * targetZoom),
      y: Math.round(-offY * targetZoom)
    });
  };

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
      knowledgeBase: null,
      isUserUpload: true
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
      knowledgeBase: uploaded.knowledgeBase,
      isUserUpload: true
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
    setZoom(1.0);
    setPan({ x: 0, y: 0 });
    setAspectRatio(1);
    onReset();
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const fracFromEvent = (e) => {
    if (!imgWrapRef.current) return { x: 0, y: 0 };
    const rect = imgWrapRef.current.getBoundingClientRect();
    return {
      x: clamp01((e.clientX - rect.left) / rect.width),
      y: clamp01((e.clientY - rect.top) / rect.height)
    };
  };

  const handlePointerDown = (e) => {
    if (!slot.uploadedPath || disabled) return;
    const isPanAction = toolMode === 'pan' || isSpacePressed || e.button === 1 || e.button === 2;

    if (isPanAction) {
      e.preventDefault();
      e.currentTarget.setPointerCapture?.(e.pointerId);
      setIsPanning(true);
      panStartRef.current = { x: e.clientX, y: e.clientY };
      panOriginRef.current = { ...pan };
      return;
    }

    if (e.button === 0) {
      e.preventDefault();
      e.currentTarget.setPointerCapture?.(e.pointerId);
      const point = fracFromEvent(e);
      setDragStart(point);
      setDragCurrent(point);
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
      return;
    }

    if (dragStart) {
      setDragCurrent(fracFromEvent(e));
    }
  };

  const handlePointerUp = () => {
    if (isPanning) {
      setIsPanning(false);
      return;
    }
    finishDrag();
  };

  const finishDrag = () => {
    if (!dragStart || !dragCurrent) return;
    const x = Math.min(dragStart.x, dragCurrent.x);
    const y = Math.min(dragStart.y, dragCurrent.y);
    const w = Math.abs(dragCurrent.x - dragStart.x);
    const h = Math.abs(dragCurrent.y - dragStart.y);
    const isShiftZoom = isShiftPressed;
    setDragStart(null);
    setDragCurrent(null);

    if (w < 0.015 || h < 0.015) return;

    if (toolMode === 'zoombox' || isShiftZoom) {
      const boxCenterX = x + w / 2;
      const boxCenterY = y + h / 2;
      const targetZoom = Math.min(10.0, Math.max(1.2, Number((0.85 / Math.max(w, h)).toFixed(2))));

      if (imgWrapRef.current) {
        const rect = imgWrapRef.current.getBoundingClientRect();
        const unscaledW = rect.width / zoom;
        const unscaledH = rect.height / zoom;
        const offX = (boxCenterX - 0.5) * unscaledW;
        const offY = (boxCenterY - 0.5) * unscaledH;
        setZoom(targetZoom);
        setPan({
          x: Math.round(-offX * targetZoom),
          y: Math.round(-offY * targetZoom)
        });
      }
      return;
    }

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
          {badgeLabel ? (
            <span
              className={`slot-role-tag ${
                badgeLabel.startsWith('ORIGINAL')
                  ? 'badge-original'
                  : 'badge-generated'
              }`}
            >
              {badgeLabel}
            </span>
          ) : (
            <span className="slot-role-tag">{label}</span>
          )}
          {slot.originalFilename && (
            <span className="slot-filename" title={slot.originalFilename}>
              {slot.originalFilename}
            </span>
          )}
        </div>

        <div className="slot-header-actions">
          {slot.uploadedPath && onToggleStageExpanded && (
            <button
              type="button"
              className={`slot-action-btn ${isStageExpanded ? 'active-stage-btn' : ''}`}
              onClick={onToggleStageExpanded}
              title={isStageExpanded ? 'Restore standard split view' : 'Expand main preview stage for maximum viewing area'}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                {isStageExpanded ? (
                  <path d="M4 14h6v6M20 10h-6V4M14 10l7-7M10 14l-7 7" />
                ) : (
                  <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
                )}
              </svg>
              <span>{isStageExpanded ? 'Compact View' : 'Expand Stage'}</span>
            </button>
          )}

          {slot.uploadedPath && onOpenModal && (
            <button
              type="button"
              className="slot-action-btn"
              onClick={() => onOpenModal({ path: slot.uploadedPath, label: slot.originalFilename })}
              title="Inspect Fullscreen Modal (1536px)"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" />
              </svg>
              <span>Fullscreen</span>
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
        <div className="sat-viewport-frame" ref={viewportRef}>
          <div
            className="sat-image-canvas"
            ref={imgWrapRef}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerUp}
            onDoubleClick={handleDoubleClick}
            style={{
              aspectRatio: `${aspectRatio}`,
              maxWidth: '100%',
              maxHeight: '100%',
              width: aspectRatio >= 1 ? '100%' : 'auto',
              height: aspectRatio <= 1 ? '100%' : 'auto',
              transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
              transformOrigin: 'center center',
              transition: isPanning ? 'none' : 'transform 0.15s ease-out',
              cursor: isPanning
                ? 'grabbing'
                : toolMode === 'pan' || isSpacePressed
                ? 'grab'
                : toolMode === 'zoombox' || isShiftPressed
                ? 'zoom-in'
                : 'crosshair'
            }}
          >
            {!imgFailed ? (
              <img
                className="sat-preview-img"
                src={rasterPreviewUrl(slot.uploadedPath, 1536)}
                alt={slot.originalFilename}
                draggable={false}
                onLoad={handleImageLoad}
                onError={() => setImgFailed(true)}
              />
            ) : (
              <div className="sat-preview-failed">
                <span>Could not render raster preview</span>
              </div>
            )}

            {/* Zoom Box Drag Preview */}
            {(toolMode === 'zoombox' || isShiftPressed) && liveBox && (
              <div
                className="sat-zoombox-rect"
                style={{
                  left: `${liveBox.x * 100}%`,
                  top: `${liveBox.y * 100}%`,
                  width: `${liveBox.w * 100}%`,
                  height: `${liveBox.h * 100}%`
                }}
              >
                <span className="zoombox-rect-tag">🔍 Zoom to Area</span>
              </div>
            )}

            {/* Normal ROI Drag Box */}
            {toolMode !== 'zoombox' && !isShiftPressed && liveBox && (
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
          </div>

          {/* Floating Viewport Toolbar */}
          <div className="sat-viewport-toolbar">
            <div className="toolbar-tool-group">
              <button
                type="button"
                className={`v-tool-btn ${toolMode === 'roi' && !isSpacePressed && !isShiftPressed ? 'active-roi' : ''}`}
                onClick={() => setToolMode('roi')}
                title="Select ROI Region: Click and drag on image to mark analysis focus"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M4 7V4h3M20 7V4h-3M4 17v3h3M20 17v3h-3" />
                  <rect x="8" y="8" width="8" height="8" rx="1" />
                </svg>
                <span>ROI Tool</span>
              </button>
              <button
                type="button"
                className={`v-tool-btn ${toolMode === 'zoombox' || isShiftPressed ? 'active-zoombox' : ''}`}
                onClick={() => setToolMode('zoombox')}
                title="Zoom to Area: Drag a box anywhere (e.g. bottom-right corner) to zoom in directly"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
                  <circle cx="11" cy="11" r="7" />
                  <line x1="21" y1="21" x2="16" y2="16" />
                  <line x1="11" y1="8" x2="11" y2="14" />
                  <line x1="8" y1="11" x2="14" y2="11" />
                </svg>
                <span>Zoom Box</span>
              </button>
              <button
                type="button"
                className={`v-tool-btn ${toolMode === 'pan' || isSpacePressed ? 'active-pan' : ''}`}
                onClick={() => setToolMode('pan')}
                title="Pan Mode: Click and drag to move image around (or hold Spacebar)"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <path d="M18 11V6a2 2 0 0 0-4 0v5" />
                  <path d="M14 10V4a2 2 0 0 0-4 0v7" />
                  <path d="M10 10.5V6a2 2 0 0 0-4 0v8" />
                  <path d="M18 8a2 2 0 0 1 4 4v4a8 8 0 0 1-16 0v-2" />
                </svg>
                <span>Pan</span>
              </button>
            </div>

            <div className="toolbar-divider" />

            <div className="toolbar-zoom-group">
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
                title="Zoom Level (Click to Reset to Fit)"
              >
                {zoom === 1 ? 'Fit' : `${Math.round(zoom * 100)}%`}
              </button>
              <button
                type="button"
                className="v-zoom-btn"
                onClick={handleZoomIn}
                disabled={zoom >= 10.0}
                title="Zoom In (+)"
              >
                +
              </button>
            </div>

            <div className="toolbar-divider" />

            <button
              type="button"
              className={`v-preset-btn ${zoom === 1 ? 'active' : ''}`}
              onClick={handleResetFit}
              title="Reset to Fit View"
            >
              Fit
            </button>
            <button
              type="button"
              className={`v-preset-btn ${zoom === 2 ? 'active' : ''}`}
              onClick={() => setZoom(2.0)}
              title="200% Zoom"
            >
              2×
            </button>
            <button
              type="button"
              className={`v-preset-btn ${zoom === 4 ? 'active' : ''}`}
              onClick={() => setZoom(4.0)}
              title="400% Zoom"
            >
              4×
            </button>
          </div>

          {/* Quick Zoom / Pan Hint badge when zoomed */}
          {zoom > 1.05 && (
            <div className="sat-viewport-pan-hint">
              <span>
                {toolMode === 'pan' || isSpacePressed
                  ? 'Pan active: Drag to move scene'
                  : toolMode === 'zoombox' || isShiftPressed
                  ? 'Zoom Box active: Drag rectangle to zoom into area'
                  : 'Scroll on any corner to zoom in there • Hold Space to pan'}
              </span>
            </div>
          )}
        </div>
      )}

      {/* 1. User Marked ROI Status Readout */}
      {slot.uploadedPath && slot.roi && (
        <div className="sat-roi-chip-bar">
          <div className="roi-details-wrap">
            <span className="roi-active-label">
              <strong>Focused ROI:</strong> {roiBbox ? formatBbox(roiBbox) : 'Custom Region Marked'}
            </span>
            {roiBbox && (
              <span className="roi-center-sub">
                (Center: {formatLat((roiBbox.min_lat + roiBbox.max_lat) / 2)}, {formatLon((roiBbox.min_lon + roiBbox.max_lon) / 2)})
              </span>
            )}
          </div>
          <div className="roi-action-buttons">
            <button
              type="button"
              className="btn-roi-zoom"
              onClick={handleZoomToRoi}
              title="Zoom directly into this marked ROI region"
            >
              🔍 Zoom to Region
            </button>
            <button
              type="button"
              className="btn-roi-clear"
              onClick={() => onChange({ roi: null })}
              disabled={disabled}
            >
              Clear Region
            </button>
          </div>
        </div>
      )}

      {/* 2. AI Identified Region Overlay */}
      {slot.uploadedPath && (slot.modelPolygon || slot.modelBbox) && (
        <div className="sat-roi-chip-bar ai-detected">
          <span className="roi-active-label">
            AI identified region from analysis
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
              <span>SCENE SPATIAL METADATA</span>
            </div>
            <div className="meta-header-badges">
              <span className={`meta-geo-badge ${slot.info?.georeferenced !== false ? 'geo-ok' : 'geo-none'}`}>
                {slot.info?.georeferenced !== false ? 'Georeferenced' : 'Unreferenced'}
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
                    {copiedBbox ? 'Copied' : 'Copy'}
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
