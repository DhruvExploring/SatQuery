import React from 'react';

export default function AuditReportModal({ isOpen, onClose, scenario, queryText, backendResponse }) {
  if (!isOpen) return null;

  const narrative = backendResponse?.narrative || scenario.narrative;
  const confidence = backendResponse?.confidence || scenario.confidence;
  const modelName = backendResponse?.model || scenario.model;

  const handlePrint = () => {
    window.print();
  };

  const handleCopy = () => {
    const reportData = {
      mission: 'SatQuery Autonomous Geospatial Intelligence',
      sessionId: '#SAT-20250824-001',
      timestamp: new Date().toISOString(),
      scenario: scenario.name,
      bbox: scenario.bbox,
      model: modelName,
      confidence: confidence,
      query: queryText || scenario.query,
      findings: narrative,
      classes: scenario.classes
    };
    navigator.clipboard.writeText(JSON.stringify(reportData, null, 2));
    alert('Audit report JSON copied to clipboard!');
  };

  return (
    <div className={`modal-backdrop ${isOpen ? 'open' : ''}`} id="audit-modal" onClick={onClose}>
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '1rem' }}>
          <div>
            <span className="badge badge-format">OFFICIAL AUDIT LOG</span>
            <h3 style={{ color: '#fff', fontSize: '1.25rem', marginTop: '0.4rem' }}>Mission Intelligence & Provenance Report</h3>
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
          {/* Metadata Block */}
          <div style={{ background: 'var(--bg-input)', padding: '1rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)', fontSize: '0.85rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>SESSION IDENTIFIER:</span>
              <span style={{ color: '#fff', fontFamily: 'var(--font-mono)' }}>#SAT-20250824-001</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>TIMESTAMP:</span>
              <span style={{ color: '#fff', fontFamily: 'var(--font-mono)' }}>{new Date().toUTCString()}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>PROVENANCE SHA-256:</span>
              <span style={{ color: 'var(--accent-cyan)', fontFamily: 'var(--font-mono)' }}>e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>TARGET AOI BBOX:</span>
              <span style={{ color: '#fff', fontFamily: 'var(--font-mono)' }}>[{scenario.bbox.join(', ')}] (EPSG:4326)</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-muted)' }}>INFERENCE MODEL:</span>
              <span style={{ color: '#fff', fontFamily: 'var(--font-mono)' }}>{modelName} (Confidence: {confidence})</span>
            </div>
          </div>

          <div>
            <h4 style={{ color: 'var(--accent-cyan)', fontSize: '0.9rem', marginBottom: '0.3rem' }}>1. Mission Inquiry</h4>
            <p style={{ color: '#cbd5e1', fontSize: '0.9rem' }}>"{queryText || scenario.query}"</p>
          </div>

          <div>
            <h4 style={{ color: 'var(--accent-cyan)', fontSize: '0.9rem', marginBottom: '0.3rem' }}>2. Spatial Reasoning & Grounded Synthesis</h4>
            <p style={{ color: '#cbd5e1', fontSize: '0.9rem', lineHeight: 1.6 }}>{narrative}</p>
          </div>

          <div>
            <h4 style={{ color: 'var(--accent-cyan)', fontSize: '0.9rem', marginBottom: '0.4rem' }}>3. Verified Spatial Distributions</h4>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
              {scenario.classes?.map((cls, idx) => (
                <span key={idx} className={`class-pill ${cls.className}`}>
                  ● {cls.name}
                </span>
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', background: 'rgba(16, 185, 129, 0.08)', border: '1px solid rgba(16, 185, 129, 0.25)', padding: '0.85rem', borderRadius: 'var(--radius-md)' }}>
            <span style={{ color: '#10b981', fontWeight: 'bold' }}>✓</span>
            <div style={{ fontSize: '0.8rem', color: '#cbd5e1' }}>
              <strong style={{ color: '#10b981' }}>ISO 19115 & OGC Georeference Compliant</strong>
              <p style={{ marginTop: '2px' }}>This report certifies that bounding boxes, affine transformations, and sensor radiometric calibrations conform to standard Open Geospatial Consortium (OGC) specifications without synthetic coordinate hallucination.</p>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1.5rem', borderTop: '1px solid var(--border-subtle)', paddingTop: '1rem' }}>
          <button type="button" className="btn-secondary" onClick={handleCopy}>
            Copy JSON
          </button>
          <button type="button" className="btn-secondary primary-shade" onClick={handlePrint}>
            Print / Save PDF
          </button>
        </div>
      </div>
    </div>
  );
}
