import React, { useEffect, useRef, useState } from 'react';
import { describeStep } from '../lib/executionSteps';
import { toolLabel } from '../lib/toolLabels';

/**
 * Analysis of the 5 canonical remote-sensing pipeline stages:
 * 1. Input & Parameters Validation
 * 2. Knowledge Base & Pre-Flight Cache
 * 3. Vision VLM Scene Recognition
 * 4. Remote-Sensing EO Tools Deployment
 * 5. Geospatial Intelligence Report Synthesis
 */
function analyzeWorkflowStages(trace = [], isRunning = false) {
  const nodes = trace.map((t) => t.node);

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

  return {
    validate: {
      id: 'validate',
      name: 'Validate',
      status: hasValidate ? (validateOk ? 'ok' : 'fail') : isRunning ? 'active' : 'idle',
      happening: validateOk
        ? 'Query parsed and geodetic coordinate constraints confirmed [EPSG:4326]'
        : hasValidate
          ? 'Validation detected missing parameters or syntax issues'
          : isRunning
            ? 'Analyzing query structure…'
            : 'Idle',
      notHappening: validateOk ? 'No coordinate or schema errors' : 'Awaiting valid parameters'
    },
    knowledgeBase: {
      id: 'knowledgeBase',
      name: 'Knowledge Base',
      status: hasKb ? (kbLoaded ? 'ok' : 'skipped') : isRunning && !hasKb ? 'pending' : 'idle',
      happening: kbLoaded
        ? 'Retrieved cached GeoTIFF profile & band designations from disk'
        : hasKb
          ? 'Operating dynamically on-the-fly without pre-existing disk cache'
          : isRunning
            ? 'Checking metadata cache…'
            : 'Idle',
      notHappening: kbLoaded ? 'Cached profile used directly' : 'Pre-flight disk cache hit skipped'
    },
    visionAnalysis: {
      id: 'visionAnalysis',
      name: 'Vision VLM',
      status: hasVlm ? (vlmGenerated ? 'ok' : 'skipped') : isRunning && !hasVlm ? 'pending' : 'idle',
      happening: vlmGenerated
        ? 'VLM generated initial descriptive visual overview of visible scene features'
        : hasVlm
          ? 'Vision prose bypassed to prioritize deterministic analytical tools'
          : isRunning
            ? 'Evaluating visual scene inspection…'
            : 'Idle',
      notHappening: vlmGenerated ? 'Vision narrative generated' : 'Prose skipped to minimize latency'
    },
    toolsExecution: {
      id: 'toolsExecution',
      name: 'EO Tools',
      status: toolsRun.length > 0 ? (toolsRun.every((t) => t.ok) ? 'ok' : 'fail') : isRunning ? 'active' : 'idle',
      count: toolsRun.length,
      tools: toolsRun,
      happening:
        toolsRun.length > 0
          ? toolsRun.map((t) => toolLabel(t.tool)).join(', ')
          : isRunning
            ? 'Selecting remote-sensing tools…'
            : 'Idle',
      notHappening: toolsRun.length > 0 ? 'Tools executed nominal' : 'No spatial tools called yet'
    },
    synthesis: {
      id: 'synthesis',
      name: 'Synthesis',
      status: hasRespond ? 'ok' : isRunning && (toolsRun.length > 0 || hasVlm) ? 'active' : 'idle',
      happening: hasRespond ? 'Synthesized geospatial intelligence report' : isRunning ? 'Synthesizing…' : 'Idle',
      notHappening: hasRespond ? 'Complete' : 'Pending prior stages'
    }
  };
}

