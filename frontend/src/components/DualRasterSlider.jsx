import React, { useRef, useState } from 'react';
import { rasterPreviewUrl } from '../api/rasters';

export default function DualRasterSlider({ slotA, slotB }) {
  const [sliderPos, setSliderPos] = useState(50); // percentage (0 to 100)
  const [viewMode, setViewMode] = useState('swipe'); // 'swipe' | 'side-by-side'
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef(null);

  const imgA = slotA?.uploadedPath ? rasterPreviewUrl(slotA.uploadedPath, 800) : null;
  const imgB = slotB?.uploadedPath ? rasterPreviewUrl(slotB.uploadedPath, 800) : null;

  const handlePointerDown = (e) => {
    if (viewMode !== 'swipe') return;
    setIsDragging(true);
    e.currentTarget.setPointerCapture?.(e.pointerId);
    updateSlider(e);
  };

  const handlePointerMove = (e) => {
    if (!isDragging || viewMode !== 'swipe') return;
    updateSlider(e);
  };

  const handlePointerUp = () => {
    setIsDragging(false);
  };

  const updateSlider = (e) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
    const percent = (x / rect.width) * 100;
    setSliderPos(percent);
  };

  if (!imgA && !imgB) {
    return (
      <div className="dual-slider-empty">
        <div className="slider-empty-icon">⇄</div>
        <h4>Temporal Raster Comparison</h4>
        <p>Load both Image A (Reference / $T_1$) and Image B (Comparison / $T_2$) to unlock the interactive swipe comparator.</p>
      </div>
    );
  }

  return (
    <div className="dual-slider-wrapper">
      <div className="dual-slider-header">
        <div className="slider-title-group">
          <h4>Temporal Comparison Analyzer</h4>
          <span className="slider-mode-badge">{viewMode === 'swipe' ? 'Interactive Swipe Curtain' : 'Side-by-Side'}</span>
        </div>
        <div className="slider-controls">
          <button
            type="button"
            className={`btn-toggle-sub ${viewMode === 'swipe' ? 'active' : ''}`}
            onClick={() => setViewMode('swipe')}
          >
            Curtain Swipe
          </button>
          <button
            type="button"
            className={`btn-toggle-sub ${viewMode === 'side-by-side' ? 'active' : ''}`}
            onClick={() => setViewMode('side-by-side')}
          >
            Side by Side
          </button>
        </div>
      </div>

      {viewMode === 'swipe' ? (
        <div
          ref={containerRef}
          className="dual-slider-stage"
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
        >
          {/* Background image: Image B (After / T2) */}
          <div className="slider-layer layer-after">
            {imgB ? (
              <img src={imgB} alt="Raster B (After)" draggable={false} />
            ) : (
              <div className="layer-placeholder">Awaiting Image B</div>
            )}
            <span className="layer-label label-right">T2 (After / Compare)</span>
          </div>

          {/* Clipped foreground image: Image A (Before / T1) */}
          <div
            className="slider-layer layer-before"
            style={{ clipPath: `inset(0 ${100 - sliderPos}% 0 0)` }}
          >
            {imgA ? (
              <img src={imgA} alt="Raster A (Before)" draggable={false} />
            ) : (
              <div className="layer-placeholder">Awaiting Image A</div>
            )}
            <span className="layer-label label-left">T1 (Before / Reference)</span>
          </div>

          {/* Draggable Divider Handle */}
          <div className="slider-divider" style={{ left: `${sliderPos}%` }}>
            <div className="divider-line" />
            <div className="divider-knob">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M18 8L22 12L18 16" />
                <path d="M6 8L2 12L6 16" />
              </svg>
            </div>
          </div>
        </div>
      ) : (
        <div className="dual-side-by-side">
          <div className="side-pane">
            <span className="pane-label">T1 Reference (Image A)</span>
            {imgA ? (
              <img src={imgA} alt="Raster A" />
            ) : (
              <div className="pane-empty">Empty Image A</div>
            )}
            <span className="filename-sub">{slotA?.originalFilename || 'No file selected'}</span>
          </div>
          <div className="side-pane">
            <span className="pane-label">T2 Comparison (Image B)</span>
            {imgB ? (
              <img src={imgB} alt="Raster B" />
            ) : (
              <div className="pane-empty">Empty Image B</div>
            )}
            <span className="filename-sub">{slotB?.originalFilename || 'No file selected'}</span>
          </div>
        </div>
      )}

      <div className="slider-footer-stats">
        <span>Drag the slider or click anywhere on the canvas to inspect surface changes.</span>
        <span>Position: {Math.round(sliderPos)}%</span>
      </div>
    </div>
  );
}
