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

  if (node === 'load_knowledge_base') {
    if (summary === 'loaded from disk' || summary === 'provided inline') {
      return { label: 'Loaded image knowledge base', ok: true };
    }
    return { label: 'No knowledge base for this image', ok: null };
  }

  if (node === 'vlm_initial_description') {
    if (summary === 'generated') return { label: 'Auto-described whole image', ok: true };
    if (summary === 'failed') return { label: 'Initial description failed', ok: false };
    return { label: 'Skipped initial description', ok: null };
  }

  if (node === 'describe_region_auto') {
    if (summary === 'generated') return { label: 'Auto-described marked region', ok: true };
    if (summary === 'failed') return { label: 'Marked-region description failed', ok: false };
    return { label: 'No region marked', ok: null };
  }

  // "llm" and "tool" are the tool_loop subgraph's own node names
  // (backend/orchestrator/tool_loop_graph.py) -- each hop of the
  // start -> llm -> tool -> llm ... loop appends one of each.
  if (node === 'llm') {
    const action = summary.match(/action=(\S+)/)?.[1];
    const tool = summary.match(/tool=(\S+)/)?.[1];
    if (action === 'call_tool' && tool) return { label: `Plan: use ${toolLabel(tool)}`, ok: true };
    if (action === 'clarify') return { label: 'Plan: need more info', ok: null };
    if (action === 'chat') return { label: 'Plan: general reply', ok: true };
    if (action === 'finish') return { label: 'Plan: enough gathered', ok: true };
    if (action === 'respond_error') return { label: 'Plan: error', ok: false };
    return { label: 'Plan', ok: true };
  }

  if (node === 'tool') {
    const m = summary.match(/^(\S+) status=(\S+)/);
    if (m) return { label: `Run ${toolLabel(m[1])}`, ok: m[2] === 'success' };
    if (summary.startsWith('blocked')) return { label: 'Blocked: missing input', ok: false };
    if (summary.startsWith('skipped')) return { label: 'No tool to run', ok: null };
    return { label: 'Execute', ok: false };
  }

  if (node === 'respond') {
    if (summary.startsWith('success')) return { label: 'Answer', ok: true };
    if (summary === 'clarify') return { label: 'Ask for more info', ok: null };
    if (summary === 'chat') return { label: 'Reply', ok: true };
    return { label: 'Error', ok: false };
  }

  // Fallback: any node not covered above still shows explicitly, by its
  // raw name and summary, rather than being silently dropped.
  return { label: summary ? `${node}: ${summary}` : node, ok: true };
}
