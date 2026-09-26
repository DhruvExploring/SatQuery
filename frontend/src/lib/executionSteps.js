import { toolLabel } from './toolLabels';

/**
 * Turn one backend execution_trace entry ({node, timestamp, summary}, see
 * backend/orchestrator/state.py::trace_entry) into a short, human label plus
 * an ok/fail/pending tri-state for coloring -- structured step labels, not
 * the raw plan/LLM reasoning text.
 */
export function describeStep(entry) {
  const { node, summary = '' } = entry;

  if (node === 'validate') {
    const ok = summary === 'input ok';
    return { label: ok ? 'Input parameters validated' : 'Validation failed', ok };
  }

  if (node === 'load_knowledge_base') {
    if (summary === 'loaded from disk' || summary === 'provided inline') {
      return { label: 'Knowledge base loaded', ok: true };
    }
    return { label: 'Operating without disk cache', ok: null };
  }

  if (node === 'vlm_initial_description') {
    if (summary === 'generated') return { label: 'Vision analysis completed', ok: true };
    if (summary === 'failed') return { label: 'Vision analysis failed', ok: false };
    return { label: 'Vision pass skipped', ok: null };
  }

  if (node === 'describe_region_auto') {
    if (summary === 'generated') return { label: 'Region of interest analyzed', ok: true };
    if (summary === 'failed') return { label: 'Region analysis failed', ok: false };
    return { label: 'No region marked', ok: null };
  }

  // "llm" and "tool" are the tool_loop subgraph's own node names
  if (node === 'llm') {
    const action = summary.match(/action=(\S+)/)?.[1];
    const tool = summary.match(/tool=(\S+)/)?.[1];
    if (action === 'call_tool' && tool) return { label: `Tool call planned: ${toolLabel(tool)}`, ok: true };
    if (action === 'clarify') return { label: 'Plan: clarification needed', ok: null };
    if (action === 'chat') return { label: 'Plan: direct response', ok: true };
    if (action === 'finish') return { label: 'Plan: analysis complete', ok: true };
    if (action === 'respond_error') return { label: 'Plan: error handler', ok: false };
    return { label: 'Planner reasoning step', ok: true };
  }

  if (node === 'tool') {
    const m = summary.match(/^(\S+) status=(\S+)/);
    if (m) return { label: `Tool call: ${toolLabel(m[1])}`, ok: m[2] === 'success' };
    if (summary.startsWith('blocked')) return { label: 'Tool blocked: missing input', ok: false };
    if (summary.startsWith('skipped')) return { label: 'Tool skipped', ok: null };
    return { label: `Tool execution: ${summary}`, ok: false };
  }

  if (node === 'respond') {
    if (summary.startsWith('success')) return { label: 'Geospatial report generated', ok: true };
    if (summary === 'clarify') return { label: 'Clarification response ready', ok: null };
    if (summary === 'chat') return { label: 'Chat response ready', ok: true };
    return { label: 'Error response ready', ok: false };
  }

  return { label: summary ? `${node}: ${summary}` : node, ok: true };
}
