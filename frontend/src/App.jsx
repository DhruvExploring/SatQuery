import React, { useEffect, useRef, useState } from 'react';
import { checkHealth, fetchModelsStatus, runQueryStream } from './api/satqueryApi';
import ChatMessage from './components/ChatMessage';
import DualRasterSlider from './components/DualRasterSlider';
import ImageSlot from './components/ImageSlot';
import LiveLogsPanel from './components/LiveLogsPanel';
import MapSelector from './components/MapSelector';
import RasterModal from './components/RasterModal';
import SpectralInspector from './components/SpectralInspector';
import WorkflowPresets from './components/WorkflowPresets';
import { roiBoxToBbox } from './lib/geo';
import { inspectGeotiff } from './lib/inspectGeotiff';
import { loadSession, saveSession } from './lib/storage';

const RECAP_PAIR_LIMIT = 2;
const RECAP_ANSWER_CHARS = 320;

const FETCH_IMAGERY_TOOLS = new Set([
  'fetch_optical_imagery',
  'fetch_satellite_imagery',
  'fetch_multispectral_imagery',
  'fetch_sar_imagery',
  'fetch_sar'
]);

const QUICK_PRESETS = [
  { label: '🌿 Crop Canopy & NDVI', query: 'Compute NDVI vegetation canopy vigor and assess biomass density', bbox: [77.10, 28.50, 77.30, 28.70] },
  { label: '🌊 Flood Inundation (SAR)', query: 'Detect flood surface water inundation using cloud-penetrating Sentinel-1 SAR backscatter', bbox: [77.20, 28.58, 77.30, 28.70] },
  { label: '🌲 Amazon Deforestation', query: 'Analyze tropical forest loss between T1 and T2 and generate change mask', bbox: [-63.50, -10.20, -63.20, -9.95] },
  { label: '🔥 Wildfire Severity (dNBR)', query: 'Calculate normalized burn ratio (NBR) and delta NBR to map wildfire burn severity', bbox: [-121.65, 39.70, -121.50, 39.85] },
  { label: '🏔️ Terrain & 2D Slope', query: 'Derive topographical 2D slope in degrees and cross-tabulate against landcover', bbox: [14.95, 37.70, 15.05, 37.80] }
];

function generateId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

