import React from 'react';

const WORKFLOW_CARDS = [
  {
    id: 'deforestation',
    title: 'Deforestation & Canopy Loss Impact',
    tag: 'T1/T2 Multi-Spectral + LULC',
    code: 'FOREST',
    mode: 'pair',
    pipeline: ['Tool 2 (MSI)', 'Tool 5 (NDVI)', 'Tool 6 (QA)', 'Tool 7 (Temporal Change)', 'Tool 8 (LULC & DEM)', 'Tool 4 (Weather)'],
    description: 'Computes multi-temporal NDVI vegetation shifts, generates change_mask.tif, and cross-tabulates forest loss against ESA WorldCover and slope gradients.',
    suggestedQuery: 'Analyze deforestation and forest canopy loss across the observation dates. Compute NDVI for both dates, generate the change mask, and cross-tabulate forest loss against terrain slope.',
    bbox: [-63.50, -10.20, -63.20, -9.95]
  },
  {
    id: 'flood_sar',
    title: 'All-Weather Flood Inundation & SAR',
    tag: 'Cloud-Penetrating Radar',
    code: 'SAR',
    mode: 'pair',
    pipeline: ['Tool 1 (Optical Check)', 'Tool 3 (SAR C-Band)', 'Tool 7 (Change Detection)', 'Tool 8 (Zonal Cross-Tab)'],
    description: 'Detects severe cloud obstruction on optical pass and falls back to Sentinel-1 GRD SAR backscatter dB drop to map surface water inundation.',
    suggestedQuery: 'Assess flood inundation extent using cloud-penetrating Sentinel-1 SAR imagery. Detect backscatter drop in dB and overlay the water mask onto cropland vs built-up areas.',
    bbox: [77.20, 28.58, 77.30, 28.70]
  },
  {
    id: 'wildfire_dnbr',
    title: 'Wildfire Burn Severity (dNBR)',
    tag: 'Spectral Biophysical Index',
    code: 'BURN',
    mode: 'pair',
    pipeline: ['Tool 2 (NIR + SWIR2)', 'Tool 5 (NBR Calculation)', 'Tool 7 (Delta NBR Algebra)', 'Tool 8 (Patch Fragmentation)'],
    description: 'Calculates normalized burn ratio (NBR) from NIR and SWIR bands for pre- and post-fire rasters, categorizing damage into unburned, moderate, and high severity.',
    suggestedQuery: 'Compute normalized burn ratio (NBR) and delta NBR (dNBR) to evaluate wildfire burn severity and vegetation destruction.',
    bbox: [-121.65, 39.70, -121.50, 39.85]
  },
  {
    id: 'drought_stress',
    title: 'Agricultural Drought & Moisture Stress',
    tag: 'Biophysical + ERA5 Weather',
    code: 'DROUGHT',
    mode: 'single',
    pipeline: ['Tool 2 (MSI)', 'Tool 5 (NDVI + NDMI)', 'Tool 4 (ECMWF Weather & Evapotranspiration)'],
    description: 'Couples satellite plant canopy moisture (NDMI) with Open-Meteo precipitation deficit and vapor pressure deficit (VPD) to identify severe drought stress.',
    suggestedQuery: 'Evaluate agricultural drought and crop canopy stress. Calculate NDVI and NDMI vegetation moisture indices and check the local weather precipitation anomaly.',
    bbox: [77.10, 28.50, 77.30, 28.70]
  },
  {
    id: 'terrain_slope',
    title: 'Topographical Slope & Landcover Matrix',
    tag: 'Discrete GIS & Copernicus DEM',
    code: 'TERRAIN',
    mode: 'single',
    pipeline: ['Tool 8 (ESA WorldCover)', 'Copernicus DEM (30m)', 'Tool 8 (Slope Gradient & Fragmentation)'],
    description: 'Ingests land cover classification and DEM rasters, calculates 2D spatial slope in degrees, and profiles 8-connectivity patch fragmentation and Largest Patch Index (LPI).',
    suggestedQuery: 'Perform landscape landcover composition profiling and derive the 2D topographical slope gradient map.',
    bbox: [14.95, 37.70, 15.05, 37.80]
  },
  {
    id: 'spatial_geocoding',
    title: 'Spatial Geocoding & Affine Feature Markup',
    tag: 'Vector to Raster Projection',
    code: 'GEOCODE',
    pipeline: ['Tool 10 (Forward/Reverse Geocode)', 'Tool 10 (Scene POI Discovery)', 'Tool 11 (Affine Mathematical Markup)'],
    mode: 'single',
    description: 'Identifies the scene identity and points of interest inside the bounding box and mathematically projects lat/long coordinates onto pixel coordinates without hallucination.',
    suggestedQuery: 'Resolve the scene identity and discover key landmarks and points of interest within this bounding box, then mark their locations on the image.',
    bbox: [77.20, 28.58, 77.30, 28.70]
  }
];

export default function WorkflowPresets({ onSelectWorkflow }) {
  return (
    <div className="workflows-container">
      <div className="workflows-header">
        <div>
          <h2>Autonomous Geospatial Workflows</h2>
          <p>
            Standard multi-tool analytical recipes orchestrating Earth Observation ingestion, differential algebra,
            and terrain cross-tabulation.
          </p>
        </div>
      </div>

      <div className="workflows-grid">
        {WORKFLOW_CARDS.map((wf) => (
          <div key={wf.id} className="workflow-card">
            <div className="workflow-card-top">
              <span className="wf-tag">{wf.code}</span>
              <div className="workflow-tag-group">
                <span className="workflow-tag">{wf.tag}</span>
                <span className="workflow-mode-pill">{wf.mode === 'pair' ? 'Dual Temporal Pair' : 'Single Scene'}</span>
              </div>
            </div>

            <h3 className="workflow-title">{wf.title}</h3>
            <p className="workflow-desc">{wf.description}</p>

            <div className="workflow-pipeline">
              <span className="pipeline-label">Execution Graph:</span>
              <div className="pipeline-chips">
                {wf.pipeline.map((step, idx) => (
                  <React.Fragment key={step}>
                    <span className="pipeline-chip">{step}</span>
                    {idx < wf.pipeline.length - 1 && <span className="pipeline-arrow">→</span>}
                  </React.Fragment>
                ))}
              </div>
            </div>

            <div className="workflow-query-preview">
              <span className="query-preview-label">Suggested Query:</span>
              <p className="query-preview-text">"{wf.suggestedQuery}"</p>
            </div>

            <button
              type="button"
              className="btn-cyan btn-full-width"
              onClick={() => onSelectWorkflow(wf)}
            >
              Load Workflow in Studio
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
