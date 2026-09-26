import React, { useEffect, useRef, useState } from 'react';
import { rasterPreviewUrl, uploadRasterFile } from '../api/rasters';
import { computeApproxAreaKm2, formatBbox, formatLat, formatLon } from '../lib/geo';
import { inspectGeotiff } from '../lib/inspectGeotiff';

/**
 * Professional Geospatial Two-TIFF Comparison Viewer
 * 
 * Features:
 * - Equal visual panels with synchronized sizing (Side-by-side)
 * - Interactive curtain comparator with draggable divider (Swipe)
 * - Rapid visual blink / switcher between T1 and T2 (Toggle)
 * - Clear T1 / T2 headers with compact metadata and remove actions
 * - Inline dropzones for unpopulated slots
 * - Preserves aspect ratio with zero nested-card bloat
 */
export default function TemporalComparisonViewer({
  slotA,
  slotB,
  onChangeA,
  onChangeB,
  onRemoveA,
  onRemoveB,
  onOpenModal,
  disabled
}) {
  const [compareMode, setCompareMode] = useState('side-by-side'); // 'side-by-side' | 'swipe' | 'toggle'
  const [sliderPos, setSliderPos] = useState(50); // 0 - 100 for swipe
  const [activeToggle, setActiveToggle] = useState('T1'); // 'T1' | 'T2' for toggle
  const [isAutoBlinking, setIsAutoBlinking] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  const containerRef = useRef(null);
  const fileInputARef = useRef(null);
  const fileInputBRef = useRef(null);

  const imgA = slotA?.uploadedPath ? rasterPreviewUrl(slotA.uploadedPath, 1024) : null;
  const imgB = slotB?.uploadedPath ? rasterPreviewUrl(slotB.uploadedPath, 1024) : null;
  const bothLoaded = Boolean(imgA && imgB);

  const boundsA = slotA?.boundsWgs84 || slotA?.info?.boundsWgs84 || null;
  const boundsB = slotB?.boundsWgs84 || slotB?.info?.boundsWgs84 || null;
  const approxAreaA = slotA?.info?.approxAreaKm2 || computeApproxAreaKm2(boundsA);
  const approxAreaB = slotB?.info?.approxAreaKm2 || computeApproxAreaKm2(boundsB);
  const centerLatA = boundsA ? (boundsA.min_lat + boundsA.max_lat) / 2 : null;
  const centerLonA = boundsA ? (boundsA.min_lon + boundsA.max_lon) / 2 : null;
  const centerLatB = boundsB ? (boundsB.min_lat + boundsB.max_lat) / 2 : null;
  const centerLonB = boundsB ? (boundsB.min_lon + boundsB.max_lon) / 2 : null;

  // Auto-Blink timer for Toggle mode
  useEffect(() => {
    let interval = null;
    if (compareMode === 'toggle' && isAutoBlinking && bothLoaded) {
      interval = setInterval(() => {
        setActiveToggle((prev) => (prev === 'T1' ? 'T2' : 'T1'));
      }, 800);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [compareMode, isAutoBlinking, bothLoaded]);

  // Swipe dragging handlers
  const handlePointerDown = (e) => {
    if (compareMode !== 'swipe' || !bothLoaded) return;
    setIsDragging(true);
    e.currentTarget.setPointerCapture?.(e.pointerId);
    updateSlider(e);
  };

  const handlePointerMove = (e) => {
    if (!isDragging || compareMode !== 'swipe') return;
    updateSlider(e);
  };

  const handlePointerUp = () => {
    setIsDragging(false);
  };

  const updateSlider = (e) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
    setSliderPos((x / rect.width) * 100);
  };

  // Upload handler for either slot
  const handleUpload = async (file, slotKey) => {
    if (!file || !/\.(tif|tiff)$/i.test(file.name)) return;
    const onChange = slotKey === 'A' ? onChangeA : onChangeB;

    onChange({
      uploading: true,
      error: null,
      uploadedPath: null,
      originalFilename: file.name,
      boundsWgs84: null,
      info: null,
      roi: null
    });

    const res = await uploadRasterFile(file);
    if (!res.ok) {
      onChange({ uploading: false, error: res.error });
      return;
    }

    onChange({
      uploading: false,
      uploadedPath: res.path,
      originalFilename: file.name,
      inspecting: true
    });

    const meta = await inspectGeotiff(res.path);
    if (meta) {
      onChange({ inspecting: false, ...meta });
    } else {
      onChange({ inspecting: false });
    }
  };

  return (
    <div className="temporal-workstation-viewer">
      {/* Top Comparison Controls Bar */}
      <div className="viewer-toolbar">
        <div className="viewer-toolbar-left">
          <span className="viewer-title">TEMPORAL COMPARISON</span>
          {bothLoaded && (
            <span className="viewer-status-badge">
              Synchronized EPSG:4326
            </span>
          )}
        </div>

        {/* Compact Mode Switcher */}
        <div className="compare-mode-control">
          <button
            type="button"
            className={`mode-btn ${compareMode === 'side-by-side' ? 'active' : ''}`}
            onClick={() => { setCompareMode('side-by-side'); setIsAutoBlinking(false); }}
            title="Two equal visual panels with synchronized sizing"
          >
            <span className="mode-icon">◫</span>
            <span>Side-by-side</span>
          </button>

          <button
            type="button"
            className={`mode-btn ${compareMode === 'swipe' ? 'active' : ''}`}
            onClick={() => { setCompareMode('swipe'); setIsAutoBlinking(false); }}
            title="Interactive swipe curtain comparator"
          >
            <span className="mode-icon">⇄</span>
            <span>Swipe</span>
          </button>

          <button
            type="button"
            className={`mode-btn ${compareMode === 'toggle' ? 'active' : ''}`}
            onClick={() => setCompareMode('toggle')}
            title="Instant toggle / auto-blink between T1 and T2"
          >
            <span className="mode-icon">⇋</span>
            <span>Toggle</span>
          </button>
        </div>
      </div>

      {/* Main Viewport Stage depending on mode */}
      <div className="viewer-viewport-stage">
        {/* =================================================================== */}
        {/* 1. SIDE-BY-SIDE MODE: Two Equal Synchronized Visual Panels          */}
        {/* =================================================================== */}
        {compareMode === 'side-by-side' && (
          <div className="compare-side-by-side-grid">
            {/* Panel T1 (Reference) */}
            <div className="t-panel t1-panel">
              <div className="t-panel-header">
                <div className="t-label-group">
                  <span className="t-tag tag-t1">T1</span>
                  <span className="t-role">Reference</span>
                  {slotA?.originalFilename && (
                    <span className="t-filename" title={slotA.originalFilename}>
                      {slotA.originalFilename}
                    </span>
                  )}
                </div>

                <div className="t-actions-group">
                  {imgA && onOpenModal && (
                    <button
                      type="button"
                      className="t-action-btn"
                      onClick={() => onOpenModal({ path: slotA.uploadedPath, label: `T1: ${slotA.originalFilename}` })}
                      title="Inspect T1 Fullscreen"
                    >
                      <span>🔍</span>
                    </button>
                  )}
                  {slotA?.uploadedPath && (
                    <button
                      type="button"
                      className="t-action-btn t-btn-remove"
                      onClick={onRemoveA}
                      disabled={disabled}
                      title="Remove T1 TIFF"
                    >
                      ✕ Remove
                    </button>
                  )}
                </div>
              </div>

              {/* Viewport or Dropzone T1 */}
              {!slotA?.uploadedPath ? (
                <label className="t-dropzone">
                  <input
                    ref={fileInputARef}
                    type="file"
                    accept=".tif,.tiff"
                    onChange={(e) => {
                      if (e.target.files?.[0]) handleUpload(e.target.files[0], 'A');
                      e.target.value = '';
                    }}
                    disabled={disabled || slotA?.uploading}
                    hidden
                  />
                  <div className="t-dropzone-inner">
                    <span className="drop-plus">＋</span>
                    <span className="drop-title">
                      {slotA?.uploading ? 'Uploading T1…' : 'Drop T1 Reference (.tif)'}
                    </span>
                    <span className="drop-hint">Browse GeoTIFF</span>
                  </div>
                </label>
              ) : (
                <div className="t-frame">
                  <img src={imgA} alt="T1 Reference" className="t-img" />
                  {slotA.modelBbox && <div className="t-bbox-overlay" />}
                </div>
              )}

              {/* Compact Monospace Metadata */}
              {slotA?.uploadedPath && (boundsA || slotA?.info) && (
                <div className="t-meta-strip">
                  {boundsA && (
                    <div className="t-meta-row t-coords-row">
                      <span className="t-coord-badge">
                        <span className="c-tag">LAT</span> {formatLat(boundsA.min_lat)}–{formatLat(boundsA.max_lat)}
                      </span>
                      <span className="t-coord-badge">
                        <span className="c-tag">LON</span> {formatLon(boundsA.min_lon)}–{formatLon(boundsA.max_lon)}
                      </span>
                      {centerLatA != null && (
                        <span className="t-coord-badge c-center">
                          <span className="c-tag">CTR</span> {formatLat(centerLatA)}, {formatLon(centerLonA)}
                        </span>
                      )}
                    </div>
                  )}
                  <div className="t-meta-row t-specs-row">
                    {slotA.info?.width && (
                      <span className="t-spec-item">{slotA.info.width}×{slotA.info.height} px</span>
                    )}
                    {slotA.info?.bandCount && (
                      <span className="t-spec-item">{slotA.info.bandCount}B</span>
                    )}
                    <span className="t-spec-item">{slotA.info?.crs || 'EPSG:4326'}</span>
                    {approxAreaA && (
                      <span className="t-spec-item">{approxAreaA} km²</span>
                    )}
                    <span className="t-spec-item">{slotA.info?.georeferenced !== false ? '✓ Georef' : 'Unreferenced'}</span>
                  </div>
                </div>
              )}
            </div>

            {/* Panel T2 (Comparison) */}
            <div className="t-panel t2-panel">
              <div className="t-panel-header">
                <div className="t-label-group">
                  <span className="t-tag tag-t2">T2</span>
                  <span className="t-role">Comparison</span>
                  {slotB?.originalFilename && (
                    <span className="t-filename" title={slotB.originalFilename}>
                      {slotB.originalFilename}
                    </span>
                  )}
                </div>

                <div className="t-actions-group">
                  {imgB && onOpenModal && (
                    <button
                      type="button"
                      className="t-action-btn"
                      onClick={() => onOpenModal({ path: slotB.uploadedPath, label: `T2: ${slotB.originalFilename}` })}
                      title="Inspect T2 Fullscreen"
                    >
                      <span>🔍</span>
                    </button>
                  )}
                  {slotB?.uploadedPath && (
                    <button
                      type="button"
                      className="t-action-btn t-btn-remove"
                      onClick={onRemoveB}
                      disabled={disabled}
                      title="Remove T2 TIFF"
                    >
                      ✕ Remove
                    </button>
                  )}
                </div>
              </div>

              {/* Viewport or Dropzone T2 */}
              {!slotB?.uploadedPath ? (
                <label className="t-dropzone">
                  <input
                    ref={fileInputBRef}
                    type="file"
                    accept=".tif,.tiff"
                    onChange={(e) => {
                      if (e.target.files?.[0]) handleUpload(e.target.files[0], 'B');
                      e.target.value = '';
                    }}
                    disabled={disabled || slotB?.uploading}
                    hidden
                  />
                  <div className="t-dropzone-inner">
                    <span className="drop-plus">＋</span>
                    <span className="drop-title">
                      {slotB?.uploading ? 'Uploading T2…' : 'Drop T2 Comparison (.tif)'}
                    </span>
                    <span className="drop-hint">Browse GeoTIFF</span>
                  </div>
                </label>
              ) : (
                <div className="t-frame">
                  <img src={imgB} alt="T2 Comparison" className="t-img" />
                  {slotB.modelBbox && <div className="t-bbox-overlay" />}
                </div>
              )}

              {/* Compact Monospace Metadata */}
              {slotB?.uploadedPath && (boundsB || slotB?.info) && (
                <div className="t-meta-strip">
                  {boundsB && (
                    <div className="t-meta-row t-coords-row">
                      <span className="t-coord-badge">
                        <span className="c-tag">LAT</span> {formatLat(boundsB.min_lat)}–{formatLat(boundsB.max_lat)}
                      </span>
                      <span className="t-coord-badge">
                        <span className="c-tag">LON</span> {formatLon(boundsB.min_lon)}–{formatLon(boundsB.max_lon)}
                      </span>
                      {centerLatB != null && (
                        <span className="t-coord-badge c-center">
                          <span className="c-tag">CTR</span> {formatLat(centerLatB)}, {formatLon(centerLonB)}
                        </span>
                      )}
                    </div>
                  )}
                  <div className="t-meta-row t-specs-row">
                    {slotB.info?.width && (
                      <span className="t-spec-item">{slotB.info.width}×{slotB.info.height} px</span>
                    )}
                    {slotB.info?.bandCount && (
                      <span className="t-spec-item">{slotB.info.bandCount}B</span>
                    )}
                    <span className="t-spec-item">{slotB.info?.crs || 'EPSG:4326'}</span>
                    {approxAreaB && (
                      <span className="t-spec-item">{approxAreaB} km²</span>
                    )}
                    <span className="t-spec-item">{slotB.info?.georeferenced !== false ? '✓ Georef' : 'Unreferenced'}</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* =================================================================== */}
        {/* 2. SWIPE CURTAIN MODE                                               */}
        {/* =================================================================== */}
        {compareMode === 'swipe' && (
          <div className="compare-swipe-stage">
            {!bothLoaded ? (
              <div className="compare-awaiting-dual">
                <span className="await-icon">⇄</span>
                <p>Upload both T1 and T2 to activate interactive Swipe comparison.</p>
                <div className="await-actions">
                  <button type="button" className="btn-switch-sbs" onClick={() => setCompareMode('side-by-side')}>
                    Open Side-by-side to load rasters
                  </button>
                </div>
              </div>
            ) : (
              <div
                ref={containerRef}
                className="swipe-viewport-canvas"
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                onPointerCancel={handlePointerUp}
              >
                {/* Background Layer: T2 (Comparison) */}
                <div className="swipe-layer layer-t2">
                  <img src={imgB} alt="T2 Comparison" draggable={false} />
                  <span className="swipe-badge badge-t2">T2 Comparison</span>
                </div>

                {/* Foreground Layer (Clipped): T1 (Reference) */}
                <div
                  className="swipe-layer layer-t1"
                  style={{ clipPath: `inset(0 ${100 - sliderPos}% 0 0)` }}
                >
                  <img src={imgA} alt="T1 Reference" draggable={false} />
                  <span className="swipe-badge badge-t1">T1 Reference</span>
                </div>

                {/* Draggable Divider Line & Knob */}
                <div className="swipe-divider-handle" style={{ left: `${sliderPos}%` }}>
                  <div className="handle-line" />
                  <div className="handle-pill">
                    <span>⇄</span>
                  </div>
                </div>
              </div>
            )}
            {bothLoaded && (
              <div className="swipe-footer-stats">
                <div className="swipe-stats-top">
                  <span>Drag divider or click anywhere to inspect spatial changes</span>
                  <span className="split-percent">{Math.round(sliderPos)}% : {100 - Math.round(sliderPos)}%</span>
                </div>
                {(boundsA || boundsB) && (
                  <div className="swipe-coords-row">
                    <span className="sc-tag">SPATIAL EXTENTS:</span>
                    <span>
                      {boundsA ? `LAT: ${formatLat(boundsA.min_lat)}–${formatLat(boundsA.max_lat)}, LON: ${formatLon(boundsA.min_lon)}–${formatLon(boundsA.max_lon)}` : ''}
                      {boundsA && approxAreaA ? ` (${approxAreaA} km²)` : ''}
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* =================================================================== */}
        {/* 3. TOGGLE / AUTO-BLINK MODE                                         */}
        {/* =================================================================== */}
        {compareMode === 'toggle' && (
          <div className="compare-toggle-stage">
            {!bothLoaded ? (
              <div className="compare-awaiting-dual">
                <span className="await-icon">⇋</span>
                <p>Upload both T1 and T2 to activate instant toggle comparison.</p>
                <button type="button" className="btn-switch-sbs" onClick={() => setCompareMode('side-by-side')}>
                  Open Side-by-side to load rasters
                </button>
              </div>
            ) : (
              <div className="toggle-viewport-canvas">
                <div className="toggle-display-frame">
                  <img
                    src={activeToggle === 'T1' ? imgA : imgB}
                    alt={activeToggle === 'T1' ? 'T1 Reference' : 'T2 Comparison'}
                    className="toggle-active-img"
                  />
                  <div className="toggle-active-tag">
                    <span className={`active-t-badge ${activeToggle === 'T1' ? 't1' : 't2'}`}>
                      {activeToggle === 'T1' ? 'T1 REFERENCE' : 'T2 COMPARISON'}
                    </span>
                    <span className="active-t-name">
                      {activeToggle === 'T1' ? slotA?.originalFilename : slotB?.originalFilename}
                    </span>
                  </div>
                </div>

                {/* Active Toggle Coordinates Strip */}
                {((activeToggle === 'T1' && (boundsA || slotA?.info)) || (activeToggle === 'T2' && (boundsB || slotB?.info))) && (
                  <div className="toggle-extents-bar">
                    <span className="toggle-extents-label">
                      {activeToggle === 'T1' ? 'T1 SCENE:' : 'T2 SCENE:'}
                    </span>
                    <span className="toggle-extents-val">
                      {activeToggle === 'T1' && boundsA
                        ? `LAT: ${formatLat(boundsA.min_lat)}–${formatLat(boundsA.max_lat)}, LON: ${formatLon(boundsA.min_lon)}–${formatLon(boundsA.max_lon)} | DIM: ${slotA?.info?.width}×${slotA?.info?.height} px`
                        : activeToggle === 'T2' && boundsB
                          ? `LAT: ${formatLat(boundsB.min_lat)}–${formatLat(boundsB.max_lat)}, LON: ${formatLon(boundsB.min_lon)}–${formatLon(boundsB.max_lon)} | DIM: ${slotB?.info?.width}×${slotB?.info?.height} px`
                          : ''}
                    </span>
                  </div>
                )}

                <div className="toggle-control-strip">
                  <div className="toggle-switch-group">
                    <button
                      type="button"
                      className={`btn-toggle-t ${activeToggle === 'T1' ? 'active-t1' : ''}`}
                      onClick={() => setActiveToggle('T1')}
                    >
                      Show T1 (Reference)
                    </button>
                    <button
                      type="button"
                      className={`btn-toggle-t ${activeToggle === 'T2' ? 'active-t2' : ''}`}
                      onClick={() => setActiveToggle('T2')}
                    >
                      Show T2 (Comparison)
                    </button>
                  </div>

                  <button
                    type="button"
                    className={`btn-auto-blink ${isAutoBlinking ? 'blinking' : ''}`}
                    onClick={() => setIsAutoBlinking((prev) => !prev)}
                    title="Toggle automatic 1Hz flicker comparison"
                  >
                    {isAutoBlinking ? '⏸ Pause Auto-Blink' : '▶ Auto-Blink (1s)'}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
