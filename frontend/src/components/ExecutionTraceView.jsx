import React from 'react';

export default function ExecutionTraceView({ traceSteps, telemetry, onOpenReport }) {
  const defaultSteps = [
    {
      step: 1,
      title: 'Query Ingestion & Validation',
      desc: 'Validated bounding box coordinates, parameters, and CRS against EPSG:4326 schema.',
      time: '0.04s'
    },
    {
      step: 2,
      title: 'LangGraph Agent Planner',
      desc: 'Confidence-weighted router selected analytical spectral tool pipeline.',
      time: '0.38s'
    },
    {
      step: 3,
      title: 'Tool Execution & Sensor Head',
      desc: 'Processed GeoTIFF rasters, computed multi-spectral indices, and extracted feature masks.',
      time: '1.82s'
    },
    {
      step: 4,
      title: 'Spatial Verification & Synthesis',
      desc: 'Assembled natural language response, verified bounding boxes, and grounded telemetry.',
      time: '0.12s'
    }
  ];

  const displaySteps = traceSteps && traceSteps.length > 0 ? traceSteps : defaultSteps;

  return (
    <div className="view-page active" id="view-trace">
      <div className="page-header">
        <div className="page-title-group">
          <div className="page-icon-badge">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
            </svg>
          </div>
          <div>
            <h1 className="page-title">Execution <span>Trace</span></h1>
            <p className="page-subtitle">LangGraph finite-state transitions & telemetry diagnostics</p>
          </div>
        </div>
      </div>

      <div className="dashboard-grid-trace">
        {/* Column 1: Session Overview */}
        <div className="card session-summary-card">
          <div className="session-thumb-row">
            <img src="/assets/satellite_rgb.jpg" alt="Session Thumbnail" className="session-thumb" />
            <div>
              <div className="session-id-title">#SAT-20250824-001</div>
              <div className="session-time">10m Ground Sample</div>
            </div>
          </div>

          <div className="earth-visual-card">
            <img src="/assets/earth_card.jpg" alt="Earth" className="earth-bg-img" />
            <span className="earth-caption">EarthMind-4B Multi-Head</span>
          </div>

          <table className="config-table">
            <tbody>
              <tr><td>CRS Projection</td><td>EPSG:4326 (WGS84)</td></tr>
              <tr><td>Orchestrator</td><td>LangGraph FSM</td></tr>
              <tr><td>API Backend</td><td>FastAPI Port 8000</td></tr>
              <tr><td>Graph Status</td><td>COMPLETED</td></tr>
            </tbody>
          </table>
        </div>

        {/* Column 2: Telemetry Metrics & Vertical Timeline */}
        <div className="card trace-timeline-card">
          <div className="timeline-header">
            <span className="badge badge-format">LANGGRAPH PIPELINE</span>
            <h3 style={{ color: '#fff', fontSize: '1.15rem' }}>Agentic Execution Timeline</h3>
          </div>

          <div className="metrics-grid-4">
            <div className="metric-card">
              <div className="metric-header"><span>PIPELINE TIME</span></div>
              <div className="metric-number" id="trace-total-time">{telemetry?.totalTime || '2.36s'}</div>
              <span className="badge badge-success">Optimal</span>
            </div>
            <div className="metric-card">
              <div className="metric-header"><span>GRAPH STATUS</span></div>
              <div className="metric-number" style={{ color: '#10b981' }}>PASS</div>
              <span className="badge badge-success">Completed</span>
            </div>
            <div className="metric-card">
              <div className="metric-header"><span>MEMORY PEAK</span></div>
              <div className="metric-number">4.2 GB</div>
              <span className="badge badge-tag">VRAM</span>
            </div>
            <div className="metric-card">
              <div className="metric-header"><span>TOOLS ACTIVE</span></div>
              <div className="metric-number" style={{ color: '#38bdf8' }}>8 Tools</div>
              <span className="badge badge-format">Ready</span>
            </div>
          </div>

          <div className="timeline-flow" id="trace-timeline-container">
            {displaySteps.map((step, idx) => (
              <div key={idx} className="timeline-step">
                <div className="step-node-badge">{step.step || idx + 1}</div>
                <div className="step-content-card">
                  <div className="step-main">
                    <span className="step-title">{step.title}</span>
                    <span className="step-desc">{step.desc}</span>
                  </div>
                  <span className="step-timestamp">{step.time}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Column 3: Geospatial Audit Checklist */}
        <div className="card session-summary-card">
          <div className="timeline-header">
            <span className="badge badge-success">AUDIT PASS</span>
            <h4 style={{ color: '#fff' }}>Geospatial Checklist</h4>
          </div>

          <ul className="highlights-list">
            <li className="highlight-item">
              <span className="highlight-check">✓</span>
              <span>CRS bounds strictly validated against WGS84 range.</span>
            </li>
            <li className="highlight-item">
              <span className="highlight-check">✓</span>
              <span>Affine transform and GeoTIFF georeference preserved without drift.</span>
            </li>
            <li className="highlight-item">
              <span className="highlight-check">✓</span>
              <span>Spectral index values clamped to physical range [-1, 1].</span>
            </li>
            <li className="highlight-item">
              <span className="highlight-check">✓</span>
              <span>Intermediate raster paths passed into state['input_file'].</span>
            </li>
          </ul>

          <div style={{ marginTop: '1.25rem' }}>
            <button
              type="button"
              className="btn-secondary primary-shade"
              id="btn-export-trace-json"
              style={{ width: '100%' }}
              onClick={onOpenReport}
            >
              📄 Export Audit Report
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
