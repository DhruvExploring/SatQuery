import React, { useState } from 'react';
import { describeStep } from '../lib/executionSteps';

export default function LogsDrawer({ isOpen, onClose, executionTrace, errors, rawToolResults, backendUp, isRunning }) {
  const [tab, setTab] = useState('trace'); // 'trace' | 'errors' | 'raw'

  if (!isOpen) return null;

  const errorCount = (errors?.length || 0) + (backendUp === false ? 1 : 0);

  return (
    <div className="logs-drawer-backdrop" onClick={onClose}>
      <aside className="logs-drawer-panel" onClick={(e) => e.stopPropagation()}>
        <div className="logs-drawer-header">
          <div className="logs-header-title">
            <span className="logs-icon">⚙️</span>
            <div>
              <h3>System Logs & Telemetry</h3>
              <p>Real-time execution trace, network diagnostics, and tool outputs</p>
            </div>
          </div>
          <button type="button" className="btn-close-drawer" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="logs-tabs-nav">
          <button
            type="button"
            className={`logs-tab-btn ${tab === 'trace' ? 'active' : ''}`}
            onClick={() => setTab('trace')}
          >
            <span>Trace Steps ({executionTrace?.length || 0})</span>
            {isRunning && <span className="mini-pulse" />}
          </button>
          <button
            type="button"
            className={`logs-tab-btn ${tab === 'errors' ? 'active' : ''}`}
            onClick={() => setTab('errors')}
          >
            <span>Errors & Diagnostics</span>
            {errorCount > 0 && <span className="error-count-pill">{errorCount}</span>}
          </button>
          <button
            type="button"
            className={`logs-tab-btn ${tab === 'raw' ? 'active' : ''}`}
            onClick={() => setTab('raw')}
          >
            <span>Tool Telemetry (JSON)</span>
          </button>
        </div>

        <div className="logs-drawer-body">
          {tab === 'trace' && (
            <div className="trace-log-view">
              {executionTrace && executionTrace.length > 0 ? (
                <div className="trace-list">
                  {executionTrace.map((row, i) => {
                    const step = describeStep(row);
                    return (
                      <div key={i} className={`trace-item ${step.ok === false ? 'item-err' : 'item-ok'}`}>
                        <div className="trace-node-badge">
                          <span className="node-idx">#{i + 1}</span>
                          <strong>{step.label}</strong>
                        </div>
                        {row.summary && <p className="trace-summary">{row.summary}</p>}
                        {row.timestamp && <span className="trace-time">{row.timestamp}</span>}
                      </div>
                    );
                  })}
                </div>
              ) : isRunning ? (
                <div className="logs-empty">
                  <span className="radar-spinner" />
                  <p>Orchestrator graph is actively executing tools…</p>
                </div>
              ) : (
                <div className="logs-empty">
                  <p>No query steps executed yet. Run a query in Studio to see graph logs.</p>
                </div>
              )}
            </div>
          )}

          {tab === 'errors' && (
            <div className="errors-log-view">
              {backendUp === false && (
                <div className="error-card critical">
                  <div className="error-head">
                    <span className="error-type">API_CONNECTION_ERROR</span>
                    <span className="error-badge">Offline</span>
                  </div>
                  <p className="error-desc">
                    Could not reach the SatQuery FastAPI backend on localhost:8000 or the configured API URL.
                  </p>
                  <p className="error-advice">Ensure <code>python -m backend.main</code> is running if testing with live models.</p>
                </div>
              )}

              {errors && errors.length > 0 ? (
                errors.map((err, i) => (
                  <div key={i} className="error-card">
                    <div className="error-head">
                      <span className="error-type">SYSTEM_ERROR</span>
                    </div>
                    <pre className="error-desc">{typeof err === 'object' ? JSON.stringify(err, null, 2) : String(err)}</pre>
                  </div>
                ))
              ) : backendUp !== false ? (
                <div className="logs-empty clean">
                  <span className="clean-check">✓</span>
                  <p>All clean. Zero exceptions or validation errors logged.</p>
                </div>
              ) : null}
            </div>
          )}

          {tab === 'raw' && (
            <div className="raw-log-view">
              {rawToolResults && rawToolResults.length > 0 ? (
                <pre className="json-code-block">{JSON.stringify(rawToolResults, null, 2)}</pre>
              ) : (
                <div className="logs-empty">
                  <p>No tool telemetry results in current turn.</p>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="logs-drawer-footer">
          <span className="footer-status-txt">
            Backend: {backendUp ? 'Online (HTTP 200)' : backendUp === false ? 'Offline' : 'Connecting'}
          </span>
          <button type="button" className="btn-glass btn-sm" onClick={onClose}>
            Close Drawer
          </button>
        </div>
      </aside>
    </div>
  );
}
