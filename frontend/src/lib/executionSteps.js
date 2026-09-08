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
    return { label: ok ? 'Validated input' : 'Validation failed', ok };
  }

  if (node === 'plan') {
    const action = summary.match(/action=(\S+)/)?.[1];
    const tool = summary.match(/tool=(\S+)/)?.[1];
    if (action === 'call_tool' && tool) return { label: `Plan: use ${toolLabel(tool)}`, ok: true };
    if (action === 'clarify') return { label: 'Plan: need more info', ok: null };
    if (action === 'chat') return { label: 'Plan: general reply', ok: true };
    if (action === 'finish') return { label: 'Plan: enough gathered', ok: true };
    if (action === 'respond_error') return { label: 'Plan: error', ok: false };
    return { label: 'Plan', ok: true };
  }

  if (node === 'execute') {
    const m = summary.match(/^(\S+) status=(\S+)/);
    if (m) return { label: `Run ${toolLabel(m[1])}`, ok: m[2] === 'success' };
    if (summary.startsWith('blocked')) return { label: 'Blocked: missing input', ok: false };
    return { label: 'Execute', ok: false };
  }

  if (node === 'advance') {
    const complete = /complete=True/.test(summary);
    const gated = summary.includes('gated');
    if (gated) return { label: 'Stopped (data issue)', ok: false };
    return { label: complete ? 'Ready to answer' : 'Gather more info', ok: true };
  }

  if (node === 'respond') {
    if (summary.startsWith('success')) return { label: 'Answer', ok: true };
    if (summary === 'clarify') return { label: 'Ask for more info', ok: null };
    if (summary === 'chat') return { label: 'Reply', ok: true };
    return { label: 'Error', ok: false };
  }

  return { label: node, ok: true };
}
