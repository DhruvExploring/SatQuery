import React from 'react';

export default function Navbar({ currentView, onSelectView, healthStatus, healthLatency }) {
  return (
    <header className="navbar">
      <div className="brand-container" onClick={() => onSelectView('analyze')}>
        <div className="brand-icon">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"></circle>
            <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"></path>
            <path d="M2 12h20"></path>
          </svg>
        </div>
        <span className="brand-title">SatQuery AI</span>
      </div>

      <ul className="nav-links">
        <li className="nav-item">
          <button
            className={`nav-link ${currentView === 'analyze' ? 'active' : ''}`}
            onClick={() => onSelectView('analyze')}
            id="nav-analyze"
          >
            Analyze
          </button>
        </li>
        <li className="nav-item">
          <button
            className={`nav-link ${currentView === 'results' ? 'active' : ''}`}
            onClick={() => onSelectView('results')}
            id="nav-results"
          >
            Results
          </button>
        </li>
        <li className="nav-item">
          <button
            className={`nav-link ${currentView === 'trace' ? 'active' : ''}`}
            onClick={() => onSelectView('trace')}
            id="nav-trace"
          >
            Execution Trace
          </button>
        </li>
        <li className="nav-item">
          <button
            className={`nav-link ${currentView === 'models' ? 'active' : ''}`}
            onClick={() => onSelectView('models')}
            id="nav-models"
          >
            Models
          </button>
        </li>
        <li className="nav-item">
          <button
            className={`nav-link ${currentView === 'about' ? 'active' : ''}`}
            onClick={() => onSelectView('about')}
            id="nav-about"
          >
            About
          </button>
        </li>
      </ul>

      <div className="nav-actions">
        <div className="status-pill" id="health-indicator">
          <span className="status-dot"></span>
          <span>{healthStatus ? `LIVE (${healthLatency || 24}ms)` : 'CONNECTING...'}</span>
        </div>
      </div>
    </header>
  );
}
