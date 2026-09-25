import React, { useEffect, useState } from 'react';
import { describeStep } from '../lib/executionSteps';

export default function LogsDrawer({ isOpen, onClose, executionTrace, errors, rawToolResults, backendUp, isRunning }) {
  const [tab, setTab] = useState('trace'); // 'trace' | 'errors' | 'raw'
  const [copiedRaw, setCopiedRaw] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const errorCount = (errors?.length || 0) + (backendUp === false ? 1 : 0);

  const handleCopyRaw = () => {
    if (!rawToolResults) return;
    navigator.clipboard?.writeText(JSON.stringify(rawToolResults, null, 2));
    setCopiedRaw(true);
    setTimeout(() => setCopiedRaw(false), 2000);
  };

  return (
    <div className="logs-drawer-backdrop" onClick={onClose}>
      <aside className="logs-drawer-panel" onClick={(e) => e.stopPropagation()}>
        {/* Drawer Header */}
        <div className="logs-drawer-header">
          <div className="logs-header-title">
            <span className="logs-icon">⚙️</span>
            <div>
              <h3>Engine Telemetry & Trace</h3>
              <p>Node steps, execution timings, and tool outputs</p>
            </div>
          </div>
          <button type="button" className="btn-close-drawer" onClick={onClose} title="Close (Esc)">
            ✕
          </button>
        </div>

        {/* Tab Navigation */}
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
            <span>Errors ({errorCount})</span>
            {errorCount > 0 && <span className="error-count-pill">{errorCount}</span>}
          </button>
          <button
            type="button"
            className={`logs-tab-btn ${tab === 'raw' ? 'active' : ''}`}
            onClick={() => setTab('raw')}
          >
            <span>Raw Data</span>
          </button>
        </div>

        {/* Drawer Body */}
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
                          <span className="node-name">{step.label}</span>
                          {row.timestamp && <span className="trace-time">{row.timestamp}</span>}
                        </div>
                        {row.summary && <p className="trace-summary">{row.summary}</p>}
                      </div>
                    );
                  })}
                </div>
              ) : isRunning ? (
                <div className="logs-empty">
                  <div className="radar-spinner-pulse" />
                  <p>Orchestrator graph is actively executing tools…</p>
                </div>
              ) : (
                <div className="logs-empty">
                  <p>No query steps executed yet. Ask a question to see real-time graph trace.</p>
                </div>
              )}
            </div>
          )}

          {tab === 'errors' && (
            <div className="errors-log-view">
              {backendUp === false && (
                <div className="error-card critical">
                  <div className="error-head">
                    <span className="error-type">API_UNREACHABLE</span>
                    <span className="error-badge">Offline</span>
                  </div>
                  <p className="error-desc">
                    Could not reach the SatQuery backend on <code>localhost:8000</code> or the configured API URL.
                  </p>
                </div>
              )}

              {errors && errors.length > 0 ? (
                errors.map((err, i) => (
                  <div key={i} className="error-card">
                    <div className="error-head">
                      <span className="error-type">SYSTEM_ERROR #{i + 1}</span>
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
              <div className="raw-actions-bar">
                <button type="button" className="btn-copy-raw" onClick={handleCopyRaw}>
                  {copiedRaw ? '✓ Copied JSON' : '📋 Copy JSON Telemetry'}
                </button>
              </div>
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

        {/* Drawer Footer */}
        <div className="logs-drawer-footer">
          <span className="footer-status-txt">
            Engine: {backendUp ? 'Online' : backendUp === false ? 'Offline' : 'Connecting'}
          </span>
          <button type="button" className="btn-close-sub" onClick={onClose}>
            Close Drawer
          </button>
        </div>
      </aside>
    </div>
  );
}
