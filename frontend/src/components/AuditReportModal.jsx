import React from 'react';

export default function AuditReportModal({ isOpen, onClose, queryText, handled, form }) {
  if (!isOpen) return null;

  const bbox = form
    ? [form.min_lon, form.min_lat, form.max_lon, form.max_lat]
    : null;

  const handleCopy = () => {
    const reportData = {
      mission: 'SatQuery',
      timestamp: new Date().toISOString(),
      query: queryText,
      bbox,
      status: handled?.status,
      httpStatus: handled?.httpStatus,
      final_answer: handled?.finalAnswer,
      plan: handled?.plan,
      tool_results: handled?.toolResults,
      errors: handled?.errors,
      execution_trace: handled?.executionTrace
    };
    navigator.clipboard.writeText(JSON.stringify(reportData, null, 2));
  };

  return (
    <div className={`modal-backdrop ${isOpen ? 'open' : ''}`} id="audit-modal" onClick={onClose}>
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '1rem' }}>
          <div>
            <span className="badge badge-format">AUDIT LOG</span>
            <h3 style={{ color: '#fff', fontSize: '1.25rem', marginTop: '0.4rem' }}>Query provenance</h3>
          </div>
          <button
            type="button"
            style={{ background: 'none', border: 'none', color: '#94a3b8', fontSize: '1.25rem', cursor: 'pointer' }}
            onClick={onClose}
          >
            ✕
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem' }}>
          <div style={{ background: 'var(--bg-input)', padding: '1rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)', fontSize: '0.85rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>STATUS</span>
              <span style={{ color: '#fff', fontFamily: 'var(--font-mono)' }}>{handled?.status || '—'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>HTTP</span>
              <span style={{ color: '#fff', fontFamily: 'var(--font-mono)' }}>{handled?.httpStatus ?? '—'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>PLAN TOOL</span>
              <span style={{ color: '#fff', fontFamily: 'var(--font-mono)' }}>{handled?.plan?.tool || handled?.toolName || '—'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-muted)' }}>BBOX</span>
              <span style={{ color: '#fff', fontFamily: 'var(--font-mono)' }}>{bbox ? `[${bbox.join(', ')}]` : '—'}</span>
            </div>
          </div>

          <div>
            <h4 style={{ color: 'var(--accent-cyan)', fontSize: '0.9rem', marginBottom: '0.3rem' }}>1. Query</h4>
            <p style={{ color: '#cbd5e1', fontSize: '0.9rem' }}>"{queryText || '—'}"</p>
          </div>

          <div>
            <h4 style={{ color: 'var(--accent-cyan)', fontSize: '0.9rem', marginBottom: '0.3rem' }}>2. final_answer</h4>
            <p style={{ color: '#cbd5e1', fontSize: '0.9rem', lineHeight: 1.6 }}>{handled?.finalAnswer || '—'}</p>
          </div>

          {Array.isArray(handled?.errors) && handled.errors.length > 0 && (
            <div>
              <h4 style={{ color: 'var(--accent-cyan)', fontSize: '0.9rem', marginBottom: '0.3rem' }}>3. errors[]</h4>
              <ul className="error-list">
                {handled.errors.map((err, idx) => <li key={idx}>{err}</li>)}
              </ul>
            </div>
          )}
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1.5rem', borderTop: '1px solid var(--border-subtle)', paddingTop: '1rem' }}>
          <button type="button" className="btn-secondary" onClick={handleCopy}>
            Copy JSON
          </button>
          <button type="button" className="btn-secondary primary-shade" onClick={() => window.print()}>
            Print / Save PDF
          </button>
        </div>
      </div>
    </div>
  );
}
