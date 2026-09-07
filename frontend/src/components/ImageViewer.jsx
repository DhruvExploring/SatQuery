import React, { useState, useRef, useEffect } from 'react';
import { LAYERS } from '../state/scenarios';

export default function ImageViewer({
  activeLayer = 'main',
  viewMode = 'result',
  onToggleMode = null,
  scenario,
  showOverlay = true,
  children = null
}) {
  const [zoom, setZoom] = useState(1.0);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const containerRef = useRef(null);

  // Determine current image source
  const currentLayerObj = LAYERS.find(l => l.id === activeLayer) || LAYERS[0];
  const imgSrc = (viewMode === 'raw' ? '/assets/satellite_rgb.jpg' : currentLayerObj.image);

  // Zoom controls
  const handleZoomIn = () => setZoom(prev => Math.min(prev + 0.25, 3.5));
  const handleZoomOut = () => setZoom(prev => Math.max(prev - 0.25, 0.5));
  const handleResetZoom = () => {
    setZoom(1.0);
    setPan({ x: 0, y: 0 });
  };

  // Mouse drag handlers
  const handleMouseDown = (e) => {
    if (e.button !== 0) return; // Primary click only
    setIsDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  };

  const handleMouseMove = (e) => {
    if (!isDragging) return;
    setPan({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y
    });
  };

  const handleMouseUp = () => setIsDragging(false);

  // Wheel zoom
  const handleWheel = (e) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.15 : 0.15;
    setZoom(prev => Math.min(Math.max(prev + delta, 0.5), 3.5));
  };

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.addEventListener('wheel', handleWheel, { passive: false });
    return () => el.removeEventListener('wheel', handleWheel);
  }, []);

  const boxStyle = scenario?.boxStyle || {
    top: '22%',
    left: '24%',
    width: '42%',
    height: '54%',
    borderColor: '#22c55e'
  };
  const boxLabel = scenario?.boxLabel || 'Agricultural Land (65%)';

  return (
    <div className="card viewer-card">
      <div className="viewer-topbar">
        <div className="viewer-file-info">
          <span className="badge badge-format">{scenario?.format || 'PNG'}</span>
          <span id="canvas-filename">{scenario?.filename || 'satellite_image.png'}</span>
          <span className="badge badge-tag">{scenario?.taskBadge || 'Optical'}</span>
        </div>

        {onToggleMode && (
          <div className="mode-toggle-group">
            <button
              type="button"
              className={`mode-btn ${viewMode === 'result' ? 'active' : ''}`}
              onClick={() => onToggleMode('result')}
              id="btn-mode-result"
            >
              Result View
            </button>
            <button
              type="button"
              className={`mode-btn ${viewMode === 'raw' ? 'active' : ''}`}
              onClick={() => onToggleMode('raw')}
              id="btn-mode-raw"
            >
              Raw Image
            </button>
          </div>
        )}

        <div className="viewer-file-stats">
          <span>1024 × 768</span>
          <span>10m / px</span>
        </div>
      </div>

      <div
        className="viewport-container"
        ref={containerRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
      >
        <img
          src={imgSrc}
          alt="Satellite Surface"
          className="viewer-image"
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
            transformOrigin: 'center center',
            transition: isDragging ? 'none' : 'transform 0.15s ease-out'
          }}
          draggable="false"
        />

        {showOverlay && viewMode === 'result' && (
          <div
            className="detection-overlay"
            style={{
              top: boxStyle.top,
              left: boxStyle.left,
              width: boxStyle.width,
              height: boxStyle.height,
              borderColor: boxStyle.borderColor,
              background: `${boxStyle.borderColor}14`
            }}
          >
            <span
              className="detection-label"
              style={{ background: boxStyle.borderColor }}
            >
              {boxLabel}
            </span>
          </div>
        )}

        {/* Controls toolbar */}
        <div className="viewer-controls-bar">
          <button className="control-btn" title="Zoom In" onClick={handleZoomIn} id="btn-zoom-in">+</button>
          <button className="control-btn" title="Zoom Out" onClick={handleZoomOut} id="btn-zoom-out">-</button>
          <button className="control-btn" title="Fit to View" onClick={handleResetZoom} id="btn-fit-view">⛶</button>
        </div>

        {/* Inset Minimap */}
        <div className="minimap-container" title="Overview Context">
          <img src="/assets/minimap.jpg" alt="Minimap" className="minimap-img" />
          <div className="minimap-rect"></div>
        </div>

        {/* Floating Compass */}
        <div className="compass-badge" title="Orientation: North Up">
          <span>▲</span>
          <span>N</span>
        </div>

        {/* Viewport Info Tag */}
        <div className="viewport-info-tag">
          {scenario?.coords || '28.6139° N, 77.2090° E'}
        </div>
      </div>

      {children}
    </div>
  );
}
