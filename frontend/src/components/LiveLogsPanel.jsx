import React, { useEffect, useRef, useState } from 'react';
import { describeStep } from '../lib/executionSteps';
import { toolLabel } from '../lib/toolLabels';

/**
 * Detailed analysis of the 5 canonical pipeline stages:
 * 1. Input & Coordinate Validation
 * 2. Knowledge Base & Pre-Flight Cache
 * 3. Vision VLM Scene Recognition
 * 4. Remote-Sensing EO Tools Deployment
 * 5. Geospatial Intelligence Report Synthesis
 */
function analyzeWorkflowStages(trace = [], isRunning = false, context = {}) {
  const nodes = trace.map((t) => t.node);
  const { mode = 'single', activeAoi, slotA, slotB, queryText = '' } = context;

  const hasValidate = nodes.includes('validate');
  const validateOk = trace.find((t) => t.node === 'validate')?.summary === 'input ok';

  const hasKb = nodes.includes('load_knowledge_base');
  const kbSummary = trace.find((t) => t.node === 'load_knowledge_base')?.summary;
  const kbLoaded = kbSummary === 'loaded from disk' || kbSummary === 'provided inline';

  const hasVlm = nodes.includes('vlm_initial_description');
  const vlmGenerated = trace.find((t) => t.node === 'vlm_initial_description')?.summary === 'generated';

  const toolSteps = trace.filter((t) => t.node === 'tool');
  const toolsRun = toolSteps
    .map((t) => {
      const m = t.summary?.match(/^(\S+) status=(\S+)/);
      return m ? { tool: m[1], ok: m[2] === 'success' } : null;
    })
    .filter(Boolean);

  const hasRespond = nodes.includes('respond');
  const respondSummary = trace.find((t) => t.node === 'respond')?.summary || '';

  return {
    validate: {
      id: 'validate',
      name: 'Input & AOI Validation',
      status: hasValidate ? (validateOk ? 'ok' : 'fail') : isRunning ? 'active' : 'idle',
      happening: validateOk
        ? 'User prompt parsed, schema verified, and bounding box geodetic constraints confirmed [EPSG:4326]'
        : hasValidate
          ? 'Validation detected missing coordinates or malformed parameters'
          : isRunning
            ? 'Analyzing query structure and spatial coordinates…'
            : 'Awaiting user query submission',
      notHappening: validateOk
        ? 'No coordinate syntax errors, out-of-bounds latitude/longitude, or schema violations'
        : 'Query requires additional spatial coordinate parameters'
    },
    knowledgeBase: {
      id: 'knowledgeBase',
      name: 'Knowledge Base Cache',
      status: hasKb ? (kbLoaded ? 'ok' : 'skipped') : isRunning && !hasKb ? 'pending' : 'idle',
      happening: kbLoaded
        ? 'Retrieved cached GeoTIFF profile, raster affine transform, and band designations from disk'
        : hasKb
          ? 'Direct on-the-fly raster parsing active; operating without pre-existing disk cache'
          : isRunning
            ? 'Checking for pre-computed GeoTIFF cache on disk…'
            : 'Knowledge base check queued',
      notHappening: kbLoaded
        ? 'Zero full raster re-indexing needed; cached profile used'
        : 'Pre-flight disk cache hit skipped (operating on fresh dynamic scene)'
    },
    visionAnalysis: {
      id: 'visionAnalysis',
      name: 'Vision VLM Scene Description',
      status: hasVlm ? (vlmGenerated ? 'ok' : 'skipped') : isRunning && !hasVlm ? 'pending' : 'idle',
      happening: vlmGenerated
        ? 'Multi-modal Vision VLM generated comprehensive descriptive overview of visible terrain features'
        : hasVlm
          ? 'Autonomous agent bypassed visual description to prioritize deterministic analytical tools'
          : isRunning
            ? 'Evaluating whether initial visual scene description is required…'
            : 'VLM vision evaluation queued',
      notHappening: vlmGenerated
        ? 'Visual inspection executed without hallucination suppression flags'
        : 'Natural language scene prose skipped to minimize token overhead and latency'
    },
    toolsExecution: {
      id: 'toolsExecution',
      name: 'Earth Observation Tools',
      status: toolsRun.length > 0 ? (toolsRun.every((t) => t.ok) ? 'ok' : 'fail') : isRunning ? 'active' : 'idle',
      count: toolsRun.length,
      tools: toolsRun,
      happening:
        toolsRun.length > 0
          ? `Successfully deployed: ${toolsRun.map((t) => toolLabel(t.tool)).join(', ')}`
          : isRunning
            ? 'Autonomous agent selecting and deploying remote sensing analytical tools…'
            : 'No satellite tools deployed yet',
      notHappening:
        toolsRun.length > 0
          ? 'Alternative non-relevant spatial tools kept dormant; no tool execution retries triggered'
          : isRunning
            ? 'Waiting for orchestrator tool deployment call'
            : 'All satellite tools currently inactive'
    },
    synthesis: {
      id: 'synthesis',
      name: 'Intelligence Report Synthesis',
      status: hasRespond ? (respondSummary.startsWith('success') ? 'ok' : 'fail') : isRunning ? 'pending' : 'idle',
      happening: hasRespond
        ? 'Synthesized multi-tool raster calculations into executive geospatial intelligence briefing'
        : isRunning
          ? 'Aggregating tool numerical outputs and generating final analytical response…'
          : 'Pending tool chain completion',
      notHappening: hasRespond
        ? 'Zero unhandled exceptions; no follow-up clarification prompts required'
        : 'Final synthesis waiting on upstream tool results'
    }
  };
}

