import React from 'react';
import ImageViewer from './ImageViewer';
import { LAYERS } from '../state/scenarios';

export default function ResultsView({
  scenario,
  activeLayer,
  setActiveLayer,
  viewMode,
  setViewMode,
  queryText,
  backendResponse,
  onNewAnalysis,
  onViewTrace,
  onOpenReport
}) {
  const narrative = backendResponse?.narrative || scenario.narrative;
  const confidence = backendResponse?.confidence || scenario.confidence;
  const taskBadge = backendResponse?.taskBadge || scenario.taskBadge;
  const classes = scenario.classes || [];

  return (
    <div className="view-page active" id="view-results">
      <div className="page-header">
        <div className="page-title-group">
          <div className="page-icon-badge">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
              <line x1="3" y1="9" x2="21" y2="9"></line>
              <line x1="9" y1="21" x2="9" y2="9"></line>
            </svg>
          </div>
          <div>
            <span className="back-link" onClick={onNewAnalysis} id="btn-new-analysis">
              ← Back to Mission Query
            </span>
            <h1 className="page-title">Analysis <span>Results</span></h1>
          </div>
        </div>

        <div className="header-meta-bar">
          <div className="meta-chip">
            <div className="meta-chip-icon">🛰</div>
            <div className="meta-chip-content">
              <span className="meta-chip-label">MODEL</span>
              <span className="meta-chip-val" id="res-model">{scenario.model}</span>
            </div>
          </div>
          <div className="meta-chip">
            <div className="meta-chip-icon">🎯</div>
            <div className="meta-chip-content">
              <span className="meta-chip-label">TASK</span>
              <span className="meta-chip-val">{taskBadge}</span>
            </div>
          </div>
          <div className="meta-chip">
            <div className="meta-chip-icon">🆔</div>
            <div className="meta-chip-content">
              <span className="meta-chip-label">SESSION</span>
              <span className="meta-chip-val" id="res-session-id">#SAT-20250824-001</span>
            </div>
          </div>
        </div>
      </div>

      <div className="dashboard-grid-results">
        {/* Left: Viewer with View Mode Toggle and Layer Carousel */}
        <ImageViewer
          scenario={scenario}
          activeLayer={activeLayer}
          viewMode={viewMode}
          onToggleMode={setViewMode}
          showOverlay={true}
        >
          <div className="layer-carousel-container">
            {LAYERS.map((layer) => (
              <div
                key={layer.id}
                className={`layer-thumbnail-card ${activeLayer === layer.id ? 'active' : ''}`}
                onClick={() => setActiveLayer(layer.id)}
                id={`layer-card-${layer.id}`}
              >
                <img src={layer.thumb} alt={layer.name} className="layer-thumb-preview" />
                <span className="layer-thumb-title">{layer.name}</span>
              </div>
            ))}
          </div>
        </ImageViewer>

        {/* Right: AI Response & Spatial Reasoning Card */}
        <div className="card ai-response-card">
          <div className="ai-response-header">
            <div className="ai-title-group">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" strokeWidth="2">
                <circle cx="12" cy="12" r="10"></circle>
                <path d="M12 16v-4"></path>
                <path d="M12 8h.01"></path>
              </svg>
              <span>AI Spatial Synthesis</span>
            </div>
            <div className="ai-badges">
              <span className="badge badge-success" id="res-confidence">
                {confidence}
              </span>
              <span className="badge badge-format" id="res-task-badge">
                {taskBadge}
              </span>
            </div>
          </div>

          <div className="ai-narrative-text" id="res-narrative">
            {narrative}
          </div>

          <div className="detected-classes-section">
            <div className="detected-classes-title">
              <span>DETECTED LAND COVER & SPATIAL CLASSES</span>
            </div>
            <div className="classes-pills-wrap" id="res-classes-container">
              {classes.map((cls, idx) => (
                <span key={idx} className={`class-pill ${cls.className}`}>
                  ● {cls.name}
                </span>
              ))}
            </div>
          </div>

          <div className="action-buttons-group">
            <button
              type="button"
              className="btn-secondary"
              id="btn-download-geotiff"
              onClick={() => alert('Downloading calibrated GeoTIFF raster stream...')}
            >
              ⬇ GeoTIFF
            </button>
            <button
              type="button"
              className="btn-secondary primary-shade"
              id="btn-generate-report"
              onClick={onOpenReport}
            >
              📄 Audit Report
            </button>
            <button
              type="button"
              className="btn-secondary"
              id="btn-view-trace-direct"
              onClick={onViewTrace}
            >
              ⚡ View Trace
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
