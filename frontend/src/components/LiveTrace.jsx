import React from 'react';

const NODE_TITLES = {
  validate: 'Query Ingestion & Validation',
  plan: 'LangGraph Agent Planner',
  execute: 'Tool Execution',
  advance: 'Handshake Advance',
  respond: 'Response Synthesis'
};

export function normalizeTrace(executionTrace = []) {
  return (executionTrace || []).map((entry, idx) => {
    const rawNode = typeof entry === 'string' ? entry : (entry?.node || `step_${idx + 1}`);
    const summary = typeof entry === 'object' ? (entry?.summary || '') : '';
    const timestamp = typeof entry === 'object' ? (entry?.timestamp || '') : '';
    const clean = String(rawNode).toLowerCase();
    return {
      step: idx + 1,
      node: String(rawNode),
      title: NODE_TITLES[clean] || `Node: ${rawNode}`,
      desc: summary || `Executed '${rawNode}'.`,
      time: timestamp
    };
  });
}

export default function LiveTrace({
  executionTrace = [],
  isRunning = false,
  hopCapHit = false
}) {
  const waitingNodes = ['validate', 'plan', 'execute', 'advance', 'respond'];
  const steps = isRunning
    ? waitingNodes.map((node, idx) => ({
        step: idx + 1,
        node,
        title: NODE_TITLES[node],
        desc: 'Waiting for the graph…',
        time: '',
        pending: true
      }))
    : normalizeTrace(executionTrace);

  if (!steps.length && !isRunning) {
    return (
      <div className="live-trace empty">
        <span className="form-hint">Execution trace will appear here after a run.</span>
      </div>
    );
  }

  return (
    <div className="live-trace">
      {hopCapHit && (
        <div className="clarify-banner hopcap">
          Analysis stopped partway (hop cap of 10). Partial tool results are kept.
        </div>
      )}
      <div className="timeline-flow compact">
        {steps.map((step) => (
          <div key={`${step.node}-${step.step}`} className={`timeline-step ${step.pending ? 'pending' : ''}`}>
            <div className="step-node-badge">{step.pending ? '…' : step.step}</div>
            <div className="step-content-card">
              <div className="step-main">
                <span className="step-title">{step.node} — {step.title}</span>
                <span className="step-desc">{step.desc}</span>
              </div>
              {step.time ? <span className="step-timestamp">{step.time}</span> : null}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