export default function LiveLogsPanel({
  executionTrace = [],
  errors = [],
  toolResults = [],
  backendUp,
  isRunning
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [tab, setTab] = useState('trace'); // 'trace' | 'stages' | 'diagnostics' | 'raw'
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

  // Auto-scroll trace feed on new steps
  useEffect(() => {
    if (scrollRef.current && isExpanded && tab === 'trace') {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [executionTrace, isRunning, isExpanded, tab]);

  const stages = analyzeWorkflowStages(executionTrace, isRunning);
  const stageList = [
    stages.validate,
    stages.knowledgeBase,
    stages.visionAnalysis,
    stages.toolsExecution,
    stages.synthesis
  ];

  const lastNode = executionTrace[executionTrace.length - 1];
  const lastStepDesc = lastNode ? describeStep(lastNode) : null;
  const recentSteps = executionTrace.slice(-3);
  const totalErrors = (errors?.length || 0) + (backendUp === false ? 1 : 0);

  return (
    <div className={`ws-telemetry-panel ${isExpanded ? 'expanded' : 'compact'}`}>
      {/* Permanent Top Pipeline Strip (Always Visible) */}
      <div className="ws-telemetry-bar">
        <div className="telemetry-bar-left">
          <div className="telemetry-status-beacon" title={isRunning ? 'Execution graph running' : 'Telemetry standby'}>
            <span className={`beacon-dot ${isRunning ? 'running' : 'idle'}`} />
            <span className="beacon-label">PIPELINE</span>
          </div>

          {/* 5-Stage Compact Status Pills */}
          <div className="pipeline-stages-track">
            {stageList.map((st) => {
              const badgeClass =
                st.status === 'ok'
                  ? 'st-ok'
                  : st.status === 'active'
                    ? 'st-active'
                    : st.status === 'fail'
                      ? 'st-fail'
                      : st.status === 'skipped'
                        ? 'st-skipped'
                        : 'st-idle';

              const icon =
                st.status === 'ok'
                  ? '✓'
                  : st.status === 'active'
                    ? '⋯'
                    : st.status === 'fail'
                      ? '✕'
                      : st.status === 'skipped'
                        ? '↷'
                        : '○';

              return (
                <div key={st.id} className={`pipeline-stage-chip ${badgeClass}`} title={`${st.name}: ${st.happening}`}>
                  <span className="stage-icon">{icon}</span>
                  <span className="stage-name">{st.name}</span>
                  {st.count !== undefined && st.count > 0 && <span className="stage-count">({st.count})</span>}
                </div>
              );
            })}
          </div>
        </div>

        <div className="telemetry-bar-right">
          {isRunning && <span className="telemetry-timer">{elapsedTime}s</span>}
          {executionTrace.length > 0 && (
            <span className="telemetry-step-count">{executionTrace.length} steps</span>
          )}
          {totalErrors > 0 && <span className="telemetry-error-tag">{totalErrors} err</span>}

          <button
            type="button"
            className="btn-telemetry-toggle"
            onClick={() => setIsExpanded((prev) => !prev)}
            title={isExpanded ? 'Collapse detailed logs' : 'Expand full execution logs & diagnostics'}
          >
            <span>{isExpanded ? '▴ Compact' : '▾ Details'}</span>
          </button>
        </div>
      </div>

      {/* Live Step Teaser (Always Visible in Compact Mode) */}
      {!isExpanded && (
        <div className="ws-telemetry-recent">
          <span className="recent-prefix">LATEST:</span>
          {isRunning && lastStepDesc ? (
            <span className="recent-content running">
              <span className="recent-node">{lastNode.node}</span>
              <span className="recent-sep">→</span>
              <span className="recent-summary">{lastNode.summary || 'Processing…'}</span>
            </span>
          ) : recentSteps.length > 0 ? (
            <span className="recent-content">
              <span className="recent-node">{lastNode.node}</span>
              <span className="recent-sep">→</span>
              <span className="recent-summary">{lastNode.summary || 'Completed'}</span>
            </span>
          ) : (
            <span className="recent-content idle">Engine standby. Execution trace will stream live here.</span>
          )}
        </div>
      )}

      {/* Expanded Details Tray (Smoothly reveals when isExpanded is true) */}
      {isExpanded && (
        <div className="ws-telemetry-tray">
          <div className="telemetry-tray-nav">
            <button
              type="button"
              className={`tray-tab-btn ${tab === 'trace' ? 'active' : ''}`}
              onClick={() => setTab('trace')}
            >
              Execution Trace ({executionTrace.length})
            </button>
            <button
              type="button"
              className={`tray-tab-btn ${tab === 'stages' ? 'active' : ''}`}
              onClick={() => setTab('stages')}
            >
              Stages Breakdown
            </button>
            <button
              type="button"
              className={`tray-tab-btn ${tab === 'diagnostics' ? 'active' : ''}`}
              onClick={() => setTab('diagnostics')}
            >
              Diagnostics {totalErrors > 0 && `(${totalErrors})`}
            </button>
            <button
              type="button"
              className={`tray-tab-btn ${tab === 'raw' ? 'active' : ''}`}
              onClick={() => setTab('raw')}
            >
              Tool Output ({toolResults.length})
            </button>
          </div>

          <div className="telemetry-tray-content" ref={scrollRef}>
            {/* TAB: Trace */}
            {tab === 'trace' && (
              <div className="tray-feed">
                {executionTrace.length === 0 ? (
                  <div className="tray-empty">No execution steps logged yet. Submit a query to see the live toolchain.</div>
                ) : (
                  executionTrace.map((row, idx) => {
                    const desc = describeStep(row);
                    const time = row.timestamp ? new Date(row.timestamp).toLocaleTimeString() : `#${idx + 1}`;
                    return (
                      <div key={idx} className="trace-row">
                        <span className="trace-time">{time}</span>
                        <span className={`trace-node node-${row.node}`}>{row.node}</span>
                        <span className="trace-label">{desc.label}</span>
                        {row.summary && <span className="trace-summary">{row.summary}</span>}
                      </div>
                    );
                  })
                )}
              </div>
            )}

            {/* TAB: Stages Breakdown */}
            {tab === 'stages' && (
              <div className="tray-stages-grid">
                {stageList.map((st) => (
                  <div key={st.id} className="stage-detail-card">
                    <div className="stage-detail-head">
                      <span className="stage-detail-name">{st.name}</span>
                      <span className={`stage-state-tag ${st.status}`}>{st.status.toUpperCase()}</span>
                    </div>
                    <div className="stage-detail-row">
                      <span className="row-tag">Active:</span> {st.happening}
                    </div>
                    <div className="stage-detail-row muted">
                      <span className="row-tag">Dormant:</span> {st.notHappening}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* TAB: Diagnostics */}
            {tab === 'diagnostics' && (
              <div className="tray-diagnostics">
                {backendUp === false && (
                  <div className="diag-item error">
                    <strong>BACKEND DISCONNECTED:</strong> Cannot connect to SatQuery API at localhost:8000.
                  </div>
                )}
                {errors && errors.length > 0 ? (
                  errors.map((err, i) => (
                    <div key={i} className="diag-item error">
                      <strong>ERROR #{i + 1}:</strong> {typeof err === 'object' ? JSON.stringify(err) : String(err)}
                    </div>
                  ))
                ) : backendUp !== false ? (
                  <div className="diag-clean">✓ System healthy. No exceptions or execution warnings recorded.</div>
                ) : null}
              </div>
            )}

            {/* TAB: Raw Output */}
            {tab === 'raw' && (
              <div className="tray-raw">
                {toolResults && toolResults.length > 0 ? (
                  <pre className="raw-json-block">{JSON.stringify(toolResults, null, 2)}</pre>
                ) : (
                  <div className="tray-empty">No raw tool output payloads for this turn.</div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