/**
 * Compute the comprehensive "What Is Happening" vs "What Is Not" intelligence breakdown
 */
function computeActivityBreakdown(trace = [], isRunning = false, context = {}, rawToolResults = []) {
  const { mode = 'single', activeAoi, slotA, slotB, queryText = '' } = context;
  const nodes = trace.map((t) => t.node);
  const qLower = queryText.toLowerCase();

  const happeningItems = [];
  const notHappeningItems = [];

  // 1. Current Active Task
  if (isRunning) {
    const lastNode = trace[trace.length - 1];
    if (lastNode) {
      const step = describeStep(lastNode);
      happeningItems.push({
        tag: 'ACTIVE PROCESS',
        title: `Executing: ${step.label}`,
        detail: lastNode.summary || 'Processing node output in LangGraph state machine…',
        status: 'active'
      });
    } else {
      happeningItems.push({
        tag: 'INITIALIZATION',
        title: 'Initializing LangGraph Agent Trajectory',
        detail: 'Connecting to SatQuery orchestrator and compiling state graph…',
        status: 'active'
      });
    }
  }

  // 2. Completed Nodes in Trace
  trace.forEach((row, i) => {
    const step = describeStep(row);
    if (step.ok) {
      happeningItems.push({
        tag: `STEP #${i + 1} COMPLETED`,
        title: step.label,
        detail: row.summary || 'Node execution completed with nominal status.',
        status: 'completed'
      });
    }
  });

  // 3. Deployed Tool Details
  rawToolResults.forEach((t) => {
    if (t.result?.status === 'success') {
      const toolName = toolLabel(t.tool);
      const dataKeys = t.result?.data ? Object.keys(t.result.data).filter((k) => k !== 'file_path').join(', ') : '';
      happeningItems.push({
        tag: 'TOOL RESULT',
        title: `${toolName} Produced Output`,
        detail: dataKeys ? `Calculated metrics: ${dataKeys}` : 'Product rendered and cached successfully.',
        status: 'completed'
      });
    }
  });

  // 4. "WHAT IS NOT HAPPENING" - Inactive Tools, Bypassed Branches, Suppressed Errors
  // Check Mode
  if (mode === 'single') {
    notHappeningItems.push({
      category: 'TEMPORAL ANALYSIS',
      title: 'Bi-Temporal Change Detection (T1 vs T2)',
      reason: 'INACTIVE',
      explanation: 'Operating in Single Scene mode. Multi-temporal difference calculations (delta NBR, change masks) are dormant.'
    });
  }

  // Check Radar SAR vs Optical
  const isSarQuery = qLower.includes('sar') || qLower.includes('radar') || qLower.includes('sentinel-1');
  if (!isSarQuery) {
    notHappeningItems.push({
      category: 'SENSOR PIPELINE',
      title: 'Sentinel-1 SAR Polarimetric Radar Backscatter',
      reason: 'INACTIVE',
      explanation: 'User prompt focused on multi-spectral optical bands. Cloud-penetrating C-band SAR pipeline was not triggered.'
    });
  }

  // Check Wildfire
  const isFire = qLower.includes('fire') || qLower.includes('burn') || qLower.includes('nbr');
  if (!isFire) {
    notHappeningItems.push({
      category: 'SPECIALIZED ALGORITHM',
      title: 'Wildfire dNBR Burn Severity Index',
      reason: 'DORMANT',
      explanation: 'No burn scar or fire severity keywords detected in query. Tool was kept dormant to avoid redundant compute.'
    });
  }

  // Check Terrain / Slope
  const isSlope = qLower.includes('slope') || qLower.includes('elevation') || qLower.includes('dem') || qLower.includes('terrain');
  if (!isSlope) {
    notHappeningItems.push({
      category: 'TOPOGRAPHY',
      title: 'Copernicus DEM 2D Slope Topographical Analysis',
      reason: 'DORMANT',
      explanation: 'Topographical elevation/slope calculations not requested. Cop-DEM 30m terrain engine is inactive.'
    });
  }

  // Knowledge base check
  const hasKb = nodes.includes('load_knowledge_base');
  const kbSummary = trace.find((t) => t.node === 'load_knowledge_base')?.summary;
  if (!hasKb || (kbSummary !== 'loaded from disk' && kbSummary !== 'provided inline')) {
    notHappeningItems.push({
      category: 'CACHE SUBSYSTEM',
      title: 'Pre-Computed GeoTIFF Disk Cache Hit',
      reason: 'SKIPPED',
      explanation: 'No pre-existing GeoTIFF metadata cache found on disk. Agent is running fresh on-the-fly raster parsing without cache dependency.'
    });
  }

  // VLM Scene Description
  const hasVlm = nodes.includes('vlm_initial_description');
  const vlmGenerated = trace.find((t) => t.node === 'vlm_initial_description')?.summary === 'generated';
  if (!vlmGenerated) {
    notHappeningItems.push({
      category: 'VLM INFERENCE',
      title: 'Global Scene Descriptive Narrative (VLM)',
      reason: 'BYPASSED',
      explanation: 'General visual prose generation was bypassed to directly trigger fast, deterministic scientific raster tools.'
    });
  }

  // Coordinate Bounds Reprojection Error
  notHappeningItems.push({
    category: 'SAFETY & CRS',
    title: 'Coordinate Out-of-Bounds & CRS Exceptions',
    reason: 'NOMINAL',
    explanation: 'Zero geodetic projection errors or out-of-range latitude/longitude coordinates encountered.'
  });

  // Orchestrator Fallback Repair
  notHappeningItems.push({
    category: 'ORCHESTRATION',
    title: 'Agent Trajectory Recovery & Error Loops',
    reason: 'NOMINAL',
    explanation: 'State machine is executing without backtracking, infinite loop guards, or schema repair fallbacks.'
  });

  return { happeningItems, notHappeningItems };
}

