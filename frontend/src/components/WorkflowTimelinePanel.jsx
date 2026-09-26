import React, { useState } from 'react';
import { describeStep } from '../lib/executionSteps';
import { toolLabel } from '../lib/toolLabels';

/**
 * Compact Professional Workflow Timeline & Live Events Panel
 * 
 * Features:
 * - 6-step professional timeline: Input, Knowledge, Vision, Tools, Analysis, Complete
 * - Current step clearly highlighted with subtle processing animation
 * - Clean latest 3–5 meaningful execution events
 * - "View details" toggle for full trace logs
 * - Zero raw log bloat dominating the interface
 */
export default function WorkflowTimelinePanel({
  executionTrace = [],
  toolResults = [],
  isRunning = false,
  errors = [],
  backendUp,
  onOpenDetails
}) {
  const [showInlineDetails, setShowInlineDetails] = useState(false);

  // Compute status for the 6 workflow timeline steps
  const nodes = executionTrace.map((t) => t.node);
  const hasValidate = nodes.includes('validate');
  const hasKb = nodes.includes('load_knowledge_base');
  const hasVlm = nodes.includes('vlm_initial_description');
  const toolSteps = executionTrace.filter((t) => t.node === 'tool');
  const hasRespond = nodes.includes('respond');

  const steps = [
    {
      id: 'input',
      name: 'Input',
      status: hasValidate ? 'complete' : isRunning ? 'active' : 'idle'
    },
    {
      id: 'knowledge',
      name: 'Knowledge',
      status: hasKb ? 'complete' : isRunning && hasValidate && !hasKb ? 'active' : 'idle'
    },
    {
      id: 'vision',
      name: 'Vision',
      status: hasVlm ? 'complete' : isRunning && hasKb && !hasVlm ? 'active' : 'idle'
    },
    {
      id: 'tools',
      name: 'Tools',
      status: toolSteps.length > 0 && (!isRunning || hasRespond)
        ? 'complete'
        : isRunning && (hasVlm || hasKb) && !hasRespond
          ? 'active'
          : 'idle'
    },
    {
      id: 'analysis',
      name: 'Analysis',
      status: hasRespond ? 'complete' : isRunning && (toolSteps.length > 0 || hasVlm) ? 'active' : 'idle'
    },
    {
      id: 'complete',
      name: 'Complete',
      status: hasRespond && !isRunning ? 'complete' : 'idle'
    }
  ];

  // Derive latest meaningful execution events including step-by-step tool calls
  const meaningfulEvents = [];
  executionTrace.forEach((entry, idx) => {
    const isLast = idx === executionTrace.length - 1;
    const desc = describeStep(entry);
    if (!desc || !desc.label) return;

    let displayLabel = desc.label;

    // If it's a tool execution step, attach duration if available
    if (entry.node === 'tool') {
      const toolMatch = entry.summary?.match(/^(\S+) status=(\S+)/);
      if (toolMatch) {
        const toolName = toolMatch[1];
        const matchResult = toolResults.find((r) => r.tool === toolName);
        if (matchResult?.duration_ms) {
          displayLabel = `${desc.label} (${Math.round(matchResult.duration_ms)}ms)`;
        }
      }
    }

    if (isLast && isRunning) {
      meaningfulEvents.push({
        id: idx,
        type: 'running',
        symbol: '→',
        label: `Running ${displayLabel.toLowerCase()}`
      });
    } else {
      meaningfulEvents.push({
        id: idx,
        type: desc.ok === false ? 'fail' : 'complete',
        symbol: desc.ok === false ? '✕' : '✓',
        label: displayLabel
      });
    }
  });

  // Take latest 4 events to keep interface compact and clean
  const recentEvents = meaningfulEvents.slice(-4);

  const handleDetailsClick = () => {
    if (onOpenDetails) {
      onOpenDetails();
    } else {
      setShowInlineDetails((prev) => !prev);
    }
  };

  return (
    <div className="ws-workflow-timeline-panel">
      {/* 1. Compact 6-Step Workflow Timeline */}
      <div className="workflow-timeline-header">
        <div className="timeline-steps-track">
          {steps.map((st, i) => {
            const isComplete = st.status === 'complete';
            const isActive = st.status === 'active';

            return (
              <React.Fragment key={st.id}>
                <div
                  className={`timeline-step ${isComplete ? 'step-complete' : ''} ${isActive ? 'step-active' : ''}`}
                  title={`${st.name} step: ${st.status}`}
                >
                  <span className="step-bullet">
                    {isComplete ? '✓' : isActive ? '●' : '●'}
                  </span>
                  <span className="step-name">{st.name}</span>
                </div>
                {i < steps.length - 1 && (
                  <span className={`timeline-connector ${isComplete ? 'connector-done' : ''}`}>
                    ›
                  </span>
                )}
              </React.Fragment>
            );
          })}
        </div>

        <div className="timeline-header-actions">
          {errors.length > 0 && <span className="timeline-err-badge">{errors.length} err</span>}
          <button
            type="button"
            className="btn-view-details"
            onClick={handleDetailsClick}
            title="Open Detailed Logs and GeoTIFF Metadata Inspector"
          >
            <span>▾ Detailed logs</span>
          </button>
        </div>
      </div>

      {/* 2. Latest 3–5 Meaningful Execution Events showing step-by-step tool calls */}
      <div className="timeline-recent-events">
        {recentEvents.length > 0 ? (
          recentEvents.map((evt) => (
            <div key={evt.id} className={`recent-event-line evt-${evt.type}`}>
              <span className="evt-symbol">{evt.symbol}</span>
              <span className="evt-label">{evt.label}</span>
            </div>
          ))
        ) : (
          <div className="recent-event-line evt-idle">
            <span className="evt-symbol">○</span>
            <span className="evt-label">Workflow engine standby — submit query to initiate pipeline</span>
          </div>
        )}
      </div>

      {/* 3. Fallback inline details if onOpenDetails is not provided */}
      {!onOpenDetails && showInlineDetails && (
        <div className="timeline-full-details-tray">
          <div className="details-tray-head">
            <span>Execution Trace Log ({executionTrace.length} events)</span>
          </div>
          <div className="details-tray-scroll dark-scroll">
            {executionTrace.map((entry, idx) => (
              <div key={idx} className="details-log-row">
                <span className="log-node">{entry.node}</span>
                <span className="log-arrow">→</span>
                <span className="log-summary">{entry.summary || 'done'}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
