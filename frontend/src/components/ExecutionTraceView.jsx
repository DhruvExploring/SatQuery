import React from 'react';
import LiveTrace from './LiveTrace';

export default function ExecutionTraceView({ handled, telemetry, onOpenReport }) {
  const trace = handled?.executionTrace || [];
  const toolCount = handled?.toolResults?.length || 0;
  const status = handled?.status || 'idle';
  const kind = handled?.kind || 'empty';

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
            <p className="page-subtitle">validate → plan → execute → advance → … from execution_trace[]</p>
          </div>
        </div>
      </div>

      <div className="dashboard-grid-trace">
        <div className="card session-summary-card">
          <div className="session-id-title">Latest graph run</div>
          <div className="session-time">{kind === 'empty' ? 'No run yet' : `status: ${status}`}</div>

          <table className="config-table">
            <tbody>
              <tr><td>Semantic status</td><td>{status}</td></tr>
              <tr><td>HTTP</td><td>{handled?.httpStatus ?? '—'}</td></tr>
              <tr><td>Plan action</td><td>{handled?.plan?.action || '—'}</td></tr>
              <tr><td>Plan tool</td><td>{handled?.plan?.tool || handled?.toolName || '—'}</td></tr>
              <tr><td>Hops</td><td>{trace.length}</td></tr>
            </tbody>
          </table>
        </div>

        <div className="card trace-timeline-card">
          <div className="timeline-header">
            <span className="badge badge-format">LANGGRAPH PIPELINE</span>
            <h3 style={{ color: '#fff', fontSize: '1.15rem' }}>Agentic Execution Timeline</h3>
          </div>

          <div className="metrics-grid-4">
            <div className="metric-card">
              <div className="metric-header"><span>PIPELINE TIME</span></div>
              <div className="metric-number" id="trace-total-time">{telemetry?.totalTime || '—'}</div>
            </div>
            <div className="metric-card">
              <div className="metric-header"><span>GRAPH STATUS</span></div>
              <div className="metric-number" style={{ fontSize: '1.1rem' }}>{status}</div>
            </div>
            <div className="metric-card">
              <div className="metric-header"><span>TRACE STEPS</span></div>
              <div className="metric-number">{trace.length}</div>
            </div>
            <div className="metric-card">
              <div className="metric-header"><span>TOOLS RAN</span></div>
              <div className="metric-number" style={{ color: '#38bdf8' }}>{toolCount}</div>
            </div>
          </div>

          <LiveTrace
            executionTrace={trace}
            hopCapHit={Boolean(handled?.hopCapHit)}
          />
        </div>

        <div className="card session-summary-card">
          <div className="timeline-header">
            <span className="badge badge-format">PLAN REASON</span>
            <h4 style={{ color: '#fff' }}>Planner note</h4>
          </div>
          <p className="form-hint">{handled?.plan?.reason || handled?.finalAnswer || 'Run a query to populate the trace.'}</p>
          {Array.isArray(handled?.errors) && handled.errors.length > 0 && (
            <ul className="error-list">
              {handled.errors.map((err, idx) => <li key={idx}>{err}</li>)}
            </ul>
          )}
          <div style={{ marginTop: '1.25rem' }}>
            <button
              type="button"
              className="btn-secondary primary-shade"
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