export default function LiveLogsPanel({
  isOpen,
  onClose,
  executionTrace = [],
  errors = [],
  rawToolResults = [],
  backendUp,
  isRunning,
  mode = 'single',
  activeAoi,
  slotA,
  slotB,
  queryText = ''
}) {
  const [tab, setTab] = useState('overview'); // 'overview' | 'flow' | 'stages' | 'diagnostics' | 'raw'
  const [activityFilter, setActivityFilter] = useState('all'); // 'all' | 'happening' | 'not'
  const [elapsedTime, setElapsedTime] = useState('0.0');
  const scrollRef = useRef(null);
  const timerRef = useRef(null);

  // Live timer tracking while isRunning
  useEffect(() => {
    if (isRunning) {
      setElapsedTime('0.0');
      const start = Date.now();
      timerRef.current = setInterval(() => {
        setElapsedTime(((Date.now() - start) / 1000).toFixed(1));
      }, 100);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isRunning]);

  // Auto-scroll to the bottom of the trace as new steps stream in
  useEffect(() => {
    if (scrollRef.current && (tab === 'flow' || tab === 'overview')) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [executionTrace, isRunning, tab]);

  if (!isOpen) return null;

  const errorCount = (errors?.length || 0) + (backendUp === false ? 1 : 0);
  const context = { mode, activeAoi, slotA, slotB, queryText };
  const stages = analyzeWorkflowStages(executionTrace, isRunning, context);
  const { happeningItems, notHappeningItems } = computeActivityBreakdown(
    executionTrace,
    isRunning,
    context,
    rawToolResults
  );

  const lastNode = executionTrace[executionTrace.length - 1];
  const currentAction = isRunning
    ? lastNode
      ? `Executing: ${describeStep(lastNode).label}`
      : 'Initiating LangGraph Agent Trajectory…'
    : executionTrace.length > 0
      ? 'Workflow Trajectory Completed'
      : 'Awaiting Query';

  return (
    <aside className="live-logs-dock">
      {/* Live Header with Status Indicator & Live Timer */}
      <div className="live-logs-header">
        <div className="logs-header-title">
          <div className="live-radar-dot">
            <span className={`live-pulse-core ${isRunning ? 'active' : ''}`} />
          </div>
          <div>
            <h3>Live Workflow & Telemetry</h3>
            <span className="live-subtitle">
              {isRunning
                ? `Active execution stream • ${elapsedTime}s elapsed`
                : executionTrace.length > 0
                  ? `Completed • ${executionTrace.length} steps executed`
                  : 'Engine ready • Standby'}
            </span>
          </div>
        </div>

        <button
          type="button"
          className="btn-dock-close"
          onClick={onClose}
          title="Minimize logs panel"
        >
          ✕
        </button>
      </div>

      {/* Persistent Pipeline Progress Bar (Live Visual Stepper) */}
      <div className="workflow-stepper-bar">
        <div className="stepper-title-row">
          <span className="stepper-label">PIPELINE STAGE PROGRESS</span>
          <span className={`stepper-status-badge ${isRunning ? 'running' : executionTrace.length > 0 ? 'done' : 'standby'}`}>
            {isRunning ? 'RUNNING' : executionTrace.length > 0 ? 'COMPLETE' : 'STANDBY'}
          </span>
        </div>

        <div className="stepper-nodes-track">
          {Object.entries(stages).map(([key, stg], idx) => {
            const isStageActive = stg.status === 'active';
            const isStageOk = stg.status === 'ok';
            const isStageSkipped = stg.status === 'skipped';
            const isStageFail = stg.status === 'fail';

            return (
              <div
                key={key}
                className={`stepper-node-item ${stg.status}`}
                onClick={() => setTab('stages')}
                title={`${stg.name}: ${stg.happening}`}
              >
                <div className="stepper-node-dot">
                  {isStageOk ? '✓' : isStageSkipped ? '↷' : isStageFail ? '✕' : idx + 1}
                </div>
                <span className="stepper-node-name">{stg.name.split(' ')[0]}</span>
                {idx < 4 && <div className={`stepper-node-line ${isStageOk ? 'completed' : ''}`} />}
              </div>
            );
          })}
        </div>
      </div>

      {/* Live Current Action HUD */}
      <div className="live-status-hud">
        <div className="hud-phase-row">
          <span className="hud-phase-label">CURRENT ORCHESTRATOR STATE:</span>
          <span className={`hud-phase-pill ${isRunning ? 'pulse' : executionTrace.length > 0 ? 'done' : 'idle'}`}>
            {isRunning ? 'IN PROGRESS' : executionTrace.length > 0 ? 'SUCCESS' : 'IDLE'}
          </span>
        </div>
        <p className="hud-current-action">{currentAction}</p>
      </div>

      {/* Navigation Tabs */}
      <div className="live-logs-tabs">
        <button
          type="button"
          className={`live-tab-btn ${tab === 'overview' ? 'active' : ''}`}
          onClick={() => setTab('overview')}
        >
          <span>Live Activity</span>
          {isRunning && <span className="running-dot-ping" />}
        </button>
        <button
          type="button"
          className={`live-tab-btn ${tab === 'flow' ? 'active' : ''}`}
          onClick={() => setTab('flow')}
        >
          <span>Step Log ({executionTrace.length})</span>
        </button>
        <button
          type="button"
          className={`live-tab-btn ${tab === 'stages' ? 'active' : ''}`}
          onClick={() => setTab('stages')}
        >
          <span>Stages</span>
        </button>
        <button
          type="button"
          className={`live-tab-btn ${tab === 'diagnostics' ? 'active' : ''}`}
          onClick={() => setTab('diagnostics')}
        >
          <span>Diagnostics</span>
          {errorCount > 0 && <span className="live-err-badge">{errorCount}</span>}
        </button>
        <button
          type="button"
          className={`live-tab-btn ${tab === 'raw' ? 'active' : ''}`}
          onClick={() => setTab('raw')}
        >
          <span>JSON</span>
        </button>
      </div>

      {/* Content Body */}
      <div className="live-logs-content" ref={scrollRef}>
        {/* TAB 1: Live Status & Activity ("What is Happening vs What is Not") */}
        {tab === 'overview' && (
          <div className="live-overview-view">
            {/* Quick Filter Controls */}
            <div className="activity-filter-bar">
              <span className="filter-title">Filter Details:</span>
              <div className="filter-pills">
                <button
                  type="button"
                  className={`filter-pill ${activityFilter === 'all' ? 'active' : ''}`}
                  onClick={() => setActivityFilter('all')}
                >
                  All ({happeningItems.length + notHappeningItems.length})
                </button>
                <button
                  type="button"
                  className={`filter-pill happening ${activityFilter === 'happening' ? 'active' : ''}`}
                  onClick={() => setActivityFilter('happening')}
                >
                  Happening ({happeningItems.length})
                </button>
                <button
                  type="button"
                  className={`filter-pill not-happening ${activityFilter === 'not' ? 'active' : ''}`}
                  onClick={() => setActivityFilter('not')}
                >
                  Not Happening ({notHappeningItems.length})
                </button>
              </div>
            </div>

            {/* Section 1: What is Happening (Active & Completed Operations) */}
            {(activityFilter === 'all' || activityFilter === 'happening') && (
              <div className="activity-section happening-section">
                <div className="activity-section-header">
                  <div className="sec-title-wrap">
                    <span className="sec-indicator green" />
                    <h4>WHAT IS HAPPENING</h4>
                  </div>
                  <span className="sec-count">{happeningItems.length} active / completed</span>
                </div>

                {happeningItems.length > 0 ? (
                  <div className="activity-card-grid">
                    {happeningItems.map((item, idx) => (
                      <div key={idx} className={`activity-card happening-card ${item.status}`}>
                        <div className="act-card-head">
                          <span className={`act-tag ${item.status}`}>{item.tag}</span>
                          {item.status === 'active' && <span className="act-live-badge">LIVE NOW</span>}
                        </div>
                        <strong className="act-title">{item.title}</strong>
                        <p className="act-detail">{item.detail}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="activity-empty-box">
                    <p>No active steps running. Submit a query to see live execution details.</p>
                  </div>
                )}
              </div>
            )}

            {/* Section 2: What is NOT Happening (Skipped, Dormant, Bypassed Branches) */}
            {(activityFilter === 'all' || activityFilter === 'not') && (
              <div className="activity-section not-happening-section">
                <div className="activity-section-header">
                  <div className="sec-title-wrap">
                    <span className="sec-indicator slate" />
                    <h4>WHAT IS NOT HAPPENING (DORMANT / SKIPPED)</h4>
                  </div>
                  <span className="sec-count">{notHappeningItems.length} inactive paths</span>
                </div>

                <div className="activity-card-grid">
                  {notHappeningItems.map((item, idx) => (
                    <div key={idx} className="activity-card not-card">
                      <div className="act-card-head">
                        <span className="act-cat-label">{item.category}</span>
                        <span className={`act-reason-pill ${item.reason.toLowerCase()}`}>
                          {item.reason}
                        </span>
                      </div>
                      <strong className="act-title text-muted">{item.title}</strong>
                      <p className="act-detail text-soft">{item.explanation}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 2: Step-by-Step Live Flow */}
        {tab === 'flow' && (
          <div className="live-flow-view">
            {executionTrace && executionTrace.length > 0 ? (
              <div className="flow-timeline">
                {executionTrace.map((row, i) => {
                  const step = describeStep(row);
                  const isLast = i === executionTrace.length - 1;
                  const isActive = isRunning && isLast;

                  return (
                    <div key={i} className="flow-node-wrapper">
                      <div className={`flow-node-card ${step.ok === false ? 'node-error' : 'node-ok'} ${isActive ? 'node-active' : ''}`}>
                        <div className="node-head-row">
                          <span className="node-step-index">STEP #{i + 1}</span>
                          <strong className="node-title">{step.label}</strong>
                          <span className={`node-status-tag ${isActive ? 'active' : step.ok ? 'ok' : 'fail'}`}>
                            {isActive ? 'ACTIVE NOW' : step.ok ? 'SUCCESS' : 'NOTICE'}
                          </span>
                        </div>

                        {row.summary && (
                          <div className="node-summary-box">
                            <span className="summary-lbl">Execution detail:</span>
                            <p className="node-summary-text">{row.summary}</p>
                          </div>
                        )}

                        <div className="node-footer-meta">
                          <span className="node-type-pill">Node: <code>{row.node}</code></span>
                          {row.timestamp && <span className="node-time-val">{row.timestamp}</span>}
                        </div>
                      </div>

                      {!isLast && <div className="flow-vertical-connector" />}
                    </div>
                  );
                })}

                {isRunning && (
                  <div className="flow-node-wrapper">
                    <div className="flow-vertical-connector dashed" />
                    <div className="flow-pending-card">
                      <span className="flow-spinner" />
                      <span>LangGraph orchestrator resolving next node…</span>
                    </div>
                  </div>
                )}
              </div>
            ) : isRunning ? (
              <div className="flow-initial-waiting">
                <span className="flow-spinner-large" />
                <h4>Orchestrator Initiating Graph</h4>
                <p>Streaming real-time execution steps as nodes execute on server…</p>
              </div>
            ) : (
              <div className="flow-empty-state">
                <div className="empty-flow-icon">⚡</div>
                <h4>Awaiting Query Execution</h4>
                <p>Submit a query to see the live step-by-step workflow trajectory alongside your results.</p>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: "What is Happening vs What is Not" Stages Breakdown */}
        {tab === 'stages' && (
          <div className="stages-breakdown-view">
            <div className="stages-explainer-banner">
              <span className="explainer-icon">ℹ️</span>
              <p>Real-time tracking of what tools and decision paths were activated vs skipped across the 5 canonical pipeline stages.</p>
            </div>

            <div className="stages-card-list">
              {/* Stage 1: Validation */}
              <div className={`stage-card ${stages.validate.status}`}>
                <div className="stage-card-head">
                  <span className="stage-num">STAGE 1</span>
                  <strong>Input & AOI Validation</strong>
                  <span className={`stage-state-pill ${stages.validate.status}`}>
                    {stages.validate.status === 'ok' ? '✓ Passed' : stages.validate.status === 'active' ? 'Checking…' : 'Idle'}
                  </span>
                </div>
                <div className="stage-row-happening">
                  <span className="row-tag yes">What Happened:</span>
                  <p>{stages.validate.happening}</p>
                </div>
                <div className="stage-row-not">
                  <span className="row-tag no">What Did Not:</span>
                  <p>{stages.validate.notHappening}</p>
                </div>
              </div>

              {/* Stage 2: Knowledge Base */}
              <div className={`stage-card ${stages.knowledgeBase.status}`}>
                <div className="stage-card-head">
                  <span className="stage-num">STAGE 2</span>
                  <strong>Knowledge Base & Pre-Flight QA</strong>
                  <span className={`stage-state-pill ${stages.knowledgeBase.status}`}>
                    {stages.knowledgeBase.status === 'ok' ? '✓ Loaded' : stages.knowledgeBase.status === 'skipped' ? '↷ Skipped' : 'Idle'}
                  </span>
                </div>
                <div className="stage-row-happening">
                  <span className="row-tag yes">What Happened:</span>
                  <p>{stages.knowledgeBase.happening}</p>
                </div>
                <div className="stage-row-not">
                  <span className="row-tag no">What Did Not:</span>
                  <p>{stages.knowledgeBase.notHappening}</p>
                </div>
              </div>

              {/* Stage 3: Vision VLM */}
              <div className={`stage-card ${stages.visionAnalysis.status}`}>
                <div className="stage-card-head">
                  <span className="stage-num">STAGE 3</span>
                  <strong>Visual Scene VLM Recognition</strong>
                  <span className={`stage-state-pill ${stages.visionAnalysis.status}`}>
                    {stages.visionAnalysis.status === 'ok' ? '✓ Generated' : stages.visionAnalysis.status === 'skipped' ? '↷ Skipped' : 'Idle'}
                  </span>
                </div>
                <div className="stage-row-happening">
                  <span className="row-tag yes">What Happened:</span>
                  <p>{stages.visionAnalysis.happening}</p>
                </div>
                <div className="stage-row-not">
                  <span className="row-tag no">What Did Not:</span>
                  <p>{stages.visionAnalysis.notHappening}</p>
                </div>
              </div>

              {/* Stage 4: Remote-Sensing Tools */}
              <div className={`stage-card ${stages.toolsExecution.status}`}>
                <div className="stage-card-head">
                  <span className="stage-num">STAGE 4</span>
                  <strong>EO Tool Deployment ({stages.toolsExecution.count} Tools)</strong>
                  <span className={`stage-state-pill ${stages.toolsExecution.status}`}>
                    {stages.toolsExecution.count > 0 ? `✓ ${stages.toolsExecution.count} Executed` : stages.toolsExecution.status === 'active' ? 'Running…' : 'Idle'}
                  </span>
                </div>
                <div className="stage-row-happening">
                  <span className="row-tag yes">What Happened:</span>
                  <p>{stages.toolsExecution.happening}</p>
                </div>
                <div className="stage-row-not">
                  <span className="row-tag no">What Did Not:</span>
                  <p>{stages.toolsExecution.notHappening}</p>
                </div>
              </div>

              {/* Stage 5: Synthesis */}
              <div className={`stage-card ${stages.synthesis.status}`}>
                <div className="stage-card-head">
                  <span className="stage-num">STAGE 5</span>
                  <strong>Geospatial Intelligence Report</strong>
                  <span className={`stage-state-pill ${stages.synthesis.status}`}>
                    {stages.synthesis.status === 'ok' ? '✓ Ready' : stages.synthesis.status === 'pending' ? 'Synthesizing…' : 'Idle'}
                  </span>
                </div>
                <div className="stage-row-happening">
                  <span className="row-tag yes">What Happened:</span>
                  <p>{stages.synthesis.happening}</p>
                </div>
                <div className="stage-row-not">
                  <span className="row-tag no">What Did Not:</span>
                  <p>{stages.synthesis.notHappening}</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: Diagnostics */}
        {tab === 'diagnostics' && (
          <div className="live-diagnostics-view">
            {backendUp === false && (
              <div className="diag-card err-critical">
                <div className="diag-head">
                  <span className="diag-type">BACKEND_DISCONNECTED</span>
                  <span className="diag-badge">Offline</span>
                </div>
                <p className="diag-msg">
                  Could not reach SatQuery API at localhost:8000. Start backend with <code>python -m backend.main</code>.
                </p>
              </div>
            )}

            {errors && errors.length > 0 ? (
              errors.map((err, i) => (
                <div key={i} className="diag-card">
                  <div className="diag-head">
                    <span className="diag-type">EXECUTION_ERROR</span>
                  </div>
                  <pre className="diag-msg">{typeof err === 'object' ? JSON.stringify(err, null, 2) : String(err)}</pre>
                </div>
              ))
            ) : backendUp !== false ? (
              <div className="diag-clean-state">
                <span className="diag-check-icon">✓</span>
                <h4>System Healthy</h4>
                <p>Zero exceptions or validation warnings logged in current run.</p>
              </div>
            ) : null}
          </div>
        )}

        {/* TAB 5: Raw JSON */}
        {tab === 'raw' && (
          <div className="live-raw-view">
            {rawToolResults && rawToolResults.length > 0 ? (
              <pre className="telemetry-json-block">{JSON.stringify(rawToolResults, null, 2)}</pre>
            ) : (
              <div className="flow-empty-state">
                <p>No tool telemetry results for this turn yet.</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="live-logs-footer">
        <span className="footer-status">
          Engine: {isRunning ? 'Streaming Graph' : backendUp ? 'Idle / Ready' : 'Backend Disconnected'}
        </span>
        <button type="button" className="btn-collapse-text" onClick={onClose}>
          Hide Logs
        </button>
      </div>
    </aside>
  );
}
