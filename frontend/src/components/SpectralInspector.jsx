import React, { useState } from 'react';

const INDICES_DATABASE = [
  {
    name: 'NDVI',
    fullName: 'Normalized Difference Vegetation Index',
    formula: '(B08 - B04) / (B08 + B04)',
    bands: 'NIR (B08), Red (B04)',
    range: '-1.0 to +1.0',
    colorScale: 'Greens',
    desc: 'Standard metric for photosynthetic canopy vigor, green biomass density, and vegetation health.'
  },
  {
    name: 'NDMI',
    fullName: 'Normalized Difference Moisture Index',
    formula: '(B08 - B11) / (B08 + B11)',
    bands: 'NIR (B08), SWIR1 (B11)',
    range: '-1.0 to +1.0',
    colorScale: 'Teals',
    desc: 'Sensitive to canopy water content and liquid leaf moisture; crucial for drought monitoring.'
  },
  {
    name: 'NDWI',
    fullName: 'Normalized Difference Water Index',
    formula: '(B03 - B08) / (B03 + B08)',
    bands: 'Green (B03), NIR (B08)',
    range: '-1.0 to +1.0',
    colorScale: 'Blues',
    desc: 'Delineates open water bodies, rivers, reservoirs, and surface water inundation.'
  },
  {
    name: 'NBR',
    fullName: 'Normalized Burn Ratio',
    formula: '(B08 - B12) / (B08 + B12)',
    bands: 'NIR (B08), SWIR2 (B12)',
    range: '-1.0 to +1.0',
    colorScale: 'Ambers',
    desc: 'Standard for mapping wildfire scars; differential dNBR categorizes burn severity.'
  },
  {
    name: 'EVI',
    fullName: 'Enhanced Vegetation Index',
    formula: '2.5 * (B08 - B04) / (B08 + 6.0*B04 - 7.5*B02 + 1.0)',
    bands: 'NIR (B08), Red (B04), Blue (B02)',
    range: '-1.0 to +1.0',
    colorScale: 'Emeralds',
    desc: 'Decouples background soil canopy noise and atmospheric aerosol interference in dense forests.'
  },
  {
    name: 'SAVI',
    fullName: 'Soil Adjusted Vegetation Index',
    formula: '((B08 - B04) / (B08 + B04 + 0.5)) * 1.5',
    bands: 'NIR (B08), Red (B04), L=0.5',
    range: '-1.0 to +1.0',
    colorScale: 'Khaki-Green',
    desc: 'Minimizes soil brightness influences in arid, semi-arid, or young crop emerging fields.'
  },
  {
    name: 'NDRE',
    fullName: 'Normalized Difference Red Edge Index',
    formula: '(B08 - B05) / (B08 + B05)',
    bands: 'NIR (B08), RedEdge1 (B05)',
    range: '-1.0 to +1.0',
    colorScale: 'Lime',
    desc: 'Monitors late-stage agricultural crops where chlorophyll concentration saturates regular NDVI.'
  },
  {
    name: 'BSI',
    fullName: 'Bare Soil Index',
    formula: '((B11 + B04) - (B08 + B02)) / ((B11 + B04) + (B08 + B02))',
    bands: 'SWIR1 (B11), Red (B04), NIR (B08), Blue (B02)',
    range: '-1.0 to +1.0',
    colorScale: 'Ochre',
    desc: 'Differentiates bare soil, fallow fields, and open land from built-up or vegetated surfaces.'
  },
  {
    name: 'NDSI',
    fullName: 'Normalized Difference Snow Index',
    formula: '(B03 - B11) / (B03 + B11)',
    bands: 'Green (B03), SWIR1 (B11)',
    range: '-1.0 to +1.0',
    colorScale: 'Cyan-Ice',
    desc: 'Separates snow cover and glaciers from dense cloud cover using strong SWIR absorption.'
  }
];

const SENTINEL2_BANDS = [
  { id: 'B01', name: 'Coastal Aerosol', wave: '443 nm', res: '60 m', role: 'Atmospheric aerosols, ocean color' },
  { id: 'B02', name: 'Blue', wave: '490 nm', res: '10 m', role: 'True-color RGB, aerosol, water penetration' },
  { id: 'B03', name: 'Green', wave: '560 nm', res: '10 m', role: 'True-color RGB, peak vegetation reflectance, NDWI' },
  { id: 'B04', name: 'Red', wave: '665 nm', res: '10 m', role: 'True-color RGB, chlorophyll absorption, NDVI' },
  { id: 'B05', name: 'Red Edge 1', wave: '705 nm', res: '20 m', role: 'Vegetation classification & stress, NDRE' },
  { id: 'B06', name: 'Red Edge 2', wave: '740 nm', res: '20 m', role: 'Canopy chlorophyll content profiling' },
  { id: 'B07', name: 'Red Edge 3', wave: '783 nm', res: '20 m', role: 'Leaf area index (LAI) evaluation' },
  { id: 'B08', name: 'NIR Broad', wave: '842 nm', res: '10 m', role: 'Biomass structure, vegetation health, NDVI, NBR' },
  { id: 'B8A', name: 'NIR Narrow', wave: '865 nm', res: '20 m', role: 'Water vapor atmospheric correction' },
  { id: 'B09', name: 'Water Vapour', wave: '945 nm', res: '60 m', role: 'Atmospheric column water vapor' },
  { id: 'B11', name: 'SWIR 1', wave: '1610 nm', res: '20 m', role: 'Canopy moisture, moisture stress (NDMI), snow (NDSI)' },
  { id: 'B12', name: 'SWIR 2', wave: '2190 nm', res: '20 m', role: 'Burn severity (NBR), geology, soil minerals' }
];