function truncate(text, max) {
  if (!text) return '';
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function buildRecap(priorMessages) {
  const pairs = [];
  for (let i = 0; i < priorMessages.length; i++) {
    if (priorMessages[i].role !== 'user') continue;
    const answer = priorMessages[i + 1]?.role === 'assistant' ? priorMessages[i + 1] : null;
    pairs.push({ q: priorMessages[i].text, a: answer?.text || '(no answer)' });
  }
  const recent = pairs.slice(-RECAP_PAIR_LIMIT);
  if (recent.length === 0) return '';
  const lines = recent.map((p) => `Q: ${p.q}\nA: ${truncate(p.a, RECAP_ANSWER_CHARS)}`);
  return `Earlier in this conversation:\n${lines.join('\n\n')}\n\nNow:`;
}

function roiNoteFor(slot, label) {
  if (!slot?.roi) return '';
  return `\n\n(Focus specifically on the highlighted region of ${label}.)`;
}

function boundsToBbox(bounds) {
  if (!bounds) return null;
  return [bounds.min_lon, bounds.min_lat, bounds.max_lon, bounds.max_lat];
}

function bboxObjToArray(bbox) {
  if (!bbox) return null;
  return [bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat];
}

function regionBboxFor(slot) {
  if (!slot?.roi || !slot?.boundsWgs84) return null;
  return bboxObjToArray(roiBoxToBbox(slot.roi, slot.boundsWgs84));
}

function buildFilePayload(mode, slotA, slotB, manualBbox) {
  const payload = {};
  if (manualBbox) {
    payload.bbox = manualBbox;
  }

  if (mode === 'single') {
    if (slotA.uploadedPath) payload.input_file = slotA.uploadedPath;
    const bbox = boundsToBbox(slotA.boundsWgs84);
    if (bbox && !payload.bbox) payload.bbox = bbox;
    const regionBbox = regionBboxFor(slotA);
    if (regionBbox) payload.region_bbox = regionBbox;
    return payload;
  }

  if (slotA.uploadedPath) payload.raster_before_path = slotA.uploadedPath;
  if (slotB.uploadedPath) payload.raster_after_path = slotB.uploadedPath;
  payload.input_file = slotB.uploadedPath || slotA.uploadedPath || undefined;
  const bbox = boundsToBbox(slotB.boundsWgs84) || boundsToBbox(slotA.boundsWgs84);
  if (bbox && !payload.bbox) payload.bbox = bbox;
  const regionBbox = slotB.uploadedPath ? regionBboxFor(slotB) : regionBboxFor(slotA);
  if (regionBbox) payload.region_bbox = regionBbox;
  return payload;
}

function latestFetchedImagery(toolResults) {
  const hits = (toolResults || []).filter(
    (t) => FETCH_IMAGERY_TOOLS.has(t.tool) && t.result?.status === 'success' && t.result?.data?.file_path
  );
  return hits[hits.length - 1] || null;
}

function adoptFetchedImagery(setSlot, path, name) {
  setSlot((prev) => ({
    ...prev,
    uploadedPath: path,
    originalFilename: name,
    boundsWgs84: null,
    info: null,
    roi: null,
    modelBbox: null,
    modelPolygon: null,
    knowledgeBase: null
  }));
  inspectGeotiff(path).then((patch) => {
    if (!patch) return;
    setSlot((prev) => (prev.uploadedPath === path ? { ...prev, ...patch } : prev));
  });
}

const emptySlot = () => ({});

export default function App() {
  const saved = loadSession();

  const [mode, setMode] = useState(saved?.mode || 'single'); // 'single' | 'pair'
  const [slotA, setSlotA] = useState(saved?.slotA || emptySlot());
  const [slotB, setSlotB] = useState(saved?.slotB || emptySlot());
  const [messages, setMessages] = useState(saved?.messages || []);
  const [input, setInput] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [liveSteps, setLiveSteps] = useState([]);
  const [backendUp, setBackendUp] = useState(null);
  const [modelsStatus, setModelsStatus] = useState(null);
  const [activeAoi, setActiveAoi] = useState(null);
  
  // Docked Live Logs state (opens automatically when query entered)
  const [isLogsOpen, setIsLogsOpen] = useState(false);
  const [isMapOpen, setIsMapOpen] = useState(false);
  const [isWorkflowsOpen, setIsWorkflowsOpen] = useState(false);
  const [isSpectralOpen, setIsSpectralOpen] = useState(false);
  const [modalRaster, setModalRaster] = useState(null);
  const [showSlider, setShowSlider] = useState(false);
  const [lastErrors, setLastErrors] = useState([]);

  const bottomRef = useRef(null);

  useEffect(() => {
    let mounted = true;
    checkHealth().then((res) => {
      if (mounted) setBackendUp(res.ok);
    });
    fetchModelsStatus().then((status) => {
      if (mounted && status) setModelsStatus(status);
    });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    saveSession({ mode, slotA, slotB, messages });
  }, [mode, slotA, slotB, messages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, isRunning]);

  const handleResetConversation = () => {
    setMessages([]);
    setLiveSteps([]);
    setLastErrors([]);
  };

  const handleModeChange = (newMode) => {
    if (newMode === mode) return;
    setMode(newMode);
    setSlotA(emptySlot());
    setSlotB(emptySlot());
    setMessages([]);
    setLiveSteps([]);
    setShowSlider(false);
  };

  const handleApplyMapAoi = (bbox) => {
    setActiveAoi(bbox);
    setIsMapOpen(false);
  };

  const handleSelectWorkflow = (wf) => {
    if (wf.mode !== mode) {
      handleModeChange(wf.mode);
    }
    if (wf.bbox) {
      setActiveAoi(wf.bbox);
    }
    setInput(wf.suggestedQuery);
    setIsWorkflowsOpen(false);
  };

  const handleSelectIndex = (idxName) => {
    setInput((prev) => (prev ? `${prev} - compute ${idxName}` : `Compute ${idxName} index`));
    setIsSpectralOpen(false);
  };

  const handleSubmit = async (e) => {
    e?.preventDefault();
    const text = input.trim();
    if (!text || isRunning) return;

    // Automatically open live logs and workflow flow as soon as query is entered!
    setIsLogsOpen(true);

    const attachmentParts = [];
    if (mode === 'single') {
      if (slotA.uploadedPath) attachmentParts.push(`File: ${slotA.originalFilename}`);
    } else {
      if (slotA.uploadedPath) attachmentParts.push(`T1: ${slotA.originalFilename}`);
      if (slotB.uploadedPath) attachmentParts.push(`T2: ${slotB.originalFilename}`);
    }
    if (activeAoi) {
      attachmentParts.push(`AOI: [${activeAoi.join(', ')}]`);
    }

    const attachmentNote = attachmentParts.length > 0 ? attachmentParts.join('  •  ') : null;

    const userMessage = {
      id: generateId(),
      role: 'user',
      text,
      attachmentNote,
      timestamp: Date.now()
    };
    const priorMessages = messages;
    setMessages((m) => [...m, userMessage]);
    setInput('');
    setIsRunning(true);
    setLiveSteps([]);
    setLastErrors([]);

    const recap = buildRecap(priorMessages);
    const roiNote =
      mode === 'single' ? roiNoteFor(slotA, 'image') : roiNoteFor(slotA, 'Image A') + roiNoteFor(slotB, 'Image B');
    const fullQuery = `${recap ? `${recap} ` : ''}${text}${roiNote}`;

    const payload = {
      query: fullQuery,
      ...buildFilePayload(mode, slotA, slotB, activeAoi)
    };

    const { networkError, error, body } = await runQueryStream(payload, {
      onStep: (step) => setLiveSteps((prev) => [...prev, step])
    });

    let assistantMessage;
    if (networkError) {
      const errMsg = error || 'Could not reach the SatQuery API.';
      setLastErrors([errMsg]);
      assistantMessage = {
        id: generateId(),
        role: 'assistant',
        status: 'error',
        text: errMsg,
        toolResults: [],
        executionTrace: [],
        timestamp: Date.now()
      };
    } else {
      const status = String(body?.status || 'error').toLowerCase();
      const kind = status === 'success' || status === 'ok' ? status : status === 'clarify' ? 'clarify' : 'error';
      if (body?.errors && body.errors.length > 0) {
        setLastErrors(body.errors);
      }
      assistantMessage = {
        id: generateId(),
        role: 'assistant',
        status: kind,
        text: body?.final_answer || body?.detail || 'The request could not be processed.',
        toolResults: body?.tool_results || [],
        executionTrace: body?.execution_trace || [],
        timestamp: Date.now()
      };
    }

    setMessages((m) => [...m, assistantMessage]);
    setIsRunning(false);

    if (!networkError) {
      const queriedImagePath = payload.input_file;
      const activeSlot =
        queriedImagePath && queriedImagePath === slotA.uploadedPath
          ? 'A'
          : queriedImagePath && queriedImagePath === slotB.uploadedPath
            ? 'B'
            : null;

      const markResult = (body?.tool_results || []).find(
        (t) =>
          (t.tool === 'mark_region_in_image' || t.tool === 'analyze_imagery_vlm') &&
          (Array.isArray(t.result?.bbox) || Array.isArray(t.result?.polygon))
      );
      const modelBbox = markResult?.result?.bbox || null;
      const modelPolygon = markResult?.result?.polygon || null;

      if (activeSlot === 'A') setSlotA((prev) => ({ ...prev, modelBbox, modelPolygon }));
      else if (activeSlot === 'B') setSlotB((prev) => ({ ...prev, modelBbox, modelPolygon }));

      const latestFetch = latestFetchedImagery(body?.tool_results);
      if (latestFetch) {
        const newPath = latestFetch.result.data.file_path;
        const newName = latestFetch.result.data.file_name || newPath.split('/').pop();
        if (mode === 'single') {
          if (slotA.uploadedPath !== newPath) adoptFetchedImagery(setSlotA, newPath, newName);
        } else if (slotA.uploadedPath !== newPath && slotB.uploadedPath !== newPath) {
          if (!slotA.uploadedPath) adoptFetchedImagery(setSlotA, newPath, newName);
          else if (!slotB.uploadedPath) adoptFetchedImagery(setSlotB, newPath, newName);
        }
      }
    }
  };

  const latestTrace = isRunning
    ? liveSteps
    : [...messages].reverse().find((m) => m.role === 'assistant')?.executionTrace || [];

  const latestToolResults = [...messages].reverse().find((m) => m.role === 'assistant')?.toolResults || [];

  const totalErrorCount = lastErrors.length + (backendUp === false ? 1 : 0);

  return (
    <div className="vpro-app-ambient">
      <div className={`vpro-dual-viewport-container ${isLogsOpen ? 'logs-active' : ''}`}>
        {/* Main Workstation Slate (Resizes & Minimizes Gracefully — NEVER BLURRED) */}
        <div className="vpro-canvas-window">
          {/* Top Header & Search Bar Pill */}
          <header className="vpro-header-bar">
            <div className="vpro-brand">
              <div className="vpro-brand-dot">
                <span className="dot-inner" />
              </div>
              <div>
                <h1 className="vpro-title">SatQuery Vision</h1>
                <span className="vpro-subtitle">Earth Observation & Spatial Intelligence</span>
              </div>
            </div>

            {/* Integrated Actions Pills */}
            <div className="vpro-pill-nav">
              <div className="mode-pill-toggle">
                <button
                  type="button"
                  className={`pill-btn ${mode === 'single' ? 'active' : ''}`}
                  onClick={() => handleModeChange('single')}
                  disabled={isRunning}
                >
                  Single Scene
                </button>
                <button
                  type="button"
                  className={`pill-btn ${mode === 'pair' ? 'active' : ''}`}
                  onClick={() => handleModeChange('pair')}
                  disabled={isRunning}
                >
                  Temporal Pair (T1/T2)
                </button>
              </div>

              <button
                type="button"
                className={`pill-tool-btn ${isMapOpen ? 'active' : ''}`}
                onClick={() => setIsMapOpen((prev) => !prev)}
              >
                <span className="tool-icon">🗺️</span>
                <span>AOI Map {activeAoi ? '✓' : ''}</span>
              </button>

              <button
                type="button"
                className={`pill-tool-btn ${isWorkflowsOpen ? 'active' : ''}`}
                onClick={() => setIsWorkflowsOpen((prev) => !prev)}
              >
                <span className="tool-icon">⚡</span>
                <span>Workflows</span>
              </button>

              <button
                type="button"
                className={`pill-tool-btn ${isSpectralOpen ? 'active' : ''}`}
                onClick={() => setIsSpectralOpen((prev) => !prev)}
              >
                <span className="tool-icon">🔬</span>
                <span>Spectral Lab</span>
              </button>

              {/* Logs & Errors Toggle */}
              <button
                type="button"
                className={`pill-tool-btn logs-toggle-btn ${totalErrorCount > 0 ? 'has-errors' : ''} ${isLogsOpen ? 'active' : ''}`}
                onClick={() => setIsLogsOpen((prev) => !prev)}
                title="Toggle live workflow flow, graph execution steps, and error diagnostics"
              >
                <span className="tool-icon">📋</span>
                <span>Live Logs</span>
                {totalErrorCount > 0 && <span className="pill-error-tag">{totalErrorCount}</span>}
                {isRunning && <span className="pill-running-pulse" />}
              </button>
            </div>

            <div className="vpro-header-right">
              <div className={`connection-status ${backendUp ? 'online' : backendUp === false ? 'offline' : 'pending'}`}>
                <span className="status-indicator" />
                <span>{backendUp ? 'Ready' : backendUp === false ? 'Offline' : 'Connecting'}</span>
              </div>

              {messages.length > 0 && (
                <button
                  type="button"
                  className="btn-icon-soft"
                  onClick={handleResetConversation}
                  title="Clear conversation"
                >
                  ↺
                </button>
              )}
            </div>
          </header>

          {/* Active AOI Banner */}
          {activeAoi && (
            <div className="active-aoi-banner">
              <div className="aoi-banner-content">
                <span className="aoi-pin">📍</span>
                <span className="aoi-label">Active Geographical AOI:</span>
                <code className="aoi-coords">[{activeAoi.join(', ')}]</code>
              </div>
              <button type="button" className="btn-text-clear" onClick={() => setActiveAoi(null)}>
                Clear AOI
              </button>
            </div>
          )}

          {/* Inline Map Accordion */}
          {isMapOpen && (
            <div className="vpro-card inline-map-card">
              <div className="card-top-row">
                <h3>Interactive Satellite AOI Map (HD Imagery)</h3>
                <button type="button" className="btn-close-sm" onClick={() => setIsMapOpen(false)}>
                  ✕ Close Map
                </button>
              </div>
              <MapSelector
                initialBbox={activeAoi || [77.10, 28.50, 77.30, 28.70]}
                onApplyBbox={handleApplyMapAoi}
                onCancel={() => setIsMapOpen(false)}
              />
            </div>
          )}

          {/* Quick Presets Strip */}
          <div className="vpro-presets-strip">
            <span className="presets-label">Quick Scenarios:</span>
            <div className="presets-scroll">
              {QUICK_PRESETS.map((p, idx) => (
                <button
                  key={idx}
                  type="button"
                  className="preset-pill-item"
                  onClick={() => {
                    setInput(p.query);
                    if (p.bbox) setActiveAoi(p.bbox);
                  }}
                  disabled={isRunning}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {/* Main One-Page Split Workspace */}
          <div className="vpro-main-grid">
            {/* Left Column: Raster Slots & Comparison Slider */}
            <div className="vpro-column-left">
              <div className="vpro-card imagery-workspace-card">
                <div className="card-top-row">
                  <h3>Satellite Scene Assets</h3>
                  {mode === 'pair' && slotA.uploadedPath && slotB.uploadedPath && (
                    <button
                      type="button"
                      className={`btn-pill-action ${showSlider ? 'active' : ''}`}
                      onClick={() => setShowSlider((prev) => !prev)}
                    >
                      {showSlider ? 'Show Grid' : '⇄ Compare Swipe'}
                    </button>
                  )}
                </div>

                {mode === 'pair' && showSlider ? (
                  <DualRasterSlider slotA={slotA} slotB={slotB} />
                ) : mode === 'single' ? (
                  <ImageSlot
                    label="Target Satellite Scene (.tif/.tiff)"
                    slot={slotA}
                    onChange={(patch) => setSlotA((prev) => ({ ...prev, ...patch }))}
                    onReset={() => setSlotA(emptySlot())}
                    disabled={isRunning}
                  />
                ) : (
                  <div className="pair-slots-stack">
                    <ImageSlot
                      label="Image A (T1 Reference / Pre-Event)"
                      slot={slotA}
                      onChange={(patch) => setSlotA((prev) => ({ ...prev, ...patch }))}
                      onReset={() => setSlotA(emptySlot())}
                      disabled={isRunning}
                    />
                    <ImageSlot
                      label="Image B (T2 Comparison / Post-Event)"
                      slot={slotB}
                      onChange={(patch) => setSlotB((prev) => ({ ...prev, ...patch }))}
                      onReset={() => setSlotB(emptySlot())}
                      disabled={isRunning}
                    />
                  </div>
                )}
              </div>

              {/* Quick Telemetry Summary Card */}
              <div className="vpro-card telemetry-card">
                <div className="card-top-row">
                  <h4>Engine Telemetry</h4>
                  <button
                    type="button"
                    className="btn-text-link"
                    onClick={() => setIsLogsOpen(true)}
                  >
                    View Live Flow →
                  </button>
                </div>
                <div className="telemetry-grid">
                  <div className="telemetry-item">
                    <span className="tel-label">Orchestrator</span>
                    <span className="tel-val">{modelsStatus?.orchestrator?.provider || 'LangGraph'}</span>
                  </div>
                  <div className="telemetry-item">
                    <span className="tel-label">Vision VLM</span>
                    <span className="tel-val">{modelsStatus?.vision_tool?.provider || 'OpenAI VLM'}</span>
                  </div>
                  <div className="telemetry-item">
                    <span className="tel-label">Steps Run</span>
                    <span className="tel-val">{latestTrace.length} node(s)</span>
                  </div>
                  <div className="telemetry-item">
                    <span className="tel-label">System State</span>
                    <span className={`tel-val ${backendUp ? 'text-green' : 'text-red'}`}>
                      {backendUp ? 'Nominal' : 'Offline'}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Right Column: Natural Language Intelligence & Results */}
            <div className="vpro-column-right">
              <div className="vpro-card chat-workspace-card">
                <div className="chat-messages-container">
                  {messages.length === 0 ? (
                    <div className="chat-welcome-state">
                      <div className="welcome-glow-circle">
                        <span className="welcome-sat-icon">🛰️</span>
                      </div>
                      <h2>Autonomous Earth Observation</h2>
                      <p>
                        Query Sentinel-1 SAR radar, Sentinel-2 optical imagery, 13+ spectral vegetation indices,
                        or landscape terrain slope profiles with autonomous agent toolchains.
                      </p>
                      <div className="welcome-suggestions">
                        <button
                          type="button"
                          className="welcome-chip"
                          onClick={() => setIsMapOpen(true)}
                        >
                          📍 Open Satellite Map
                        </button>
                        <button
                          type="button"
                          className="welcome-chip"
                          onClick={() => setIsWorkflowsOpen(true)}
                        >
                          ⚡ Explore Workflows
                        </button>
                      </div>
                    </div>
                  ) : (
                    messages.map((m) => (
                      <ChatMessage key={m.id} message={m} onOpenRaster={setModalRaster} />
                    ))
                  )}

                  {isRunning && (
                    <div className="chat-row chat-row-assistant">
                      <div className="chat-bubble chat-bubble-assistant live-evaluating">
                        <div className="vpro-typing-dots">
                          <span className="dot" />
                          <span className="dot" />
                          <span className="dot" />
                        </div>
                        <span className="eval-text">Orchestrating remote-sensing tools (check live flow panel →)</span>
                      </div>
                    </div>
                  )}
                  <div ref={bottomRef} />
                </div>

                {/* Bottom Command Pill Form */}
                <form className="vpro-command-dock" onSubmit={handleSubmit}>
                  <div className="vpro-input-pill">
                    <textarea
                      rows={1}
                      placeholder="Ask about imagery, vegetation vigor, flood extent, or temporal changes..."
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          handleSubmit(e);
                        }
                      }}
                      disabled={isRunning}
                    />
                    <button
                      type="submit"
                      className="btn-send-pill"
                      disabled={isRunning || !input.trim()}
                      title="Send Query (Opens Live Workflow Flow)"
                    >
                      <span>Send</span>
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <path d="M5 12h14M12 5l7 7-7 7" />
                      </svg>
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        </div>

        {/* Live Logs & Workflow Flow Docked Alongside Main Page (NEVER BLURS MAIN PAGE) */}
        <LiveLogsPanel
          isOpen={isLogsOpen}
          onClose={() => setIsLogsOpen(false)}
          executionTrace={latestTrace}
          errors={lastErrors}
          rawToolResults={latestToolResults}
          backendUp={backendUp}
          isRunning={isRunning}
          mode={mode}
          activeAoi={activeAoi}
          slotA={slotA}
          slotB={slotB}
          queryText={input || messages.filter((m) => m.role === 'user').slice(-1)[0]?.text || ''}
        />
      </div>

      {/* Fullscreen Workflows Modal */}
      {isWorkflowsOpen && (
        <div className="vpro-modal-backdrop" onClick={() => setIsWorkflowsOpen(false)}>
          <div className="vpro-modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head-row">
              <h3>Geospatial Intelligence Workflows</h3>
              <button type="button" className="btn-close-sm" onClick={() => setIsWorkflowsOpen(false)}>
                ✕
              </button>
            </div>
            <div className="modal-body-scroll">
              <WorkflowPresets onSelectWorkflow={handleSelectWorkflow} />
            </div>
          </div>
        </div>
      )}

      {/* Fullscreen Spectral Lab Modal */}
      {isSpectralOpen && (
        <div className="vpro-modal-backdrop" onClick={() => setIsSpectralOpen(false)}>
          <div className="vpro-modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head-row">
              <h3>Spectral & Telemetry Reference</h3>
              <button type="button" className="btn-close-sm" onClick={() => setIsSpectralOpen(false)}>
                ✕
              </button>
            </div>
            <div className="modal-body-scroll">
              <SpectralInspector onSelectIndex={handleSelectIndex} />
            </div>
          </div>
        </div>
      )}

      {/* High-Resolution Raster Product Modal */}
      {modalRaster && (
        <RasterModal raster={modalRaster} onClose={() => setModalRaster(null)} />
      )}
    </div>
  );
}
