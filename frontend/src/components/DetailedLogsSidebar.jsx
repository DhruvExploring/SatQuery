import React, { useEffect, useState } from 'react';
import { describeStep } from '../lib/executionSteps';
import { toolLabel } from '../lib/toolLabels';

/**
 * Detailed Logs & GeoTIFF Metadata Sidebar Drawer
 * 
 * Displays:
 * 1. Step-by-step execution trace & backend tool calls (inputs, outputs, duration, status)
 * 2. Complete, syntax-formatted JSON metadata of the active GeoTIFF file(s)
 */
export default function DetailedLogsSidebar({
  isOpen,
  onClose,
  executionTrace = [],
  toolResults = [],
  isRunning = false,
  errors = [],
  slotA = {},
  slotB = {},
  mode = 'single',
  initialTab = 'logs'
}) {
  const [activeTab, setActiveTab] = useState(initialTab); // 'logs' | 'tiff-json'
  const [selectedTiffSlot, setSelectedTiffSlot] = useState('A'); // 'A' | 'B'
  const [copied, setCopied] = useState(false);
  const [expandedToolIdx, setExpandedToolIdx] = useState(null);

  // Sync activeTab when initialTab changes
  useEffect(() => {
    if (isOpen) {
      setActiveTab(initialTab);
    }
  }, [isOpen, initialTab]);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  // Active slot for TIFF JSON
  const activeSlot = selectedTiffSlot === 'B' && mode === 'pair' ? slotB : slotA;

  // Build complete TIFF JSON representation
  const getTiffJson = () => {
    if (!activeSlot?.uploadedPath && !activeSlot?.originalFilename) {
      return {
        status: 'empty',
        message: 'No GeoTIFF file loaded in this slot.'
      };
    }

    if (activeSlot.rawMetadata) {
      return activeSlot.rawMetadata;
    }

    return {
      file_name: activeSlot.originalFilename || 'unknown.tif',
      file_path: activeSlot.uploadedPath || null,
      spatial: {
        crs: activeSlot.info?.crs || 'EPSG:4326',
        bounds_wgs84: activeSlot.boundsWgs84 || null,
        pixel_size_wgs84_degrees: activeSlot.info?.pixelSizeWgs84Degrees || null
      },
      raster: {
        width: activeSlot.info?.width || null,
        height: activeSlot.info?.height || null,
        band_count: activeSlot.info?.bandCount || null,
        is_georeferenced: activeSlot.info?.georeferenced ?? true
      },
      roi: activeSlot.roi || null,
      model_detections: {
        bbox: activeSlot.modelBbox || null,
        polygon: activeSlot.modelPolygon || null
      }
    };
  };

  const tiffJson = getTiffJson();
  const tiffJsonString = JSON.stringify(tiffJson, null, 2);

  const handleCopyJson = () => {
    navigator.clipboard?.writeText(tiffJsonString);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="sidebar-drawer-overlay" onClick={onClose}>
      <aside
        className="sidebar-drawer-container dark-scroll"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Detailed Execution Logs and GeoTIFF Inspector"
      >
        {/* Drawer Header */}
        <header className="sidebar-drawer-header">
          <div className="drawer-title-group">
            <div>
              <h2 className="drawer-title">Detailed System Telemetry</h2>
              <span className="drawer-subtitle">Backend Tool Calls & GeoTIFF Inspector</span>
            </div>
          </div>

          <button
            type="button"
            className="drawer-close-btn"
            onClick={onClose}
            title="Close Sidebar (Esc)"
          >
            ✕
          </button>
        </header>

        {/* Navigation Tabs */}
        <nav className="sidebar-drawer-tabs">
          <button
            type="button"
            className={`drawer-tab-btn ${activeTab === 'logs' ? 'active' : ''}`}
            onClick={() => setActiveTab('logs')}
          >
            <span>Step-by-Step Logs</span>
            <span className="tab-count-pill">{executionTrace.length}</span>
          </button>

          <button
            type="button"
            className={`drawer-tab-btn ${activeTab === 'tiff-json' ? 'active' : ''}`}
            onClick={() => setActiveTab('tiff-json')}
          >
            <span>GeoTIFF JSON</span>
            {activeSlot?.originalFilename && (
              <span className="tab-file-pill" title={activeSlot.originalFilename}>
                {selectedTiffSlot === 'B' ? 'T2' : 'T1'}
              </span>
            )}
          </button>
        </nav>

        {/* Tab 1: Step-by-Step Tool Calls & Detailed Execution Logs */}
        {activeTab === 'logs' && (
          <div className="sidebar-tab-content">
            {/* Quick Status Summary Strip */}
            <div className="telemetry-summary-strip">
              <div className="summary-item">
                <span className="summary-label">STATUS</span>
                <span className={`summary-val ${isRunning ? 'val-running' : 'val-complete'}`}>
                  {isRunning ? '● Processing...' : '✓ Complete'}
                </span>
              </div>
              <div className="summary-item">
                <span className="summary-label">STEPS</span>
                <span className="summary-val">{executionTrace.length}</span>
              </div>
              <div className="summary-item">
                <span className="summary-label">TOOL CALLS</span>
                <span className="summary-val">{toolResults.length}</span>
              </div>
              {errors.length > 0 && (
                <div className="summary-item">
                  <span className="summary-label">ERRORS</span>
                  <span className="summary-val val-error">{errors.length}</span>
                </div>
              )}
            </div>

            {/* Backend Tool Calls Section */}
            <div className="sidebar-section">
              <div className="section-header-row">
                <h3 className="sidebar-section-title">Backend Tool Calls</h3>
                <span className="sidebar-section-tag">{toolResults.length} executed</span>
              </div>

              {toolResults.length > 0 ? (
                <div className="tool-calls-stack">
                  {toolResults.map((t, idx) => {
                    const isExpanded = expandedToolIdx === idx;
                    const status = t.result?.status || 'success';
                    const duration = t.duration_ms ? `${Math.round(t.duration_ms)}ms` : null;

                    return (
                      <div key={idx} className={`tool-call-card ${status === 'success' ? 'status-ok' : 'status-fail'}`}>
                        <div
                          className="tool-card-head"
                          onClick={() => setExpandedToolIdx(isExpanded ? null : idx)}
                          title="Click to toggle JSON details"
                        >
                          <div className="tool-card-left">
                            <span className="tool-step-number">#{idx + 1}</span>
                            <span className="tool-canonical-name">{toolLabel(t.tool)}</span>
                            <code className="tool-raw-name">{t.tool}</code>
                          </div>

                          <div className="tool-card-right">
                            {duration && <span className="tool-duration-pill">{duration}</span>}
                            <span className={`tool-status-pill ${status === 'success' ? 'pill-ok' : 'pill-err'}`}>
                              {status === 'success' ? '✓ success' : '✕ error'}
                            </span>
                            <span className="tool-expand-caret">{isExpanded ? '▴' : '▾'}</span>
                          </div>
                        </div>

                        {/* Tool Result Preview */}
                        <div className="tool-card-summary">
                          {t.result?.data?.file_path && (
                            <div className="tool-output-row">
                              <span className="row-key">Product:</span>
                              <span className="row-val code-path">{t.result.data.file_path}</span>
                            </div>
                          )}
                          {t.result?.summary && (
                            <div className="tool-output-row">
                              <span className="row-key">Summary:</span>
                              <span className="row-val">{t.result.summary}</span>
                            </div>
                          )}
                        </div>

                        {/* Expandable Full Tool Result JSON */}
                        {isExpanded && (
                          <div className="tool-card-json-tray">
                            <div className="tray-code-header">
                              <span>Tool Result Payload</span>
                              <button
                                type="button"
                                className="btn-copy-small"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  navigator.clipboard?.writeText(JSON.stringify(t.result, null, 2));
                                }}
                              >
                                Copy Tool JSON
                              </button>
                            </div>
                            <pre className="tool-json-pre dark-scroll">
                              {JSON.stringify(t.result, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="sidebar-empty-box">
                  <span>{isRunning ? 'Orchestrator selecting tool…' : 'No tools required for this query.'}</span>
                </div>
              )}
            </div>

            {/* Complete Chronological Trace Log */}
            <div className="sidebar-section">
              <div className="section-header-row">
                <h3 className="sidebar-section-title">Execution Node Trace</h3>
                <span className="sidebar-section-tag">{executionTrace.length} events</span>
              </div>

              <div className="trace-timeline-list">
                {executionTrace.map((entry, idx) => {
                  const desc = describeStep(entry);
                  const time = entry.timestamp
                    ? new Date(entry.timestamp).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
                    : null;

                  return (
                    <div key={idx} className={`trace-item-row ${desc.ok === false ? 'row-err' : 'row-ok'}`}>
                      <div className="trace-item-time">{time || `#${idx + 1}`}</div>
                      <div className="trace-item-bullet">{desc.ok === false ? '✕' : '✓'}</div>
                      <div className="trace-item-body">
                        <div className="trace-item-main">
                          <span className="trace-node-badge">{entry.node}</span>
                          <span className="trace-label-text">{desc.label}</span>
                        </div>
                        {entry.summary && entry.summary !== 'done' && (
                          <div className="trace-item-summary">{entry.summary}</div>
                        )}
                      </div>
                    </div>
                  );
                })}

                {isRunning && (
                  <div className="trace-item-row row-running">
                    <div className="trace-item-time">now</div>
                    <div className="trace-item-bullet">→</div>
                    <div className="trace-item-body">
                      <span className="trace-node-badge node-active">running</span>
                      <span className="trace-label-text">Processing backend stage...</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: GeoTIFF JSON Inspector */}
        {activeTab === 'tiff-json' && (
          <div className="sidebar-tab-content">
            {/* Pair Slot Switcher if in pair mode */}
            {mode === 'pair' && (
              <div className="tiff-slot-toggle-bar">
                <button
                  type="button"
                  className={`btn-slot-switch ${selectedTiffSlot === 'A' ? 'active' : ''}`}
                  onClick={() => setSelectedTiffSlot('A')}
                >
                  <span className="slot-badge tag-t1">T1</span>
                  <span>Reference TIFF</span>
                  {slotA?.originalFilename && (
                    <span className="slot-fn" title={slotA.originalFilename}>
                      ({slotA.originalFilename})
                    </span>
                  )}
                </button>

                <button
                  type="button"
                  className={`btn-slot-switch ${selectedTiffSlot === 'B' ? 'active' : ''}`}
                  onClick={() => setSelectedTiffSlot('B')}
                >
                  <span className="slot-badge tag-t2">T2</span>
                  <span>Comparison TIFF</span>
                  {slotB?.originalFilename && (
                    <span className="slot-fn" title={slotB.originalFilename}>
                      ({slotB.originalFilename})
                    </span>
                  )}
                </button>
              </div>
            )}

            {/* Quick Metadata Chip Strip */}
            <div className="tiff-quick-meta-strip">
              <div className="meta-chip">
                <span className="chip-key">File</span>
                <span className="chip-val" title={activeSlot?.originalFilename || 'None'}>
                  {activeSlot?.originalFilename || '(No file loaded)'}
                </span>
              </div>
              <div className="meta-chip">
                <span className="chip-key">CRS</span>
                <span className="chip-val">{activeSlot?.info?.crs || 'EPSG:4326'}</span>
              </div>
              <div className="meta-chip">
                <span className="chip-key">Dim</span>
                <span className="chip-val">
                  {activeSlot?.info?.width ? `${activeSlot.info.width}×${activeSlot.info.height}` : '—'}
                </span>
              </div>
              <div className="meta-chip">
                <span className="chip-key">Bands</span>
                <span className="chip-val">{activeSlot?.info?.bandCount ? `${activeSlot.info.bandCount}B` : '—'}</span>
              </div>
            </div>

            {/* JSON Code Viewer Container */}
            <div className="tiff-json-viewer-card">
              <div className="json-viewer-header">
                <div className="json-title-group">
                  <span className="json-symbol">{'{ }'}</span>
                  <span className="json-header-label">
                    GeoTIFF Metadata Profile (JSON)
                  </span>
                </div>

                <button
                  type="button"
                  className="btn-copy-json"
                  onClick={handleCopyJson}
                  title="Copy full JSON metadata to clipboard"
                >
                  {copied ? '✓ Copied!' : 'Copy JSON'}
                </button>
              </div>

              <div className="json-code-canvas dark-scroll">
                <pre className="json-pre-block">
                  <code>{tiffJsonString}</code>
                </pre>
              </div>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
