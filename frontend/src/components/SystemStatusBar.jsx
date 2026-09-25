import React from 'react';

export default function SystemStatusBar({ activeTab, onTabChange, backendUp, modelsStatus, onResetSession, hasMessages }) {
  const orchestrator = modelsStatus?.orchestrator;
  const vision = modelsStatus?.vision_tool;

  return (
    <header className="app-header-bar">
      <div className="header-left">
        <div className="brand-wrap">
          <div className="satellite-radar-icon">
            <span className="radar-sweep" />
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3" />
              <path d="M4.93 4.93a10 10 0 0 1 14.14 0" />
              <path d="M7.76 7.76a6 6 0 0 1 8.48 0" />
              <circle cx="12" cy="12" r="9" strokeDasharray="3 3" opacity="0.4" />
            </svg>
          </div>
          <div>
            <div className="brand-title">
              <h1>SatQuery</h1>
              <span className="version-pill">EO INTEL v1.0</span>
            </div>
            <p className="brand-subtitle">Autonomous Earth Observation & Spatial Intelligence Suite</p>
          </div>
        </div>
      </div>

      <nav className="header-nav" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'studio'}
          className={`nav-tab ${activeTab === 'studio' ? 'active' : ''}`}
          onClick={() => onTabChange('studio')}
        >
          <span className="tab-icon">🛰️</span>
          <span>Studio</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'map'}
          className={`nav-tab ${activeTab === 'map' ? 'active' : ''}`}
          onClick={() => onTabChange('map')}
        >
          <span className="tab-icon">🗺️</span>
          <span>AOI Map</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'workflows'}
          className={`nav-tab ${activeTab === 'workflows' ? 'active' : ''}`}
          onClick={() => onTabChange('workflows')}
        >
          <span className="tab-icon">⚡</span>
          <span>Workflows</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'spectral'}
          className={`nav-tab ${activeTab === 'spectral' ? 'active' : ''}`}
          onClick={() => onTabChange('spectral')}
        >
          <span className="tab-icon">🔬</span>
          <span>Spectral Lab</span>
        </button>
      </nav>

      <div className="header-right">
        <div className="telemetry-badges">
          <div className={`status-pill ${backendUp ? 'online' : backendUp === false ? 'offline' : 'connecting'}`}>
            <span className="status-dot" />
            <span>{backendUp ? 'API Online' : backendUp === false ? 'Backend Offline' : 'Connecting...'}</span>
          </div>

          {orchestrator && (
            <div className="model-chip" title={`LLM Provider: ${orchestrator.provider} (${orchestrator.model || 'Default'})`}>
              <span className="chip-key">LLM:</span>
              <span className="chip-val">{orchestrator.provider}</span>
            </div>
          )}

          {vision?.enabled && (
            <div className="model-chip" title={`Vision Tool: ${vision.provider} (${vision.model || 'active'})`}>
              <span className="chip-key">VLM:</span>
              <span className="chip-val">{vision.provider}</span>
            </div>
          )}
        </div>

        {hasMessages && (
          <button
            type="button"
            className="btn-glass btn-reset-icon"
            onClick={onResetSession}
            title="Clear current conversation"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            </svg>
            <span>Reset</span>
          </button>
        )}
      </div>
    </header>
  );
}
