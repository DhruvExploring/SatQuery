import React from 'react';

export default function ModelsView() {
  const models = [
    {
      name: 'SatQuery-Vision v2.4',
      badge: 'FOUNDATION MODEL',
      desc: 'Multimodal earth-observation transformer combining Sentinel-2 optical, Landsat-8 multispectral, and Sentinel-1 SAR inputs into a unified spatial reasoning engine.',
      params: '14.2 Billion',
      inputs: 'Optical / SAR / Multispectral',
      latency: '~1.8s',
      status: 'Active',
      statusClass: 'badge-success'
    },
    {
      name: 'FastGeo-7B',
      badge: 'HIGH-THROUGHPUT VQA',
      desc: 'Optimized language-vision model fine-tuned on earth observation query pairs for ultra-low latency interactive question answering.',
      params: '7.1 Billion',
      inputs: 'RGB 512×512 Normalized',
      latency: '~650ms',
      status: 'Ready',
      statusClass: 'badge-format'
    },
    {
      name: 'LandCoverNet-v1',
      badge: 'SEMANTIC SEGMENTATION',
      desc: 'High-precision 12-class land use and land cover semantic segmenter built on a hierarchical vision backbone for agricultural and ecological tracking.',
      params: '340 Million',
      inputs: 'GeoTIFF Surface Reflectance',
      latency: '~420ms',
      status: 'Ready',
      statusClass: 'badge-format'
    },
    {
      name: 'ChangeDetect-XL',
      badge: 'BI-TEMPORAL DIFFERENCING',
      desc: 'Dual-date temporal Siamese transformer designed for deforestation monitoring, disaster damage mapping, and wildfire scar delineation.',
      params: '1.8 Billion',
      inputs: 'Multi-Date GeoTIFF Rasters',
      latency: '~1.2s',
      status: 'Ready',
      statusClass: 'badge-format'
    }
  ];

  return (
    <div className="view-page active" id="view-models">
      <div className="page-header">
        <div className="page-title-group">
          <div className="page-icon-badge">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
              <polyline points="2 17 12 22 22 17"></polyline>
              <polyline points="2 12 12 17 22 12"></polyline>
            </svg>
          </div>
          <div>
            <h1 className="page-title">Remote Sensing <span>Models</span></h1>
            <p className="page-subtitle">Curated earth observation neural architectures & specialized vision heads</p>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '1.5rem' }}>
        {models.map((m, idx) => (
          <div key={idx} className="card" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <span className="badge badge-format" style={{ fontSize: '0.7rem' }}>{m.badge}</span>
                <h3 style={{ color: '#fff', fontSize: '1.2rem', marginTop: '0.4rem' }}>{m.name}</h3>
              </div>
              <span className={`badge ${m.statusClass}`}>{m.status}</span>
            </div>

            <p style={{ color: '#94a3b8', fontSize: '0.875rem', lineHeight: 1.6 }}>{m.desc}</p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.75rem', marginTop: 'auto', background: 'var(--bg-card-elevated)', padding: '0.85rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
              <div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>Parameters</span>
                <span style={{ color: '#fff', fontSize: '0.85rem', fontFamily: 'var(--font-mono)' }}>{m.params}</span>
              </div>
              <div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>Sensors</span>
                <span style={{ color: '#fff', fontSize: '0.85rem', fontFamily: 'var(--font-mono)' }}>{m.inputs}</span>
              </div>
              <div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>Latency</span>
                <span style={{ color: 'var(--accent-cyan)', fontSize: '0.85rem', fontFamily: 'var(--font-mono)' }}>{m.latency}</span>
              </div>
              <div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>Quantization</span>
                <span style={{ color: '#fff', fontSize: '0.85rem', fontFamily: 'var(--font-mono)' }}>FP16 / INT8</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
