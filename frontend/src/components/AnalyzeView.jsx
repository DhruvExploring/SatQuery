import React from 'react';
import ImageViewer from './ImageViewer';

export default function AnalyzeView({
  scenario,
  onSelectScenario,
  queryText,
  setQueryText,
  onRunAnalysis,
  isRunning,
  selectedModel,
  setSelectedModel,
  selectedSensor,
  setSelectedSensor
}) {
  const handleKeyDown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      onRunAnalysis();
    }
  };

  return (
    <div className="view-page active" id="view-analyze">
      <div className="page-header">
        <div className="page-title-group">
          <div className="page-icon-badge">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="2" y1="12" x2="22" y2="12"></line>
              <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
            </svg>
          </div>
          <div>
            <h1 className="page-title">Satellite <span>Earth Analysis</span></h1>
            <p className="page-subtitle">Interactive multispectral query & autonomous intelligence generation</p>
          </div>
        </div>
      </div>

      <div className="dashboard-grid-analyze">
        {/* Left: Viewer Card + Metadata Panel */}
        <ImageViewer scenario={scenario} showOverlay={true}>
          <div className="metadata-panel">
            <div className="panel-header">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="16" x2="12" y2="12"></line>
                <line x1="12" y1="8" x2="12.01" y2="8"></line>
              </svg>
              <span>Image Metadata & Telemetry</span>
            </div>
            <div className="metadata-grid">
              <div className="meta-item">
                <span className="meta-label">BBOX (EPSG:4326)</span>
                <span className="meta-value" id="canvas-bbox">[{scenario.bbox.join(', ')}]</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">GROUND RESOLUTION</span>
                <span className="meta-value">10.0m / pixel</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">SENSOR PLATFORM</span>
                <span className="meta-value">{selectedSensor}</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">CLOUD COVERAGE</span>
                <span className="meta-value">0.02% (Optimal Clear)</span>
              </div>
            </div>
          </div>
        </ImageViewer>

        {/* Right: Query Console Card */}
        <div className="card query-panel">
          <div className="tab-nav">
            <button className="tab-btn active">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
                <polyline points="2 17 12 22 22 17"></polyline>
                <polyline points="2 12 12 17 22 12"></polyline>
              </svg>
              Query Console
            </button>
          </div>

          <div className="tab-content-container">
            {/* Natural Language Prompt */}
            <div className="prompt-box-card">
              <div className="prompt-header">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="11" cy="11" r="8"></circle>
                  <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                </svg>
                <span>NATURAL LANGUAGE QUERY</span>
              </div>
              <textarea
                id="query-input"
                className="prompt-textarea"
                rows="3"
                placeholder="Ask a question about the satellite imagery (e.g. land cover, crop health, flood extent)..."
                value={queryText}
                onChange={(e) => setQueryText(e.target.value)}
                onKeyDown={handleKeyDown}
              />
              <div className="prompt-footer">
                <span className="char-counter" id="query-char-count">
                  {queryText.length} / 500 characters
                </span>
                <button
                  type="button"
                  className="btn-send"
                  onClick={onRunAnalysis}
                  title="Run Analysis"
                  disabled={isRunning || !queryText.trim()}
                >
                  {isRunning ? '⏳' : '➤'}
                </button>
              </div>
            </div>

            {/* Scenario Presets Chips */}
            <div className="example-queries-section">
              <div className="section-label">
                <span>MISSION PRESETS</span>
              </div>
              <div className="example-chips-wrap">
                <button
                  type="button"
                  className={`example-chip ${scenario.id === 'agriculture' ? 'active' : ''}`}
                  onClick={() => onSelectScenario('agriculture')}
                  id="btn-scenario-agri"
                >
                  🌾 Delhi Agriculture
                </button>
                <button
                  type="button"
                  className={`example-chip ${scenario.id === 'flood' ? 'active' : ''}`}
                  onClick={() => onSelectScenario('flood')}
                  id="btn-scenario-flood"
                >
                  🌊 Mumbai Flood (SAR)
                </button>
                <button
                  type="button"
                  className={`example-chip ${scenario.id === 'deforestation' ? 'active' : ''}`}
                  onClick={() => onSelectScenario('deforestation')}
                  id="btn-scenario-deforest"
                >
                  🌲 Amazon Deforestation
                </button>
              </div>
            </div>

            {/* Detected Intent Card */}
            <div className="intent-card" id="query-intent-tag">
              <div className="intent-icon">✓</div>
              <div>
                <div className="intent-title">INTENT: {scenario.taskBadge}</div>
                <div className="intent-desc">{scenario.task} using {scenario.model}</div>
              </div>
            </div>

            {/* Model Selector */}
            <div className="model-select-group">
              <div className="section-label">AI INFERENCE MODEL</div>
              <select
                id="model-select"
                className="model-select-card"
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                style={{ width: '100%', color: '#f8fafc', background: '#0a1120' }}
              >
                <option value="SatQuery-Vision v2.4">SatQuery-Vision v2.4 (Multimodal Sentinel)</option>
                <option value="FastGeo-7B">FastGeo-7B (High-Speed VQA)</option>
                <option value="LandCoverNet-v1">LandCoverNet-v1 (12-Class Semantic)</option>
                <option value="ChangeDetect-XL">ChangeDetect-XL (Bi-Temporal Diff)</option>
              </select>
            </div>

            {/* Primary Action Button */}
            <button
              type="button"
              className="btn-primary-action"
              id="btn-run-analysis"
              onClick={onRunAnalysis}
              disabled={isRunning || !queryText.trim()}
            >
              {isRunning ? 'Processing LangGraph Pipeline...' : 'Run Analysis ➔'}
            </button>
          </div>

          {/* Suggested Inquiries */}
          <div className="recent-queries-panel">
            <div className="recent-header">
              <div className="recent-title">
                <span>Suggested Inquiries</span>
              </div>
            </div>
            <ul className="recent-list">
              <li
                className="recent-item"
                onClick={() => setQueryText('What land cover is visible in this area? Estimate percentages.')}
              >
                <span className="recent-item-query">"What land cover is visible in this area?"</span>
                <span className="recent-item-meta">VQA</span>
              </li>
              <li
                className="recent-item"
                onClick={() => setQueryText('Compute NDVI and assess crop canopy health across cultivated fields.')}
              >
                <span className="recent-item-query">"Compute NDVI and assess crop health"</span>
                <span className="recent-item-meta">Spectral</span>
              </li>
              <li
                className="recent-item"
                onClick={() => setQueryText('Detect standing flood water using Sentinel-1 SAR dual-polarization backscatter.')}
              >
                <span className="recent-item-query">"Detect standing flood water using SAR"</span>
                <span className="recent-item-meta">Radar</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
