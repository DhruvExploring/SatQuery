import React from 'react';
import ToolResultsPanel from './ToolResultsPanel';
import LiveTrace from './LiveTrace';
import RasterViewer from './RasterViewer';
import { collectRasterAssets } from '../api/rasters';
import { INTENTS } from '../state/intents';

function CapabilityGuide({ finalAnswer, onSelectIntent }) {
  return (
    <div className="capability-guide">
      <p className="ai-narrative-text">{finalAnswer}</p>
      <p className="form-hint">
        No tools ran. This is a capability guide, not an analysis — there is no imagery to show.
      </p>
      <div className="example-chips-wrap">
        {INTENTS.map((chip) => (
          <button
            key={chip.id}
            type="button"
            className="example-chip"
            onClick={() => onSelectIntent(chip.id)}
          >
            {chip.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function ResultsView({
  handled,
  queryText,
  onNewAnalysis,
  onViewTrace,
  onOpenReport,
  onSelectIntent,
  onErrorAction,
  isRunning
}) {
  const kind = handled?.kind || 'empty';
  const toolName = handled?.toolName;
  const httpStatus = handled?.httpStatus;
  const copy = handled?.copy || {};
  const toolResults = handled?.toolResults || [];
  const rasters = collectRasterAssets(toolResults);
  const trace = handled?.executionTrace || [];
  const hops = trace.length;

  const statusBadge = kind === 'success'
    ? 'badge-success'
    : kind === 'ok'
      ? 'badge-format'
      : kind === 'error'
        ? 'badge-danger'
        : 'badge-tag';

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
              <span className="meta-chip-label">STATUS</span>
              <span className="meta-chip-val">{handled?.status || '—'}</span>
            </div>
          </div>
          <div className="meta-chip">
            <div className="meta-chip-icon">🎯</div>
            <div className="meta-chip-content">
              <span className="meta-chip-label">TOOL</span>
              <span className="meta-chip-val">{toolName ? String(toolName).replace(/_/g, ' ') : 'none'}</span>
            </div>
          </div>
          <div className="meta-chip">
            <div className="meta-chip-icon">🆔</div>
            <div className="meta-chip-content">
              <span className="meta-chip-label">HTTP</span>
              <span className="meta-chip-val">{httpStatus || '—'}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="dashboard-grid-results">
        {(kind === 'success' || (kind === 'error' && rasters.length > 0)) && rasters.length > 0 ? (
          <RasterViewer rasters={rasters} isRunning={isRunning} />
        ) : (
          <div className="card results-main-card">
            <div className="results-main-header">
              <span className={`badge ${statusBadge}`}>{kind.toUpperCase()}</span>
              {hops > 1 && (
                <span className="badge badge-format">{hops} graph hops</span>
              )}
            </div>

            {kind === 'empty' && (
              <p className="form-hint" style={{ padding: '1.5rem' }}>
                Run a query from Analyze. Imagery appears here when a tool returns a GeoTIFF.
              </p>
            )}

            {kind === 'ok' && (
              <div style={{ padding: '1.25rem' }}>
                <h3 style={{ color: '#fff', marginBottom: '0.75rem' }}>{copy.title}</h3>
                <CapabilityGuide finalAnswer={handled.finalAnswer} onSelectIntent={onSelectIntent} />
              </div>
            )}

            {kind === 'error' && (
              <div className={`error-banner http-${httpStatus}`} style={{ margin: '1rem' }}>
                <strong>{copy.title}</strong>
                <p>{copy.message}</p>
                {Array.isArray(handled.errors) && handled.errors.length > 0 && (
                  <ul className="error-list">
                    {handled.errors.map((err, idx) => <li key={idx}>{err}</li>)}
                  </ul>
                )}
                {copy.actions?.length > 0 && (
                  <div className="example-chips-wrap" style={{ marginTop: '0.6rem' }}>
                    {copy.actions.map((action) => (
                      <button
                        key={action.id}
                        type="button"
                        className="example-chip"
                        onClick={() => onErrorAction(action.id)}
                      >
                        {action.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {kind === 'success' && (
              <div style={{ padding: '1.25rem' }}>
                <h3 style={{ color: '#fff', marginBottom: '0.75rem' }}>{copy.title}</h3>
                <div className="ai-narrative-text">{handled.finalAnswer}</div>
              </div>
            )}

            {isRunning && (
              <div style={{ padding: '1.25rem' }}>
                <LiveTrace isRunning executionTrace={trace} />
              </div>
            )}
          </div>
        )}

        <div className="card ai-response-card">
          <div className="ai-response-header">
            <div className="ai-title-group">
              <span>{kind === 'ok' ? 'Capability guide' : 'Tool results'}</span>
            </div>
            <div className="ai-badges">
              <span className={`badge ${statusBadge}`}>{handled?.status || 'idle'}</span>
            </div>
          </div>

          {queryText && (
            <p className="form-hint">Query: “{queryText}”</p>
          )}

          {kind === 'success' && handled?.finalAnswer && rasters.length > 0 && (
            <div className="ai-narrative-text">{handled.finalAnswer}</div>
          )}

          {hops > 1 && kind === 'success' && (
            <LiveTrace executionTrace={trace} hopCapHit={handled?.hopCapHit} />
          )}

          {kind === 'ok' ? (
            <p className="form-hint">No GeoTIFF or analysis products — the planner chose chat.</p>
          ) : (
            <ToolResultsPanel toolResults={toolResults} kind={kind} />
          )}

          <div className="action-buttons-group">
            <button type="button" className="btn-secondary primary-shade" onClick={onOpenReport}>
              📄 Audit Report
            </button>
            <button type="button" className="btn-secondary" onClick={onViewTrace}>
              ⚡ View Trace
            </button>
            <button type="button" className="btn-secondary" onClick={onNewAnalysis}>
              New query
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
