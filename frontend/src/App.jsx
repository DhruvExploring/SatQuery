import React, { useEffect, useRef, useState } from 'react';
import { checkHealth, runQueryStream } from './api/satqueryApi';
import ChatMessage from './components/ChatMessage';
import ImageSlot from './components/ImageSlot';
import StepTimeline from './components/StepTimeline';
import { formatBbox, roiBoxToBbox } from './lib/geo';
import { loadSession, saveSession } from './lib/storage';

const RECAP_PAIR_LIMIT = 2;
const RECAP_ANSWER_CHARS = 320;

function truncate(text, max) {
  if (!text) return '';
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

/** Last few Q/A pairs, folded into the outgoing query text as plain-language
 * context — the backend runs each request statelessly (see backend/api/routes
 * /query.py: a fresh empty_state() every call, no thread/session concept), so
 * this is how a follow-up question ("is that a lot of rainfall?") gets to see
 * what "that" refers to. Capped in count and per-answer length so the prompt
 * doesn't grow unbounded over a long conversation. */
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
  const bbox = slot.boundsWgs84 ? roiBoxToBbox(slot.roi, slot.boundsWgs84) : null;
  return bbox
    ? `\n\n(Focus specifically on the ${label} region roughly bounded by ${formatBbox(bbox)}.)`
    : `\n\n(Focus specifically on the highlighted region of ${label}.)`;
}

function boundsToBbox(bounds) {
  if (!bounds) return null;
  return [bounds.min_lon, bounds.min_lat, bounds.max_lon, bounds.max_lat];
}

function buildFilePayload(mode, slotA, slotB) {
  const payload = {};
  if (mode === 'single') {
    if (slotA.uploadedPath) payload.input_file = slotA.uploadedPath;
    // The upload-time auto-inspect already extracted this file's real
    // coordinates (see ImageSlot's runInspection) -- carry them into every
    // request so a location-only tool (e.g. weather) can be satisfied
    // without another whole clarify round-trip asking the user for a bbox
    // the app already has.
    const bbox = boundsToBbox(slotA.boundsWgs84);
    if (bbox) payload.bbox = bbox;
    return payload;
  }
  if (slotA.uploadedPath) payload.raster_before_path = slotA.uploadedPath;
  if (slotB.uploadedPath) payload.raster_after_path = slotB.uploadedPath;
  // Single-image tools (vision analysis, inspection) still need *an*
  // image_path/input_file even in two-image mode, for a general question
  // that isn't phrased as an explicit before/after comparison.
  payload.input_file = slotB.uploadedPath || slotA.uploadedPath || undefined;
  const bbox = boundsToBbox(slotB.boundsWgs84) || boundsToBbox(slotA.boundsWgs84);
  if (bbox) payload.bbox = bbox;
  return payload;
}

const emptySlot = () => ({});