const WORLDCOVER_CLASSES = [
  { code: 10, name: 'Tree cover', color: '#006400' },
  { code: 20, name: 'Shrubland', color: '#ffbb22' },
  { code: 30, name: 'Grassland', color: '#ffff4c' },
  { code: 40, name: 'Cropland', color: '#f096ff' },
  { code: 50, name: 'Built-up', color: '#fa0000' },
  { code: 60, name: 'Bare / Sparse vegetation', color: '#b4b4b4' },
  { code: 70, name: 'Snow and ice', color: '#f0f0f0' },
  { code: 80, name: 'Permanent water bodies', color: '#0064c8' },
  { code: 90, name: 'Herbaceous wetland', color: '#0096a0' },
  { code: 95, name: 'Mangroves', color: '#00cf75' },
  { code: 100, name: 'Moss and lichen', color: '#fae6a0' }
];

export default function SpectralInspector({ onSelectIndex }) {
  const [activeSubTab, setActiveSubTab] = useState('indices');
  const [searchFilter, setSearchFilter] = useState('');

  const filteredIndices = INDICES_DATABASE.filter(
    (idx) =>
      idx.name.toLowerCase().includes(searchFilter.toLowerCase()) ||
      idx.fullName.toLowerCase().includes(searchFilter.toLowerCase()) ||
      idx.desc.toLowerCase().includes(searchFilter.toLowerCase())
  );

  return (
    <div className="spectral-lab-container">
      <div className="spectral-header">
        <div>
          <h2>Spectral & Biophysical Telemetry Reference</h2>
          <p>
            Curated mathematical index engines, Sentinel-2 band configurations, and ESA WorldCover categorical
            dictionaries utilized across Tools 5, 7, and 8.
          </p>
        </div>
        <div className="subtab-buttons">
          <button
            type="button"
            className={`subtab-btn ${activeSubTab === 'indices' ? 'active' : ''}`}
            onClick={() => setActiveSubTab('indices')}
          >
            Vegetation & Water Indices ({INDICES_DATABASE.length})
          </button>
          <button
            type="button"
            className={`subtab-btn ${activeSubTab === 'bands' ? 'active' : ''}`}
            onClick={() => setActiveSubTab('bands')}
          >
            Sentinel-2 Bands ({SENTINEL2_BANDS.length})
          </button>
          <button
            type="button"
            className={`subtab-btn ${activeSubTab === 'lulc' ? 'active' : ''}`}
            onClick={() => setActiveSubTab('lulc')}
          >
            ESA WorldCover (10m)
          </button>
        </div>
      </div>

      {activeSubTab === 'indices' && (
        <div className="indices-view">
          <div className="indices-toolbar">
            <input
              type="text"
              placeholder="Search index name or application (e.g. moisture, wildfire, NDVI)..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              className="indices-search-input"
            />
          </div>

          <div className="indices-cards-grid">
            {filteredIndices.map((idx) => (
              <div key={idx.name} className="index-card">
                <div className="index-card-head">
                  <span className="index-acronym">{idx.name}</span>
                  <span className="index-range">{idx.range}</span>
                </div>
                <h4 className="index-fullname">{idx.fullName}</h4>
                <div className="index-formula-box">
                  <code>{idx.formula}</code>
                </div>
                <div className="index-meta-row">
                  <span className="meta-item"><strong>Bands:</strong> {idx.bands}</span>
                </div>
                <p className="index-desc">{idx.desc}</p>
                {onSelectIndex && (
                  <button
                    type="button"
                    className="btn-cyan-outline"
                    onClick={() => onSelectIndex(idx.name)}
                  >
                    Compute {idx.name} in Query
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {activeSubTab === 'bands' && (
        <div className="bands-view">
          <table className="telemetry-table">
            <thead>
              <tr>
                <th>Band ID</th>
                <th>Common Name</th>
                <th>Central Wavelength</th>
                <th>Native Resolution</th>
                <th>Primary Application</th>
              </tr>
            </thead>
            <tbody>
              {SENTINEL2_BANDS.map((b) => (
                <tr key={b.id}>
                  <td><span className="band-badge">{b.id}</span></td>
                  <td><strong>{b.name}</strong></td>
                  <td><code>{b.wave}</code></td>
                  <td><span className="res-badge">{b.res}</span></td>
                  <td className="role-cell">{b.role}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {activeSubTab === 'lulc' && (
        <div className="lulc-view">
          <p className="lulc-intro">
            Tool 8 categorizes biomes using the 10m ESA WorldCover discrete classification system for zonal cross-tabulation:
          </p>
          <div className="lulc-classes-grid">
            {WORLDCOVER_CLASSES.map((c) => (
              <div key={c.code} className="lulc-card">
                <span className="lulc-swatch" style={{ backgroundColor: c.color }} />
                <div className="lulc-info">
                  <span className="lulc-code">Class {c.code}</span>
                  <strong className="lulc-name">{c.name}</strong>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
