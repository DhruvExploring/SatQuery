import React, { useEffect, useRef, useState } from 'react';
import { checkHealth, fetchModelsStatus, resetConversationApi, runQueryStream } from './api/satqueryApi';
import { deleteUploadedRaster, collectRasterAssets } from './api/rasters';
import ChatMessage from './components/ChatMessage';
import DetailedLogsSidebar from './components/DetailedLogsSidebar';
import ImageHistoryToggle from './components/ImageHistoryToggle';
import ImageSlot from './components/ImageSlot';
import RasterModal from './components/RasterModal';
import SpectralInspector from './components/SpectralInspector';
import TemporalComparisonViewer from './components/TemporalComparisonViewer';
import WorkflowPresets from './components/WorkflowPresets';
import WorkflowTimelinePanel from './components/WorkflowTimelinePanel';
import { roiBoxToBbox } from './lib/geo';
import { inspectGeotiff } from './lib/inspectGeotiff';
import { clearSession, loadSession, saveSession } from './lib/storage';

const RECAP_PAIR_LIMIT = 2;
const RECAP_ANSWER_CHARS = 320;

const FETCH_IMAGERY_TOOLS = new Set([
  'fetch_optical_imagery',
  'fetch_satellite_imagery',
  'fetch_multispectral_imagery',
  'fetch_sar_imagery',
  'fetch_sar'
]);

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

function buildFilePayload(mode, slotA, slotB) {
  const payload = {};

  if (mode === 'single') {
    if (slotA.uploadedPath) payload.input_file = slotA.uploadedPath;
    const bbox = boundsToBbox(slotA.boundsWgs84);
    if (bbox) payload.bbox = bbox;
    const regionBbox = regionBboxFor(slotA);
    if (regionBbox) payload.region_bbox = regionBbox;
    return payload;
  }

  if (slotA.uploadedPath) payload.raster_before_path = slotA.uploadedPath;
  if (slotB.uploadedPath) payload.raster_after_path = slotB.uploadedPath;
  payload.input_file = slotB.uploadedPath || slotA.uploadedPath || undefined;
  const bbox = boundsToBbox(slotB.boundsWgs84) || boundsToBbox(slotA.boundsWgs84);
  if (bbox) payload.bbox = bbox;
  const regionBbox = slotB.uploadedPath ? regionBboxFor(slotB) : regionBboxFor(slotA);
  if (regionBbox) payload.region_bbox = regionBbox;
  return payload;
}

function classifyRaster(tool = '', filePath = '', label = '') {
  const t = String(tool).toLowerCase();
  const p = String(filePath).toLowerCase();
  const l = String(label).toLowerCase();

  if (t.includes('sar') || p.includes('sar') || l.includes('sar')) {
    return { category: 'SAR', shortLabel: 'SAR', badgeLabel: 'GENERATED · SAR' };
  }
  if (t.includes('vegetation') || p.includes('ndvi') || l.includes('ndvi')) {
    return { category: 'NDVI', shortLabel: 'NDVI', badgeLabel: 'GENERATED · NDVI' };
  }
  if (p.includes('ndwi') || l.includes('ndwi') || t.includes('water')) {
    return { category: 'NDWI', shortLabel: 'NDWI', badgeLabel: 'GENERATED · NDWI' };
  }
  if (p.includes('evi') || l.includes('evi')) {
    return { category: 'EVI', shortLabel: 'EVI', badgeLabel: 'GENERATED · EVI' };
  }
  if (t.includes('optical') || t.includes('satellite') || t.includes('multispectral') || p.includes('optical')) {
    return { category: 'Optical', shortLabel: 'Optical', badgeLabel: 'GENERATED · OPTICAL' };
  }
  if (t.includes('change') || p.includes('change') || p.includes('diff') || l.includes('diff')) {
    return { category: 'Change Mask', shortLabel: 'Change', badgeLabel: 'GENERATED · CHANGE' };
  }
  if (t.includes('flood') || p.includes('flood') || l.includes('flood')) {
    return { category: 'Flood', shortLabel: 'Flood', badgeLabel: 'GENERATED · FLOOD' };
  }
  if (t.includes('wildfire') || p.includes('wildfire') || p.includes('nbr')) {
    return { category: 'Wildfire', shortLabel: 'Wildfire', badgeLabel: 'GENERATED · WILDFIRE' };
  }
  if (p.includes('mask') || l.includes('mask')) {
    return { category: 'Mask', shortLabel: 'Mask', badgeLabel: 'GENERATED · MASK' };
  }

  const cleanLabel = (label || '').replace(/_/g, ' ').trim();
  const short = cleanLabel ? cleanLabel.split(' ')[0].toUpperCase() : 'Raster';
  return {
    category: cleanLabel || 'Generated Raster',
    shortLabel: short,
    badgeLabel: `GENERATED · ${short}`
  };
}

