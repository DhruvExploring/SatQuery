import React, { useEffect, useRef, useState } from 'react';
import { checkHealth, runQueryStream } from './api/satqueryApi';
import ChatMessage from './components/ChatMessage';
import ImageSlot from './components/ImageSlot';
import StepTimeline from './components/StepTimeline';
import { roiBoxToBbox } from './lib/geo';
import { inspectGeotiff } from './lib/inspectGeotiff';
import { loadSession, saveSession } from './lib/storage';

const RECAP_PAIR_LIMIT = 2;
const RECAP_ANSWER_CHARS = 320;

// Tool names (canonical + aliases, see backend/orchestrator/registry.py)
// whose success means a *new* GeoTIFF now exists server-side, the same way
// picking a file in ImageSlot does -- this is what lets a query like "give
// me the image of the yamuna river" (no upload at all) result in something
// a follow-up question can actually operate on.
const FETCH_IMAGERY_TOOLS = new Set([
  'fetch_optical_imagery',
  'fetch_satellite_imagery',
  'fetch_multispectral_imagery',
  'fetch_sar_imagery',
  'fetch_sar'
]);

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
  // Deliberately no coordinates here -- the exact bbox is already sent
  // separately as the structured `region_bbox` field (regionBboxFor below,
  // full precision), which is what actually drives the backend's
  // marked-region grounding (describe_marked_region, etc.). Embedding the
  // same rounded numbers as plain query text caused the model to echo this
  // note back verbatim as if it were a verified tool result, even for a
  // later, unrelated question -- e.g. "mark the area with the most
  // vegetation" got answered with the *original* marked region's
  // coordinates, copied from this hint, instead of that turn's own new
  // mark_region_in_image result.
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

/** The marked ROI's real-world bbox, as [min_lon, min_lat, max_lon, max_lat]
 * -- sent to the backend as region_bbox so describe_marked_region can crop
 * the actual GeoTIFF to exactly what the user drew, instead of the model
 * only seeing a natural-language hint about roughly where to look. */
function regionBboxFor(slot) {
  if (!slot?.roi || !slot?.boundsWgs84) return null;
  return bboxObjToArray(roiBoxToBbox(slot.roi, slot.boundsWgs84));
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
    const regionBbox = regionBboxFor(slotA);
    if (regionBbox) payload.region_bbox = regionBbox;
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
  // region_bbox tracks whichever slot input_file actually points at.
  const regionBbox = slotB.uploadedPath ? regionBboxFor(slotB) : regionBboxFor(slotA);
  if (regionBbox) payload.region_bbox = regionBbox;
  return payload;
}

/** The most recent successful fetch_*_imagery result in this turn's
 * tool_results, if any -- a signal that a *new* GeoTIFF now exists
 * server-side, same as picking a file in ImageSlot. */
function latestFetchedImagery(toolResults) {
  const hits = (toolResults || []).filter(
    (t) => FETCH_IMAGERY_TOOLS.has(t.tool) && t.result?.status === 'success' && t.result?.data?.file_path
  );
  return hits[hits.length - 1] || null;
}

/** Adopts a tool-fetched GeoTIFF into a slot exactly as if the user had
 * uploaded it themselves: sets uploadedPath/originalFilename, clears the
 * previous file's now-stale roi/model-marked/knowledge-base fields, then
 * runs the same background inspect_geotiff_metadata call ImageSlot's own
 * upload flow does to populate boundsWgs84/info (the fetch tool's own
 * result doesn't carry bounds in the shape the app needs -- see
 * inspectGeotiff). Without this, "give me the image of X" leaves nothing
 * for a follow-up question to operate on, even though the file now exists.
 * Guards against a slower, now-stale inspect response landing after a newer
 * image has since replaced this one. */
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
    //
    // Drawn regardless of whether a manual ROI also exists on the slot: an
    // earlier version suppressed the AI overlay entirely whenever any manual
    // ROI was present, on the assumption a later question was still "about"
    // that same drawn region. That broke a genuinely new request against the
    // same image (e.g. drawing a region, then later asking to "mark the
    // area with the most vegetation") -- the tool found a real, different
    // location, but it never reached the screen. The two overlays already
    // have distinct styling (dashed green for your drawn ROI, solid violet
    // tagged "AI" for the model's own result) specifically so they don't get
    // confused for each other, so there's no need to hide one in favor of
    // the other -- whichever this turn's tool call actually returned is what
    // gets drawn.
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
      // A polygon (an elongated/curved feature's own path, e.g. a river --
      // see backend/vision/openai_provider.py) is drawn instead of the
      // plain rectangle when present, since it traces the feature itself
      // rather than a loose bounding box around it.
      const modelPolygon = markResult?.result?.polygon || null;

      if (activeSlot === 'A') setSlotA((prev) => ({ ...prev, modelBbox, modelPolygon }));
      else if (activeSlot === 'B') setSlotB((prev) => ({ ...prev, modelBbox, modelPolygon }));

      // A fetch_*_imagery tool just created a new GeoTIFF server-side (e.g.
      // "give me the image of the Yamuna river", with no upload at all) --
      // adopt it as the active image so it renders in the panel and a
      // follow-up question ("mark the vegetation") has an input_file to
      // operate on, instead of only appearing as a passive download link in
      // the chat gallery.
      const latestFetch = latestFetchedImagery(body?.tool_results);
      if (latestFetch) {
        const newPath = latestFetch.result.data.file_path;
        const newName = latestFetch.result.data.file_name || newPath.split('/').pop();
        if (mode === 'single') {
          if (slotA.uploadedPath !== newPath) adoptFetchedImagery(setSlotA, newPath, newName);
        } else if (slotA.uploadedPath !== newPath && slotB.uploadedPath !== newPath) {
          // Two-image mode: fill whichever slot is empty (A before B). If
          // both already hold a file, leave them alone -- overwriting a
          // deliberate before/after comparison would be more surprising
          // than helpful; the fetched file still shows in the chat gallery.
          if (!slotA.uploadedPath) adoptFetchedImagery(setSlotA, newPath, newName);
          else if (!slotB.uploadedPath) adoptFetchedImagery(setSlotB, newPath, newName);
        }
      }
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
