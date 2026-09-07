/**
 * Scenario presets and layer definitions for SatQuery
 */

export const SCENARIOS = {
  agriculture: {
    id: 'agriculture',
    name: 'Delhi NCR Agricultural Valley',
    filename: 'agriculture_region_20250824.png',
    format: 'PNG',
    task: 'Visual Question Answering',
    taskBadge: 'VQA',
    confidence: 'High 0.88',
    model: 'EarthMind-4B',
    bbox: [77.10, 28.50, 77.30, 28.70],
    coords: '28.6139° N, 77.2090° E (Delhi)',
    boxLabel: 'Agricultural Land (65%)',
    boxStyle: { top: '22%', left: '24%', width: '42%', height: '54%', borderColor: '#22c55e' },
    query: 'What land cover is visible in this area? Provide a detailed description of the main features and estimate the percentage of each land cover type.',
    narrative: 'The satellite image shows predominantly agricultural land with approximately 65% crop coverage. The area contains a mix of cultivated fields, small settlements, forest patches and a river running through the region. The fields appear to be healthy with good vegetation cover, and there are visible rural settlements and road networks connecting the area.',
    classes: [
      { name: 'Agricultural Land (65%)', className: 'class-agri' },
      { name: 'Forest (18%)', className: 'class-forest' },
      { name: 'Water Body (8%)', className: 'class-water' },
      { name: 'Settlement (4%)', className: 'class-settlement' },
      { name: 'Roads (5%)', className: 'class-roads' }
    ]
  },
  flood: {
    id: 'flood',
    name: 'Mumbai Coastal Floodplain (Sentinel-1)',
    filename: 'sentinel1_mumbai_sar_20250824.tif',
    format: 'GeoTIFF',
    task: 'SAR Flood Detection',
    taskBadge: 'SAR Flood',
    confidence: 'High 0.94',
    model: 'Sentinel-1 IW GRD Head',
    bbox: [72.80, 18.90, 73.00, 19.10],
    coords: '19.0760° N, 72.8777° E (Mumbai)',
    boxLabel: 'Flooded Inundation Zone (216.8 km²)',
    boxStyle: { top: '30%', left: '15%', width: '55%', height: '48%', borderColor: '#0ea5e9' },
    query: 'Detect flooded regions in Mumbai coastal lowlands using Sentinel-1 SAR imagery.',
    narrative: 'Sentinel-1 SAR radar backscatter analysis identifies 216.8 km² of standing water inundation along coastal and lowland floodplains. Low dB specular return distinguishes water bodies clearly from surrounding urban topography with high polarization ratio (VV/VH).',
    classes: [
      { name: 'Inundated Water (34%)', className: 'class-water' },
      { name: 'Saturated Soil (26%)', className: 'class-roads' },
      { name: 'Urban Elevation (28%)', className: 'class-settlement' },
      { name: 'Vegetation Canopy (12%)', className: 'class-forest' }
    ]
  },
  deforestation: {
    id: 'deforestation',
    name: 'Amazon Basin Deforestation Arc',
    filename: 'temporal_change_deforestation_2025.tif',
    format: 'GeoTIFF',
    task: 'Bi-Temporal Change Detection',
    taskBadge: 'Change VQA',
    confidence: 'High 0.91',
    model: 'InternVL3-1B FT',
    bbox: [-62.20, -9.50, -62.00, -9.30],
    coords: '9.4000° S, 62.1000° W (Amazon AOI)',
    boxLabel: 'Significant Forest Loss (-0.24 dNDVI)',
    boxStyle: { top: '25%', left: '30%', width: '40%', height: '45%', borderColor: '#ef4444' },
    query: 'Analyze deforestation and temporal canopy loss in Amazon AOI across multi-date rasters.',
    narrative: 'Temporal change analysis between pre- and post-event rasters indicates 60.98 km² of canopy reduction. Bipolar thresholding confirms persistent clearings along primary road arteries with significant negative NDVI deviation.',
    classes: [
      { name: 'Intact Primary Forest (58%)', className: 'class-forest' },
      { name: 'Recent Tree Loss (16%)', className: 'class-agri' },
      { name: 'Bare Soil Clearing (18%)', className: 'class-roads' },
      { name: 'Secondary Regrowth (8%)', className: 'class-water' }
    ]
  }
};

export const LAYERS = [
  {
    id: 'main',
    name: 'Main Image',
    desc: 'RGB Optical Surface',
    thumb: '/assets/thumb_main.jpg',
    image: '/assets/satellite_rgb.jpg'
  },
  {
    id: 'ndvi',
    name: 'NDVI Index',
    desc: 'Crop & Canopy Health',
    thumb: '/assets/thumb_ndvi.jpg',
    image: '/assets/layer_ndvi_full.jpg'
  },
  {
    id: 'landcover',
    name: 'Land Cover',
    desc: 'Semantic SegNet-12',
    thumb: '/assets/thumb_landcover.jpg',
    image: '/assets/layer_landcover_full.jpg'
  },
  {
    id: 'edge',
    name: 'SAR / Backscatter',
    desc: 'Sentinel-1 C-Band',
    thumb: '/assets/thumb_edge.jpg',
    image: '/assets/layer_sar_full.jpg'
  },
  {
    id: 'annotations',
    name: 'Annotations',
    desc: 'Spatial Clusters',
    thumb: '/assets/thumb_annotations.jpg',
    image: '/assets/layer_annotations_full.jpg'
  }
];

export const INITIAL_TRACE = [
  { step: 1, title: 'Query Received & Classified', desc: 'Task: VQA | Query: What land cover is visible in this area?', time: '14:32:01.120' },
  { step: 2, title: 'Model Selected (LangGraph Router)', desc: 'EarthMind-4B selected via confidence-weighted routing', time: '14:32:03.450' },
  { step: 3, title: 'Image Preprocessed & Normalized', desc: '512×512 RGB | Format: PNG/GeoTIFF | VRAM: 4.2GB', time: '14:32:05.180' },
  { step: 4, title: 'Tool Execution & Model Inference', desc: 'Response generated in 2.3 seconds across 8 remote-sensing heads', time: '14:32:07.820' },
  { step: 5, title: 'Response Validated & Grounded', desc: 'Confidence: 0.88 | Output Tokens: 142 | Status: Success', time: '14:32:09.910' }
];