const emptySlot = () => ({});

export default function App() {
  const saved = loadSession();
  const initialSlotA = saved?.slotA || emptySlot();
  let initialHistory = Array.isArray(saved?.imageHistory) ? saved.imageHistory : [];
  if (initialHistory.length === 0 && initialSlotA?.uploadedPath) {
    initialHistory = [
      {
        id: 'original',
        type: 'original',
        filename: initialSlotA.originalFilename || initialSlotA.uploadedPath.split('/').pop(),
        filePath: initialSlotA.uploadedPath,
        source: 'upload',
        category: 'Original',
        shortLabel: 'Original',
        badgeLabel: 'ORIGINAL',
        timestamp: Date.now(),
        toolResult: null,
        slotState: { ...initialSlotA }
      }
    ];
  }
  const initialActiveId =
    saved?.activeImageId || (initialHistory.length > 0 ? initialHistory[0].id : null);

  const [mode, setMode] = useState(saved?.mode || 'single'); // 'single' | 'pair'
  const [isMobileViewerCollapsed, setIsMobileViewerCollapsed] = useState(false);
  const [slotA, setSlotA] = useState(initialSlotA);
  const [slotB, setSlotB] = useState(saved?.slotB || emptySlot());
  const [imageHistory, setImageHistory] = useState(initialHistory);
  const [activeImageId, setActiveImageId] = useState(initialActiveId);
  const [messages, setMessages] = useState(saved?.messages || []);
  const [input, setInput] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [liveSteps, setLiveSteps] = useState([]);
  const [backendUp, setBackendUp] = useState(null);
  const [modelsStatus, setModelsStatus] = useState(null);

  // Modals & Popups
  const [isWorkflowsOpen, setIsWorkflowsOpen] = useState(false);
  const [isSpectralOpen, setIsSpectralOpen] = useState(false);
  const [modalRaster, setModalRaster] = useState(null);
  const [isDetailsSidebarOpen, setIsDetailsSidebarOpen] = useState(false);
  const [sidebarInitialTab, setSidebarInitialTab] = useState('logs');
  const [lastErrors, setLastErrors] = useState([]);

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const abortControllerRef = useRef(null);
  const queryIdRef = useRef(0);

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
    saveSession({ mode, slotA, slotB, messages, imageHistory, activeImageId });
  }, [mode, slotA, slotB, messages, imageHistory, activeImageId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isRunning]);

  // Esc key closes modals
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        setIsWorkflowsOpen(false);
        setIsSpectralOpen(false);
        setModalRaster(null);
        setIsDetailsSidebarOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleSelectImage = (id) => {
    if (id === activeImageId) return;
    const target = imageHistory.find((item) => item.id === id);
    if (!target) return;

    // Cache current slotA state into current active item before switching
    setImageHistory((prevHist) =>
      prevHist.map((item) =>
        item.id === activeImageId ? { ...item, slotState: { ...slotA } } : item
      )
    );

    setActiveImageId(id);

    if (target.slotState) {
      setSlotA(target.slotState);
    } else {
      const fallback = {
        uploadedPath: target.filePath,
        originalFilename: target.filename || target.filePath.split('/').pop(),
        boundsWgs84: null,
        info: null,
        roi: null,
        modelBbox: null,
        modelPolygon: null,
        knowledgeBase: null,
        isUserUpload: target.type === 'original'
      };
      setSlotA(fallback);
      inspectGeotiff(target.filePath).then((patch) => {
        if (!patch) return;
        setSlotA((curr) => (curr.uploadedPath === target.filePath ? { ...curr, ...patch } : curr));
        setImageHistory((prevHist) =>
          prevHist.map((it) =>
            it.id === id ? { ...it, slotState: { ...fallback, ...patch } } : it
          )
        );
      });
    }
  };

  const handleRemoveImage = (id, e) => {
    e?.stopPropagation();
    const itemToRemove = imageHistory.find((item) => item.id === id);
    if (!itemToRemove) return;

    const path = itemToRemove.filePath;
    if (path && typeof path === 'string' && path.startsWith('uploads/')) {
      deleteUploadedRaster(path).catch((err) => {
        console.warn('Could not delete temporary raster on server:', err);
      });
    }

    const newHistory = imageHistory.filter((item) => item.id !== id);
    setImageHistory(newHistory);

    if (activeImageId === id) {
      if (newHistory.length > 0) {
        const nextActive =
          newHistory.find((item) => item.type === 'original') || newHistory[newHistory.length - 1];
        setActiveImageId(nextActive.id);
        setSlotA(
          nextActive.slotState || {
            uploadedPath: nextActive.filePath,
            originalFilename: nextActive.filename,
            boundsWgs84: null,
            info: null,
            roi: null
          }
        );
      } else {
        setActiveImageId(null);
        setSlotA(emptySlot());
      }
    }
  };

  const handleSlotAChange = (patch) => {
    setSlotA((prev) => {
      const next = { ...prev, ...patch };

      if (next.uploadedPath) {
        setImageHistory((prevHist) => {
          if (patch.isUserUpload) {
            const origItem = {
              id: 'original',
              type: 'original',
              filename: next.originalFilename || next.uploadedPath.split('/').pop(),
              filePath: next.uploadedPath,
              source: 'upload',
              category: 'Original',
              shortLabel: 'Original',
              badgeLabel: 'ORIGINAL',
              timestamp: Date.now(),
              toolResult: null,
              slotState: next
            };
            const withoutOrig = prevHist.filter((item) => item.id !== 'original');
            return [origItem, ...withoutOrig];
          }

          return prevHist.map((item) => {
            if (item.id === activeImageId) {
              return {
                ...item,
                slotState: next,
                filename: next.originalFilename || item.filename,
                filePath: next.uploadedPath || item.filePath
              };
            }
            return item;
          });
        });

        if (patch.isUserUpload) {
          setActiveImageId('original');
        }
      }

      return next;
    });
  };

  const handleRemoveSlot = (slotKey) => {
    if (slotKey === 'A') {
      if (activeImageId) {
        handleRemoveImage(activeImageId);
      } else {
        const path = slotA?.uploadedPath;
        if (path && typeof path === 'string' && path.startsWith('uploads/')) {
          deleteUploadedRaster(path).catch((err) => {
            console.warn('Could not delete temporary raster on server:', err);
          });
        }
        setSlotA(emptySlot());
      }
    } else {
      const path = slotB?.uploadedPath;
      if (path && typeof path === 'string' && path.startsWith('uploads/')) {
        deleteUploadedRaster(path).catch((err) => {
          console.warn('Could not delete temporary raster on server:', err);
        });
      }
      setSlotB(emptySlot());
    }
  };

  const handleNewConversation = async () => {
    // 1. Cancel in-flight query and increment query ID so late responses are discarded
    queryIdRef.current += 1;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    // 2. Identify active temporary uploaded files across slots and image history
    const allPaths = [
      slotA?.uploadedPath,
      slotB?.uploadedPath,
      ...imageHistory.map((it) => it.filePath)
    ];
    const tempFiles = Array.from(
      new Set(allPaths.filter((p) => typeof p === 'string' && p.startsWith('uploads/')))
    );

    // 3. Reset all conversation, TIFF, metadata, results, and telemetry states
    setMessages([]);
    setLiveSteps([]);
    setLastErrors([]);
    setInput('');
    setIsRunning(false);
    setSlotA(emptySlot());
    setSlotB(emptySlot());
    setImageHistory([]);
    setActiveImageId(null);
    setMode('single');
    setModalRaster(null);
    setIsWorkflowsOpen(false);
    setIsSpectralOpen(false);
    setIsDetailsSidebarOpen(false);

    // 4. Clear temporary persisted storage
    clearSession();

    // 5. Synchronize reset with backend
    try {
      await resetConversationApi({ tempFiles });
    } catch (err) {
      console.warn('Backend reset notification failed:', err);
    }
  };

  const handleModeChange = (newMode) => {
    if (newMode === mode) return;
    queryIdRef.current += 1;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setMode(newMode);
  };

  const handleSelectWorkflow = (wf) => {
    if (wf.mode && wf.mode !== mode) {
      handleModeChange(wf.mode);
    }
    setInput(wf.suggestedQuery);
    setIsWorkflowsOpen(false);
    inputRef.current?.focus();
  };

  const handleSelectIndex = (idxName) => {
    setInput((prev) => (prev ? `${prev} - compute ${idxName}` : `Compute ${idxName} index`));
    setIsSpectralOpen(false);
    inputRef.current?.focus();
  };

  const handleSubmit = async (e) => {
    e?.preventDefault();
    const text = input.trim();
    if (!text || isRunning) return;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;
    const currentQueryId = ++queryIdRef.current;

    const userMessage = {
      id: generateId(),
      role: 'user',
      text,
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
      ...buildFilePayload(mode, slotA, slotB)
    };

    const { networkError, error, body, aborted } = await runQueryStream(payload, {
      signal: controller.signal,
      onStep: (step) => {
        if (queryIdRef.current === currentQueryId && !controller.signal.aborted) {
          setLiveSteps((prev) => [...prev, step]);
        }
      }
    });

    // Guard: If conversation was reset or aborted, ignore old responses completely
    if (queryIdRef.current !== currentQueryId || aborted || controller.signal.aborted) {
      return;
    }

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

    if (!networkError && queryIdRef.current === currentQueryId) {
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

      if (activeSlot === 'A') {
        setSlotA((prev) => ({ ...prev, modelBbox, modelPolygon }));
        setImageHistory((prevHist) =>
          prevHist.map((item) =>
            item.id === activeImageId
              ? { ...item, slotState: { ...item.slotState, modelBbox, modelPolygon } }
              : item
          )
        );
      } else if (activeSlot === 'B') {
        setSlotB((prev) => ({ ...prev, modelBbox, modelPolygon }));
      }

      // Collect any newly generated raster assets across all executed tools
      const rasterAssets = collectRasterAssets(body?.tool_results);
      if (rasterAssets.length > 0) {
        // Collect existing filePaths to avoid duplicates
        const existingPaths = new Set(imageHistory.map((it) => it.filePath));
        const origHist = imageHistory.find((it) => it.type === 'original');
        if (origHist?.filePath) existingPaths.add(origHist.filePath);

        const newItems = [];
        rasterAssets.forEach((asset, idx) => {
          if (!asset.path || existingPaths.has(asset.path)) return;
          existingPaths.add(asset.path);

          const classification = classifyRaster(asset.tool, asset.path, asset.label);
          const newId = `gen-${Date.now()}-${idx}`;
          const newHistItem = {
            id: newId,
            type: 'generated',
            filename: asset.path.split('/').pop(),
            filePath: asset.path,
            source: asset.tool || 'generated',
            category: classification.category,
            shortLabel: classification.shortLabel,
            badgeLabel: classification.badgeLabel,
            timestamp: Date.now(),
            toolResult: (body?.tool_results || []).find((t) => t.tool === asset.tool) || null,
            slotState: {
              uploadedPath: asset.path,
              originalFilename: asset.path.split('/').pop(),
              boundsWgs84: slotA.boundsWgs84 || null,
              info: null,
              roi: null,
              modelBbox: null,
              modelPolygon: null,
              knowledgeBase: null,
              isUserUpload: false
            }
          };

          // Trigger asynchronous inspection for new raster to populate bounds and metadata
          inspectGeotiff(asset.path).then((patch) => {
            if (!patch) return;
            setImageHistory((prevHist) =>
              prevHist.map((it) =>
                it.id === newId ? { ...it, slotState: { ...it.slotState, ...patch } } : it
              )
            );
            setSlotA((curr) => (curr.uploadedPath === asset.path ? { ...curr, ...patch } : curr));
          });

          newItems.push(newHistItem);
        });

        if (newItems.length > 0) {
          setImageHistory((prev) => [...prev, ...newItems]);
          // Automatically switch left display to latest generated image
          const latestItem = newItems[newItems.length - 1];
          setActiveImageId(latestItem.id);
          setSlotA(latestItem.slotState);
        }
      }
    }
  };

  const latestTrace = isRunning
    ? liveSteps
    : [...messages].reverse().find((m) => m.role === 'assistant')?.executionTrace || [];

  const latestToolResults = [...messages].reverse().find((m) => m.role === 'assistant')?.toolResults || [];
  const totalErrorCount = lastErrors.length + (backendUp === false ? 1 : 0);

  const activeHistoryItem =
    imageHistory.find((item) => item.id === activeImageId) ||
    imageHistory.find((item) => item.type === 'original') ||
    imageHistory[0] ||
    null;

  return (
    <div className="vpro-app-ambient">
      <div className="vpro-canvas-window">
        {/* Claymorphic Header */}
        <header className="vpro-header-bar">
          <div className="vpro-brand">
            <div className="vpro-brand-dot">
              <span className="dot-inner" />
            </div>
            <div>
              <h1 className="vpro-title">SatQuery AI</h1>
              <span className="vpro-subtitle">Earth Observation & Spatial Intelligence</span>
            </div>
          </div>

          {/* Claymorphic Sunken Capsule Toolbar */}
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
              className={`pill-tool-btn ${isWorkflowsOpen ? 'active' : ''}`}
              onClick={() => setIsWorkflowsOpen(true)}
            >
              <span>Workflows</span>
            </button>

            <button
              type="button"
              className={`pill-tool-btn ${isSpectralOpen ? 'active' : ''}`}
              onClick={() => setIsSpectralOpen(true)}
            >
              <span>Spectral Lab</span>
            </button>
          </div>

          <div className="vpro-header-right">
            <button
              type="button"
              className="btn-new-convo"
              onClick={handleNewConversation}
              title="Start a new conversation and reset workspace"
              id="btn-new-conversation"
            >
              <span className="plus-icon">＋</span>
              <span>New Conversation</span>
            </button>

            <div className={`connection-status ${backendUp ? 'online' : backendUp === false ? 'offline' : 'pending'}`}>
              <span className="status-indicator" />
              <span>{backendUp ? 'Ready' : backendUp === false ? 'Offline' : 'Connecting'}</span>
            </div>
          </div>
        </header>

        {/* Main Workstation Viewport: Responsive 2-Pane Architecture (Desktop = Side-by-Side, Mobile = Stacked Split) */}
        <div className="vpro-main-grid">
          {/* Left / Top Column: Satellite Visualizer (Always visible in mobile view) */}
          <div className={`vpro-column-left ${isMobileViewerCollapsed ? 'mobile-collapsed' : ''}`}>
            <div className="vpro-card imagery-workspace-card">
              <div className="card-top-row">
                <div className="card-top-title-group">
                  <h3>Satellite Scene Assets</h3>
                  {activeHistoryItem?.badgeLabel ? (
                    <span className="mobile-active-fn-badge" title={activeHistoryItem.filename}>
                      {activeHistoryItem.badgeLabel}
                    </span>
                  ) : slotA.uploadedPath ? (
                    <span className="mobile-active-fn-badge" title={slotA.originalFilename}>
                      {slotA.originalFilename}
                    </span>
                  ) : null}
                </div>

                <div className="card-top-actions">
                  {(slotA.uploadedPath || slotB.uploadedPath) && (
                    <button
                      type="button"
                      className="btn-pill-action"
                      onClick={() => {
                        setSidebarInitialTab('tiff-json');
                        setIsDetailsSidebarOpen(true);
                      }}
                      title="Inspect GeoTIFF Metadata & JSON Profile"
                    >
                      <span>{'{ }'} GeoTIFF JSON</span>
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn-collapse-viewer"
                    onClick={() => setIsMobileViewerCollapsed((prev) => !prev)}
                    title={isMobileViewerCollapsed ? 'Expand Satellite Scene' : 'Collapse Satellite Scene'}
                    aria-expanded={!isMobileViewerCollapsed}
                  >
                    <span>{isMobileViewerCollapsed ? '▼ Show Image' : '▲ Hide Image'}</span>
                  </button>
                </div>
              </div>

              <div className="visualizer-content-stage">
                {mode === 'single' && imageHistory.length > 0 && (
                  <ImageHistoryToggle
                    imageHistory={imageHistory}
                    activeImageId={activeImageId}
                    onSelectImage={handleSelectImage}
                    onRemoveImage={handleRemoveImage}
                    disabled={isRunning}
                  />
                )}
                {mode === 'single' ? (
                  <ImageSlot
                    label="Target Satellite Scene (.tif/.tiff)"
                    badgeLabel={
                      activeHistoryItem?.badgeLabel ||
                      (slotA.uploadedPath ? 'ORIGINAL' : null)
                    }
                    slot={slotA}
                    onChange={handleSlotAChange}
                    onReset={() => handleRemoveSlot('A')}
                    disabled={isRunning}
                    onOpenModal={setModalRaster}
                  />
                ) : (
                  <TemporalComparisonViewer
                    slotA={slotA}
                    slotB={slotB}
                    onChangeA={(patch) => setSlotA((prev) => ({ ...prev, ...patch }))}
                    onChangeB={(patch) => setSlotB((prev) => ({ ...prev, ...patch }))}
                    onRemoveA={() => handleRemoveSlot('A')}
                    onRemoveB={() => handleRemoveSlot('B')}
                    onOpenModal={setModalRaster}
                    disabled={isRunning}
                  />
                )}
              </div>
            </div>
          </div>

          {/* Right / Bottom Column: AI Chat & Reasoning Stream */}
          <div className="vpro-column-right">
            <div className="vpro-card chat-workspace-card">
              <div className="chat-messages-container">
                {messages.length === 0 ? (
                  <div className="chat-empty-ready">
                    <div className="ready-indicator-badge">
                      <span className="ready-beacon-pulse" />
                      <span className="ready-label">WORKSTATION READY</span>
                    </div>
                    <p className="ready-subtext">
                      Upload a satellite GeoTIFF (.tif/.tiff) or type an Earth Observation query below to deploy autonomous multi-sensor tools.
                    </p>
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
                      <span className="eval-text">Orchestrating remote-sensing tools…</span>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Compact Professional Workflow Timeline & Execution Events */}
              <WorkflowTimelinePanel
                executionTrace={latestTrace}
                toolResults={latestToolResults}
                isRunning={isRunning}
                errors={lastErrors}
                backendUp={backendUp}
                onOpenDetails={() => {
                  setSidebarInitialTab('logs');
                  setIsDetailsSidebarOpen(true);
                }}
              />

              {/* Bottom Command Form - Fixed at Bottom */}
              <form className="vpro-command-dock" onSubmit={handleSubmit}>
                <div className="vpro-input-pill">
                  <textarea
                    ref={inputRef}
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
                    title="Send Query"
                  >
                    <span>Send</span>
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <path d="M5 12h14M12 5l7 7-7 7" />
                    </svg>
                  </button>
                </div>
                <div className="composer-hints-row">
                  <span className="composer-hint-item">↵ Enter to send</span>
                  <span className="composer-hint-item">Shift + ↵ for newline</span>
                  {slotA.uploadedPath && (
                    <span className="composer-hint-target">
                      Active: <code>{slotA.originalFilename}</code>
                    </span>
                  )}
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>

      {/* Workflows Modal */}
      {isWorkflowsOpen && (
        <div className="vpro-modal-backdrop" onClick={() => setIsWorkflowsOpen(false)}>
          <div className="vpro-modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head-row">
              <h3>Autonomous Geospatial Workflows</h3>
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

      {/* Spectral Lab Modal */}
      {isSpectralOpen && (
        <div className="vpro-modal-backdrop" onClick={() => setIsSpectralOpen(false)}>
          <div className="vpro-modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head-row">
              <h3>Spectral Indices & Biophysical Reference</h3>
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

      {/* High-Resolution Raster Modal */}
      {modalRaster && (
        <RasterModal raster={modalRaster} onClose={() => setModalRaster(null)} />
      )}

      {/* Detailed System Telemetry & GeoTIFF Inspector Sidebar Drawer */}
      <DetailedLogsSidebar
        isOpen={isDetailsSidebarOpen}
        onClose={() => setIsDetailsSidebarOpen(false)}
        executionTrace={latestTrace}
        toolResults={latestToolResults}
        isRunning={isRunning}
        errors={lastErrors}
        slotA={slotA}
        slotB={slotB}
        mode={mode}
        initialTab={sidebarInitialTab}
      />
    </div>
  );
}
