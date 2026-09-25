import React, { useEffect, useRef, useState } from 'react';

const PRESET_LOCATIONS = [
  { name: 'Yamuna River (Delhi, India)', bbox: [77.20, 28.58, 77.30, 28.70], desc: 'Urban river monitoring & monsoon flooding' },
  { name: 'Amazon Basin (Rondônia, Brazil)', bbox: [-63.50, -10.20, -63.20, -9.95], desc: 'Tropical forest loss & fire scars' },
  { name: 'Valencia Coast (Spain)', bbox: [-0.45, 39.40, -0.30, 39.55], desc: 'Flash flood inundation & lagoon changes' },
  { name: 'Camp Fire / Paradise (California)', bbox: [-121.65, 39.70, -121.50, 39.85], desc: 'Wildfire burn severity analysis (dNBR)' },
  { name: 'Suez Canal (Great Bitter Lake)', bbox: [32.30, 30.25, 32.48, 30.45], desc: 'Maritime SAR radar backscatter & shipping' },
  { name: 'Mount Etna (Sicily, Italy)', bbox: [14.95, 37.70, 15.05, 37.80], desc: 'Volcanic thermal & spectral characterization' }
];

export default function MapSelector({ initialBbox, onApplyBbox, onCancel }) {
  const mapContainerRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const rectLayerRef = useRef(null);

  const [currentBbox, setCurrentBbox] = useState(initialBbox || [77.10, 28.50, 77.30, 28.70]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [drawingMode, setDrawingMode] = useState(false);
  const isDraggingRef = useRef(false);
  const startLatLngRef = useRef(null);

  useEffect(() => {
    if (!window.L || !mapContainerRef.current) return;

    if (!mapInstanceRef.current) {
      const midLon = (currentBbox[0] + currentBbox[2]) / 2;
      const midLat = (currentBbox[1] + currentBbox[3]) / 2;

      const map = window.L.map(mapContainerRef.current, {
        center: [midLat, midLon],
        zoom: 11,
        zoomControl: false
      });

      window.L.control.zoom({ position: 'bottomright' }).addTo(map);

      // High-res Esri World Imagery (satellite)
      const esriSatellite = window.L.tileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        {
          attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
          maxZoom: 18
        }
      ).addTo(map);

      // Subtle labels overlay
      const labels = window.L.tileLayer(
        'https://{s}.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}{r}.png',
        {
          attribution: '&copy; CartoDB',
          subdomains: 'abcd',
          maxZoom: 18
        }
      ).addTo(map);

      mapInstanceRef.current = map;

      // Draw initial rectangle
      drawRectangleOnMap(currentBbox);

      // Handle interactive drag-draw box
      map.on('mousedown', (e) => {
        if (!drawingMode) return;
        map.dragging.disable();
        isDraggingRef.current = true;
        startLatLngRef.current = e.latlng;
      });

      map.on('mousemove', (e) => {
        if (!isDraggingRef.current || !startLatLngRef.current) return;
        const start = startLatLngRef.current;
        const current = e.latlng;
        const minLon = Math.min(start.lng, current.lng);
        const maxLon = Math.max(start.lng, current.lng);
        const minLat = Math.min(start.lat, current.lat);
        const maxLat = Math.max(start.lat, current.lat);

        const newBox = [
          parseFloat(minLon.toFixed(4)),
          parseFloat(minLat.toFixed(4)),
          parseFloat(maxLon.toFixed(4)),
          parseFloat(maxLat.toFixed(4))
        ];
        drawRectangleOnMap(newBox);
      });

      map.on('mouseup', (e) => {
        if (!isDraggingRef.current || !startLatLngRef.current) return;
        isDraggingRef.current = false;
        map.dragging.enable();
        const start = startLatLngRef.current;
        const current = e.latlng;
        const minLon = Math.min(start.lng, current.lng);
        const maxLon = Math.max(start.lng, current.lng);
        const minLat = Math.min(start.lat, current.lat);
        const maxLat = Math.max(start.lat, current.lat);

        if (Math.abs(maxLon - minLon) > 0.005 && Math.abs(maxLat - minLat) > 0.005) {
          const newBox = [
            parseFloat(minLon.toFixed(4)),
            parseFloat(minLat.toFixed(4)),
            parseFloat(maxLon.toFixed(4)),
            parseFloat(maxLat.toFixed(4))
          ];
          setCurrentBbox(newBox);
          drawRectangleOnMap(newBox);
        }
        setDrawingMode(false);
      });
    }

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, []);

  const drawRectangleOnMap = (bbox) => {
    const map = mapInstanceRef.current;
    if (!map || !window.L) return;

    if (rectLayerRef.current) {
      map.removeLayer(rectLayerRef.current);
    }

    const bounds = [
      [bbox[1], bbox[0]], // [south, west]
      [bbox[3], bbox[2]]  // [north, east]
    ];

    const rect = window.L.rectangle(bounds, {
      color: '#09D1C7',
      weight: 2,
      opacity: 0.9,
      fillColor: '#46DFB1',
      fillOpacity: 0.22,
      dashArray: '6, 6'
    }).addTo(map);

    rectLayerRef.current = rect;
  };

  const handleApplyPreset = (preset) => {
    setCurrentBbox(preset.bbox);
    drawRectangleOnMap(preset.bbox);
    if (mapInstanceRef.current) {
      const bounds = [
        [preset.bbox[1], preset.bbox[0]],
        [preset.bbox[3], preset.bbox[2]]
      ];
      mapInstanceRef.current.fitBounds(bounds, { padding: [40, 40], maxZoom: 13 });
    }
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!searchQuery.trim() || isSearching) return;
    setIsSearching(true);
    setSearchError('');

    try {
      const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(searchQuery)}&limit=1`;
      const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
      const data = await res.json();

      if (data && data.length > 0) {
        const item = data[0];
        const lat = parseFloat(item.lat);
        const lon = parseFloat(item.lon);
        const delta = 0.08;
        const newBox = [
          parseFloat((lon - delta).toFixed(4)),
          parseFloat((lat - delta).toFixed(4)),
          parseFloat((lon + delta).toFixed(4)),
          parseFloat((lat + delta).toFixed(4))
        ];
        setCurrentBbox(newBox);
        drawRectangleOnMap(newBox);
        if (mapInstanceRef.current) {
          mapInstanceRef.current.setView([lat, lon], 12);
        }
      } else {
        setSearchError('Location not found. Try a broader city or region name.');
      }
    } catch {
      setSearchError('Geocoding request failed. Please check your network.');
    } finally {
      setIsSearching(false);
    }
  };

  const toggleDrawMode = () => {
    setDrawingMode((prev) => !prev);
  };

  return (
    <div className="map-selector-container">
      <div className="map-toolbar">
        <form className="map-search-form" onSubmit={handleSearch}>
          <input
            type="text"
            placeholder="Search place, river, volcano, or region..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <button type="submit" className="btn-cyan" disabled={isSearching}>
            {isSearching ? 'Searching…' : 'Locate'}
          </button>
        </form>

        <button
          type="button"
          className={`btn-action-tool ${drawingMode ? 'active' : ''}`}
          onClick={toggleDrawMode}
          title="Click to draw a custom bounding box on the satellite map"
        >
          <span>📐</span>
          <span>{drawingMode ? 'Click & Drag on Map' : 'Draw AOI Box'}</span>
        </button>

        <div className="bbox-pill-readout">
          <span className="pill-tag">AOI BBOX</span>
          <code>[{currentBbox.join(', ')}]</code>
        </div>

        <div className="toolbar-actions">
          <button type="button" className="btn-primary-glow" onClick={() => onApplyBbox(currentBbox)}>
            Apply AOI to Query
          </button>
          {onCancel && (
            <button type="button" className="btn-glass" onClick={onCancel}>
              Close
            </button>
          )}
        </div>
      </div>

      {searchError && <div className="map-search-alert">{searchError}</div>}

      <div className="map-split-view">
        <div className="map-canvas-wrap">
          <div ref={mapContainerRef} className={`leaflet-map-host ${drawingMode ? 'drawing-active' : ''}`} />
          {drawingMode && (
            <div className="map-crosshair-overlay">
              <span>Click and drag on the satellite imagery to define your AOI bounding box</span>
            </div>
          )}
        </div>

        <div className="map-presets-sidebar">
          <h3>Geospatial AOI Presets</h3>
          <p className="presets-desc">Select an operational satellite benchmark location:</p>
          <div className="presets-list">
            {PRESET_LOCATIONS.map((loc) => (
              <div
                key={loc.name}
                className="preset-card"
                onClick={() => handleApplyPreset(loc)}
              >
                <div className="preset-card-title">
                  <span className="preset-pin">📍</span>
                  <strong>{loc.name}</strong>
                </div>
                <div className="preset-card-desc">{loc.desc}</div>
                <div className="preset-card-bbox">
                  <code>{loc.bbox.join(', ')}</code>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