export default function App() {
  const saved = loadSession();

  const [mode, setMode] = useState(saved?.mode || 'single');
  const [slotA, setSlotA] = useState(saved?.slotA || emptySlot());
  const [slotB, setSlotB] = useState(saved?.slotB || emptySlot());
  const [messages, setMessages] = useState(saved?.messages || []);
  const [input, setInput] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [liveSteps, setLiveSteps] = useState([]);
  const [backendUp, setBackendUp] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    let mounted = true;
    checkHealth().then((res) => {
      if (mounted) setBackendUp(res.ok);
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
  };

  // Single vs. two-image are different tasks -- carrying an old file or
  // conversation across the switch is how a stale image ends up paired
  // against a fresh one (e.g. a leftover Image A from a previous session
  // compared against a brand new Image B).
  const handleModeChange = (newMode) => {
    if (newMode === mode) return;
    setMode(newMode);
    setSlotA(emptySlot());
    setSlotB(emptySlot());
    setMessages([]);
    setLiveSteps([]);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || isRunning) return;

    const attachmentNote =
      mode === 'single'
        ? slotA.uploadedPath
          ? `Attached: ${slotA.originalFilename}`
          : null
        : [slotA.uploadedPath && `A: ${slotA.originalFilename}`, slotB.uploadedPath && `B: ${slotB.originalFilename}`]
            .filter(Boolean)
            .join('   ') || null;

    const userMessage = {
      id: crypto.randomUUID(),
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

    const recap = buildRecap(priorMessages);
    const roiNote =
      mode === 'single' ? roiNoteFor(slotA, 'image') : roiNoteFor(slotA, 'Image A') + roiNoteFor(slotB, 'Image B');
    const fullQuery = `${recap ? `${recap} ` : ''}${text}${roiNote}`;

    const payload = { query: fullQuery, ...buildFilePayload(mode, slotA, slotB) };
    const { networkError, error, body } = await runQueryStream(payload, {
      onStep: (step) => setLiveSteps((prev) => [...prev, step])
    });

    let assistantMessage;
    if (networkError) {
      assistantMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        status: 'error',
        text: error || 'Could not reach the SatQuery API.',
        toolResults: [],
        executionTrace: [],
        timestamp: Date.now()
      };
    } else {
      const status = String(body?.status || 'error').toLowerCase();
      const kind = status === 'success' || status === 'ok' ? status : status === 'clarify' ? 'clarify' : 'error';
      assistantMessage = {
        id: crypto.randomUUID(),
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

    // mark_region_in_image (or analyze_imagery_vlm, asked the same way)
    // returns a bbox only when the question was about locating something --
    // draw it on whichever slot was actually queried this turn, and clear
    // any earlier one on that same slot when this turn didn't return one.
    if (!networkError) {
      const queriedImagePath = payload.input_file;
      const activeSlot =
        queriedImagePath && queriedImagePath === slotA.uploadedPath
          ? 'A'
          : queriedImagePath && queriedImagePath === slotB.uploadedPath
            ? 'B'
            : null;
      const activeSlotHasManualRoi = activeSlot === 'A' ? !!slotA.roi : activeSlot === 'B' ? !!slotB.roi : false;

      const markResult = (body?.tool_results || []).find(
        (t) => (t.tool === 'mark_region_in_image' || t.tool === 'analyze_imagery_vlm') && Array.isArray(t.result?.bbox)
      );
      // If you already drew your own region for this image, that's the
      // precise, authoritative one -- a separate AI-estimated box for the
      // same image would just be a rougher, possibly conflicting guess
      // fighting for attention with the one you drew.
      const modelBbox = activeSlotHasManualRoi ? null : markResult?.result?.bbox || null;

      if (activeSlot === 'A') setSlotA((prev) => ({ ...prev, modelBbox }));
      else if (activeSlot === 'B') setSlotB((prev) => ({ ...prev, modelBbox }));
    }
  };

  const latestTrace = isRunning
    ? liveSteps
    : [...messages].reverse().find((m) => m.role === 'assistant')?.executionTrace || [];

  return (
    <div className="page">
      <header className="app-header">
        <h1>SatQuery</h1>
        <p>Ask questions about optical, multispectral, or SAR satellite imagery.</p>
        {backendUp === false && <div className="health-warning">Backend not reachable at the configured API URL.</div>}
      </header>

      <div className="app-layout">
        <aside className="image-panel">
          <div className="mode-toggle" role="tablist">
            <button
              type="button"
              className={mode === 'single' ? 'active' : ''}
              onClick={() => handleModeChange('single')}
              disabled={isRunning}
            >
              Single image
            </button>
            <button
              type="button"
              className={mode === 'pair' ? 'active' : ''}
              onClick={() => handleModeChange('pair')}
              disabled={isRunning}
            >
              Two images
            </button>
          </div>

          {mode === 'single' ? (
            <ImageSlot
              label="Image"
              slot={slotA}
              onChange={(patch) => setSlotA((prev) => ({ ...prev, ...patch }))}
              onReset={() => setSlotA(emptySlot())}
              disabled={isRunning}
            />
          ) : (
            <>
              <ImageSlot
                label="Image A (before / reference)"
                slot={slotA}
                onChange={(patch) => setSlotA((prev) => ({ ...prev, ...patch }))}
                onReset={() => setSlotA(emptySlot())}
                disabled={isRunning}
              />
              <ImageSlot
                label="Image B (after / comparison)"
                slot={slotB}
                onChange={(patch) => setSlotB((prev) => ({ ...prev, ...patch }))}
                onReset={() => setSlotB(emptySlot())}
                disabled={isRunning}
              />
              <p className="mode-hint">
                Ask about the change between A and B (e.g. "what changed between these two SAR images"), or ask a
                general question — those are answered using image B.
              </p>
            </>
          )}

          <div className="steps-panel">
            <span className="steps-panel-heading">Steps</span>
            {latestTrace.length > 0 ? (
              <StepTimeline steps={latestTrace} vertical activeLast={isRunning} />
            ) : isRunning ? (
              <p className="steps-panel-empty">Starting…</p>
            ) : (
              <p className="steps-panel-empty">Ask a question to see the steps taken.</p>
            )}
          </div>

          <button type="button" className="btn-link btn-reset" onClick={handleResetConversation} disabled={isRunning}>
            Clear conversation
          </button>
        </aside>

        <main className="chat-panel">
          <div className="chat-log">
            {messages.length === 0 && (
              <div className="chat-empty">Upload an image and ask a question to get started.</div>
            )}
            {messages.map((m) => (
              <ChatMessage key={m.id} message={m} />
            ))}
            {isRunning && (
              <div className="chat-row chat-row-assistant">
                <div className="chat-bubble chat-bubble-assistant chat-typing">Thinking…</div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <form className="chat-input-row" onSubmit={handleSubmit}>
            <textarea
              rows={2}
              placeholder="Ask a question about the image(s)…"
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
            <button type="submit" className="btn-submit" disabled={isRunning || !input.trim()}>
              Send
            </button>
          </form>
        </main>
      </div>
    </div>
  );
}
