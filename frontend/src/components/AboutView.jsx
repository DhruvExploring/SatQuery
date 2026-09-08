import React from 'react';

export default function AboutView() {
  return (
    <div className="view-page active" id="view-about">
      <div className="page-header">
        <div className="page-title-group">
          <div className="page-icon-badge">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
          </div>
          <div>
            <h1 className="page-title">About <span>SatQuery AI</span></h1>
            <p className="page-subtitle">Autonomous Earth Observation & Geospatial Intelligence Orchestration Engine</p>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.5rem', marginBottom: '1.5rem' }}>
        <div className="card" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <div style={{ fontSize: '1.8rem' }}>🧠</div>
          <h3 style={{ color: '#fff', fontSize: '1.1rem' }}>LangGraph Orchestration</h3>
          <p style={{ color: '#94a3b8', fontSize: '0.875rem', lineHeight: 1.6 }}>
            Deterministic state transitions across validation, multi-candidate planning, isolated tool execution, and grounded natural language response generation.
          </p>
        </div>

        <div className="card" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <div style={{ fontSize: '1.8rem' }}>🛰</div>
          <h3 style={{ color: '#fff', fontSize: '1.1rem' }}>8 Analytical Tools</h3>
          <p style={{ color: '#94a3b8', fontSize: '0.875rem', lineHeight: 1.6 }}>
            Unified ecosystem supporting Optical Imagery, Multispectral Imagery, SAR Radar, Weather Reanalysis, Vegetation Indices, GeoTIFF Inspection, Change Detection, and Land Cover Classification.
          </p>
        </div>

        <div className="card" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <div style={{ fontSize: '1.8rem' }}>🛡</div>
          <h3 style={{ color: '#fff', fontSize: '1.1rem' }}>Geospatial Guardrails</h3>
          <p style={{ color: '#94a3b8', fontSize: '0.875rem', lineHeight: 1.6 }}>
            Strict bounding box validation, georeference affine preservation without resampling distortion, and numerical clipping to physical spectrum bounds.
          </p>
        </div>

        <div className="card" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <div style={{ fontSize: '1.8rem' }}>⚡</div>
          <h3 style={{ color: '#fff', fontSize: '1.1rem' }}>FastMCP Protocol</h3>
          <p style={{ color: '#94a3b8', fontSize: '0.875rem', lineHeight: 1.6 }}>
            Supports Model Context Protocol (FastMCP) tool discovery and native Python imports for high-throughput distributed GeoTIFF batch pipelines.
          </p>
        </div>
      </div>

      <div className="card" style={{ padding: '1.5rem' }}>
        <h3 style={{ color: '#fff', fontSize: '1.1rem', marginBottom: '1rem' }}>System & API Specifications</h3>
        <table className="config-table">
          <tbody>
            <tr><td>Frontend Architecture</td><td>React 19 + Vite (Native ES Modules & CSS Tokens)</td></tr>
            <tr><td>Backend Engine</td><td>FastAPI + LangGraph + GDAL / Rasterio</td></tr>
            <tr><td>API Endpoints</td><td><code>POST /api/v1/query</code>, <code>GET /health</code>, <code>GET /docs</code> — every analysis uses the single query endpoint</td></tr>
            <tr><td>Coordinate Reference System</td><td>WGS 84 (EPSG:4326)</td></tr>
            <tr><td>Constellations Supported</td><td>Sentinel-1 C-Band SAR, Sentinel-2 Optical MSI, Landsat-8/9 OLI, ECMWF ERA5</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
