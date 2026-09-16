# SatQuery orchestration layer

This package is the **LangGraph controller** for Tools 1–11 plus named science missions. It has two entry points, not one: an **ingestion graph** that runs once per uploaded file, and a **query graph** that runs once per `POST /api/v1/query`.

It does **not** download rasters itself. Sentinel Hub / Open-Meteo work lives in `Tool_1_…` through `Tool_4_…`. Offline analysis lives in Tools 5–8 and Tool 11. Tavily/DuckDuckGo web search lives in Tool 9; LocationIQ/OpenStreetMap geocoding and POI discovery live in Tool 10. ESA WorldCover / Copernicus DEM are still **user-supplied paths** — the graph never fetches them.

Canonical paths:

```text
POST /api/v1/upload-raster
  → backend/api/routes/uploads.py
  → run_ingest(file_path)                 (backend/orchestrator/ingest_graph.py)
  → backend/tools/executor.py             (inspect_geotiff_metadata, get_place_name_from_coordinates)
  → {"knowledge_base": {...}}  or  400 "Please enter a valid GeoTIFF/TIFF file."

POST /api/v1/query
  → backend/api/routes/query.py
  → invoke_satquery(state)                (backend/orchestrator/graph.py)
  → backend/tools/executor.py
  → Tool_1 … Tool_11  or  satquery_workflows.workflow_*
```

## Graph 1 — upload-time ingestion (`ingest_graph.py`)

```text
START → count_images → inspect_and_validate → (router)
                                                  ├── invalid → END (plain-text error)
                                                  └── valid → extract_fields → resolve_place_name → build_knowledge_base → END
```

| Node | Job |
|---|---|
| `count_images` | Bookkeeping only — the endpoint is one file per call, always `1`. |
| `inspect_and_validate` | Calls `inspect_geotiff_metadata` (Tool 6). Doubles as validation: a non-raster file surfaces as `status: "error"` here (Tool 6's own `rasterio.open()` failure, wrapped by `executor.py`), which becomes the `"Please enter a valid GeoTIFF/TIFF file."` HTTP 400. |
| `extract_fields` | Band names + a centroid `latitude`/`longitude` from `spatial.bounds_wgs84` (`registry.py::derive_grounding_fields`). |
| `resolve_place_name` | Calls `get_place_name_from_coordinates` (`backend/tools/geocode.py`, backed by Tool 10's reverse geocoding). Failure degrades gracefully: `place_name: null`, ingestion still succeeds. |
| `build_knowledge_base` | Assembles `{file_path, bands, latitude, longitude, place_name}`, writes `<file>.kb.json` next to the raster, returns it. |

`run_ingest(file_path) -> {"ok": True, "knowledge_base": {...}} | {"ok": False, "error": "..."}` is the one function `uploads.py` calls.

## Graph 2 — query time (`graph.py`)

```text
START → validate → (router)
                      ├── errors → respond → END
                      └── ok → load_knowledge_base → (router)
                                    ├── no KB   → describe_region_auto → tool_loop → respond → END
                                    └── KB found → vlm_initial_description → describe_region_auto → tool_loop → respond → END
```

| Node | File | Job |
|---|---|---|
| `validate` | `nodes.py` | Check query, bbox, lat/lon. Append `errors`. Any error short-circuits straight to `respond`. |
| `load_knowledge_base` | `nodes.py` | If `input_file` is set, load its sibling `<stem>.kb.json` (written at upload time) onto state. |
| `vlm_initial_description` | `nodes.py` | Only when a knowledge base was found. Calls `analyze_imagery_vlm` with the query *plus* the knowledge base as context, records the result as `initial_description` **and** as the first `tool_results` entry (so the loop below sees it as already-gathered evidence). |
| `describe_region_auto` | `nodes.py` (`describe_region_if_marked`) | Always runs, regardless of whether a knowledge base was found. No-ops unless both `region_bbox` and `input_file` are set on state, in which case it calls `describe_marked_region` (crop + vision + reverse-geocode — see below) exactly once and records it as a `tool_results` entry, same as `vlm_initial_description` does. This exists because leaving it to the tool-loop planner's own judgment was observed to sometimes skip it entirely (the planner decided the whole-image description, or an earlier conversation turn's answer, already covered it) — making it deterministic guarantees a marked region is always actually looked at. |
| `tool_loop` | `tool_loop_graph.py`, embedded via `_tool_loop_node` in `graph.py` | A separate compiled subgraph — see below. |
| `respond` | `nodes.py` | Build `status` + `final_answer` from errors, plan, or the last tool output (now possibly including the initial VLM description and/or the marked-region description). |

### The `tool_loop` subgraph (`tool_loop_graph.py`)

```text
START → llm → (router)
                ├── call_tool → tool → llm   (loop)
                └── clarify / chat / respond_error → END
```

| Node | Job |
|---|---|
| `llm` | Calls `plan_single_tool(state)` (`llm.py` — keyword matcher or a live LLM). Before consulting, checks `tool_hops >= MAX_TOOL_HOPS` (10) and force-stops with `respond_error` if exceeded. |
| `tool` | Dispatches via `execute_tool` + `trusted_args_for_tool`. Records path outputs onto state: `input_file` for fetch/indices/inspect results, `last_change_mask_path` for `analyze_temporal_change`, `bbox`/`latitude`/`longitude` for a successful `inspect_geotiff_metadata` (`derive_grounding_fields`), and — since there's no agenda "role" (t1/t2) any more — a simple first-fetch-is-before/second-fetch-is-after heuristic for `raster_before_path`/`raster_after_path`/`index_before_path`/`index_after_path`. |

This subgraph is embedded in the outer graph through a thin wrapper (`graph.py::_tool_loop_node`), not added directly as a node — a compiled `StateGraph` invoked directly returns its *full* resulting state, and adding it as-is would double-count every `Annotated[list, add]` field (`tool_results`/`errors`/`execution_trace`) it merely inherited from the parent at entry. The wrapper slices each of those fields down to just what the subgraph actually added.

**No more deterministic agenda.** Every request — single-tool, a change-detection chain, or a named mission (wildfire/flood/drought) — goes through this same generic loop; the planner decides each hop for itself, guided by routing hints in `prompts/planner_system.md` (e.g. "a wildfire request needs `raster_before_path`/`raster_after_path` and `lulc_raster_path` before calling `workflow_wildfire_burn_severity` — fetch what's missing first"). This replaced an earlier `handshake.py` module that pre-classified each query into a fixed `Intent` and built a hard-coded step-by-step agenda up front.

Trade-off worth knowing: mission sequencing is now only as reliable as the planner's own reasoning, not a guaranteed fixed order. `enforce_call_tool_location` (`registry.py`) still guards every call — a tool selected before its prerequisites exist is downgraded to `clarify` rather than executed with a missing/hallucinated path — so a premature call fails cleanly, but it does mean the mock/keyword planner (`_keyword_plan`, used in tests) can select a mission tool via keyword match yet can't gather its prerequisites across hops the way a real LLM can; a mock-mode mission request will typically stop at `clarify` rather than complete. `_keyword_plan` also never re-selects a tool it has already attempted in the same request (success or failure) — without that guard it would repeat the same keyword match every hop (the query text never changes) and spin until `MAX_TOOL_HOPS`.

`satquery_workflows.py` is still the **mission engine** (wildfire / flood / drought science constants, fixed internal Tool 2/3/4/5/6/7/8 sequencing) — only *how the orchestrator decides to call it* changed, not what it does once called.

### Marked-region grounding (`region_bbox`)

When the frontend's ROI box is drawn on a rendered image preview, `roiBoxToBbox()`
(`frontend/src/lib/geo.js`) converts it to a real WGS84 bbox using the image's own
`bounds_wgs84` (from `inspect_geotiff_metadata`) and sends it as the request's
`region_bbox` — distinct from `bbox`, which is the whole image's own extent or a
fetch tool's AOI.

1. **`describe_region_auto`** (deterministic, see the Graph 2 table above) crops
   the source GeoTIFF's own pixels to `region_bbox`
   (`render_geotiff_region_preview` in `backend/rendering/raster_preview.py`,
   `rasterio.windows.from_bounds` reprojected into the raster's native CRS,
   clamped to the raster's own extent so a slightly-overshooting box never
   errors), renders just that crop to PNG, and runs the vision model on it —
   `backend/tools/executor.py::_run_describe_region`.
2. The same call also reverse-geocodes the region's own center (`backend/tools/
   geocode.py`, backed by Tool 10) for a verified `place_name`, instead of
   leaving place identification to the vision model's own guess — best-effort,
   never fails the tool call if geocoding is unavailable. Both the attempt and
   its outcome are logged (`[REGION DESCRIBE] reverse geocode center=... 
   place_name=...` on success, `... failed for center=...` on failure) — this
   was previously silent on success, which made a wrong final answer
   undiagnosable from the console alone (see point 5).
3. Any *other* location-based tool consulted afterward (in the same request)
   automatically prefers the marked region over a plain lat/long or the whole
   image's bbox: `fetch_weather_environment` and `get_place_name_from_coordinates`
   use the region's geometric center — the intersection of its two diagonals,
   i.e. the midpoint of its min/max lat and min/max lon
   (`registry.py::_region_center`/`_effective_point`) — and
   `resolve_scene_identity`/`discover_points_of_interest` use `region_bbox`
   itself in place of `bbox` (`registry.py::_effective_bbox`).
4. The planner is told (via `prompts/planner_system.md`) that step 1 already
   happened and is in `tool_results_so_far` — it must not call
   `describe_marked_region` again itself; it only decides whether that result
   alone answers the question or another tool is still needed.
5. **`place_name` beats the vision model's own guess, always.** Both
   `prompts/planner_system.md` (mid-loop "is this enough to finish"
   reasoning) and `prompts/synthesis_system.md` (final-answer narrative) are
   told explicitly: when a result has both a `text` field (a vision model's
   own description, which can name a specific real-world place from visual
   similarity alone) and a `place_name` field (a reverse-geocoded, verified
   lookup), `place_name` is authoritative — never repeat a `text`-guessed
   place name that conflicts with it. This was a real, observed bug: for a
   marked region whose correct reverse-geocoded location was "Vasant Vihar
   Tehsil, New Delhi," the vision model's own guess ("India Gate," several km
   away and outside the marked bbox) won in the final synthesized answer
   because neither prompt said which field to trust when they disagreed.

## Every graph step, on the console and in the frontend

Every node in every graph (query graph, ingest graph, `tool_loop` subgraph) builds its
state update by calling `state.py::trace_entry(node, summary)`. That single function now
does two things, guaranteed in lockstep — a node can't add a step that shows up in one
place but not the other:

1. Logs it immediately: `satquery.graph [STEP] <node>: <summary>` on the console, in
   real time, as each node actually runs (not buffered until the request finishes).
2. Returns the entry that gets appended to `execution_trace` — the same list
   `/api/v1/query/stream` (`backend/api/routes/query.py`) streams one SSE `step` event
   per entry for, live, as each node completes. The frontend's `StepTimeline`
   (`frontend/src/components/StepTimeline.jsx`, driven by `frontend/src/lib
   /executionSteps.js::describeStep`) renders every one of those as a connected step
   node in the left panel — `describeStep` never drops or filters a step; a node it
   doesn't have a specific case for still shows by its raw `node: summary` text rather
   than being silently hidden.

So a live request looks the same in both places, node for node: e.g.
`validate → load_knowledge_base → describe_region_auto → llm → tool → llm → respond`. The
existing more specific log tags (`[REQUEST RECEIVED]`, `[TOOL CALL]`, `[ORCHESTRATOR
DECISION]`, etc., under the `satquery.pipeline`/`satquery.ingest` loggers) are additional
detail alongside the `[STEP]` lines, not a replacement for them.

## Files

| File | Role |
|---|---|
| `graph.py` | Query graph wiring, `_tool_loop_node` wrapper, `invoke_satquery()` (recursion limit for the whole graph — separate from `tool_loop_graph.py`'s own `MAX_TOOL_HOPS`). |
| `ingest_graph.py` | Upload-time graph: validate (via Tool 6), extract bands/lat-long, resolve place name, build `<file>.kb.json`. |
| `tool_loop_graph.py` | The recursive `start → llm → tool → end` subgraph; `MAX_TOOL_HOPS = 10`. |
| `state.py` | `SatQueryState` clipboard + `empty_state()`. Includes `knowledge_base`, `initial_description`, `tool_hops`, `region_bbox`, `geocoded_landmarks`. |
| `registry.py` | Tool names (incl. `get_place_name_from_coordinates`, `mark_region_in_image`, `compare_images_visually`, Tools 9–11's `fetch_web_intelligence`/`geocode_place_to_coordinates`/`resolve_scene_identity`/`discover_points_of_interest`/`deterministic_affine_markup`, and `describe_marked_region`), keywords (now including the 3 mission tools — previously keyword-unreachable), location rules, arg builders, success text, `derive_grounding_fields()`, `_geocoded_features_for_markup()`, and `_effective_point()`/`_effective_bbox()`/`_region_center()` — a marked region's center (the intersection of its diagonals) takes priority over a plain latitude/longitude, and `region_bbox` itself takes priority over the whole image's `bbox`, for any location-based tool (`fetch_weather_environment`, `get_place_name_from_coordinates`, `resolve_scene_identity`, `discover_points_of_interest`) — SAR-aware Tool 7 threshold defaults. |
| `llm.py` | Keyword planner or LLM planner for every hop — no more single-tool-only restriction; mission `workflow_*` tools are LLM-selectable (previously explicitly blocked). The entire system prompt (identity, rules, tool list, routing hints) lives in one editable file, `prompts/planner_system.md` — see `prompts.py`. |
| `prompts.py` / `prompts/*.md` | `load_prompt(name, **placeholders)` reads the planner/synthesis system prompts from editable markdown files (`planner_system.md` — the entire planner prompt, one file; `continuation_suffix.md`; `synthesis_system.md`) so prompt wording can change without touching Python. |
| `router.py` | `route_after_validate`, `route_after_load_kb` for the outer graph. |
| `nodes.py` | `validate_input`, `load_knowledge_base`, `vlm_initial_description`, `respond`. |
| `synthesis.py` | Optional orchestrator-written narrative final answer, now also given `initial_description` as context; falls back to templated text on any failure. |

## Prompt files → code lookup

All LLM-facing prompt wording lives in `prompts/*.md`, not inline Python strings, so it
can be edited without touching code. Each file is read once at import time by
`prompts.py::load_prompt(name, **placeholders)`, which does plain `{{TOKEN}}` string
replacement (not `str.format`) — so a file can contain literal `{`/`}` (e.g. "Set args
to `{}`.") without escaping.

**The planner's entire system prompt is one file, `prompts/planner_system.md`** — identity,
rules, the (auto-generated) tool list, all routing hints, the Skill/SkillRead usage note,
and where the continuation reminder plugs in are all in this single file. There is no
separate SkillKit-only prompt to keep in sync: the same file is used whether or not
SkillKit is active, since it already says how to treat Skill/SkillRead tools if they
happen to be bound.

| Markdown file | Loaded by | Becomes | Used when |
|---|---|---|---|
| `prompts/planner_system.md` | `llm.py` — `load_prompt("planner_system", TOOL_NAMES=, TOOL_LINES=, CONTINUATION_NOTE=)` | `SYSTEM_PROMPT` (no continuation note) and `SYSTEM_PROMPT_WITH_CONTINUATION` (note filled in) — built once at import time, both from this same file | Every planner hop (`_llm_plan`) picks whichever of the two is appropriate: `SYSTEM_PROMPT_WITH_CONTINUATION` once `tool_results` is non-empty (a continuation hop), `SYSTEM_PROMPT` on the first hop. |
| `prompts/continuation_suffix.md` | `llm.py` — `load_prompt("continuation_suffix")` | Filled into `planner_system.md`'s `{{CONTINUATION_NOTE}}` placeholder for `SYSTEM_PROMPT_WITH_CONTINUATION` only | Tells the planner that returning `chat` on a continuation hop means "stop gathering and answer," not "no tool was ever needed" — would be actively misleading on a fresh request, so it's left blank there. |
| `prompts/synthesis_system.md` | `synthesis.py` — `load_prompt("synthesis_system")` | `_SYSTEM_PROMPT` | `synthesize_final_answer()`, only when `SATQUERY_ORCHESTRATOR_PROVIDER` is not `mock` and `SATQUERY_ORCHESTRATOR_SYNTHESIZE_ANSWER=true` (the default). Writes the short narrative final answer from the collected `tool_results`; on any failure it returns `None` and `respond()` falls back to the templated `format_tool_success()` string untouched by this file. Also the rule that a reverse-geocoded `place_name` field beats a vision model's own guessed place name — see "Marked-region grounding" point 5 above. |

None of these files are read per-request — they're loaded once when `llm.py`/`synthesis.py`
are first imported (module load time), so a running process needs a restart to pick up edits.

### SkillKit

`SATQUERY`'s planner can optionally consult **SkillKit** (`langchain-skillkit` on PyPI,
one of `requirements.txt`) for two extra tools, `Skill` and `SkillRead`, bound onto the
LLM client alongside the registered tool schema (`llm.py::_build_llm_client`). `Skill`
loads one of the `SKILL.md` files under `skills/` (each with YAML frontmatter `name` +
`description`) as free-form domain guidance; `SkillRead` reads a reference file scoped to
that skill's own directory. `_build_skillkit()` (cached, `functools.lru_cache`) is silently
`None` — falling back to no skills, not an error — whenever `skills/` doesn't exist or
`langchain_skillkit` fails to import; check `SkillKit disabled: ...` in the logs if skills
aren't showing up. The planner is instructed (in `planner_system.md`) to treat these two
tools as background reference only — never to return `Skill`/`SkillRead` themselves as the
chosen `tool`.

Related (outside this folder):

- `backend/main.py` — FastAPI app
- `backend/api/` — request/response models, `/health`, `/api/v1/query` (+ `/api/v1/query/stream`, SSE — one event per graph node as it completes, then a closing `final` event; response includes `knowledge_base`/`initial_description`), `/api/v1/upload-raster` (now runs `run_ingest` and returns a knowledge base or a plain-text 400), `/api/v1/models`, `/api/v1/raster-preview` + `/api/v1/raster-file`, HTTP status mapping
- `backend/tools/executor.py` — Tools 1–11, `analyze_imagery_vlm` / `mark_region_in_image` / `compare_images_visually` (vision tools, all dispatch through `_run_vlm_analysis`/`_run_visual_compare`), `get_place_name_from_coordinates` (`_run_geocode`), plus `workflow_wildfire_burn_severity` / `workflow_flood_inundation_impact` / `workflow_agricultural_drought_canopy_stress`
- `backend/tools/geocode.py` — `reverse_geocode(latitude, longitude)`, backed by Tool 10's `spatial_geocoding_poi.reverse_geocode()` (LocationIQ, falling back to OpenStreetMap Nominatim)
- `backend/vision/` — vision-tool provider interface + OpenAI / local-model-server backends
- `backend/rendering/raster_preview.py` — GeoTIFF → PNG rendering shared by the raster-preview route and the vision tool
- `satquery_workflows.py` — Pipeline A/B/C bodies
- `backend/config/settings.py` — orchestrator/vision-tool model roles and fetch defaults
- `backend/demo.py` — same graph, no HTTP
- `local_model_server/` — separate service serving InternVL-1B / EarthMind-4B for the vision tool's `local` provider

## Planner

`SATQUERY_ORCHESTRATOR_PROVIDER=mock` (default, used in tests) → keyword scan (`_keyword_plan`) for every hop. Stops re-attempting a tool it has already called once in the same request (success or failure) — see the trade-off note above.

`SATQUERY_ORCHESTRATOR_PROVIDER=openai` or `anthropic` → a live LLM (`SATQUERY_ORCHESTRATOR_MODEL` / `_API_KEY` / `_BASE_URL`, e.g. `gpt-5.2` or `claude-sonnet-5`) for every hop, including mission `workflow_*` tool selection. On a continuation hop (`tool_results` non-empty) it sees `tool_results_so_far` — successes *and* failures — in context, and a "chat" response there is relabeled `finish` (not "no tool was ever needed") so `respond()` falls through to synthesizing from what's already gathered instead of showing a canned reply. When this is enabled, `respond()` also asks the same model to write the final narrative answer (`SATQUERY_ORCHESTRATOR_SYNTHESIZE_ANSWER=true`, the default) instead of the templated `format_tool_success()` string — see `synthesis.py`. `synthesis.py::_extract_text` handles a provider returning content as a list of blocks (e.g. Anthropic extended-thinking models) rather than a plain string — keeps only `text`-type blocks, never the raw thinking block. Synthesis failures fall back to the template; this is a reliability safety net, not a local/API mode switch. Mode selection stays a static per-deployment choice. Note: `ChatAnthropic` is constructed without `temperature` — some Claude models reject it outright.

A separate, independently configurable **vision tool family** (`backend/vision/`) can be called like any other tool to interpret a rendered image on request — `analyze_imagery_vlm` (general description; also the one call `vlm_initial_description` fires automatically per query when a knowledge base is present), `mark_region_in_image` (same, plus an approximate `bbox` when the query asks to locate/mark something — a rough visual estimate, not a dedicated grounding model), `compare_images_visually` (qualitative two-image comparison, no grid-alignment requirement). Backed by an OpenAI vision model or a local model server (InternVL-1B / EarthMind-4B, see `local_model_server/README.md`; `compare` isn't implemented on the local provider). Off by default (`SATQUERY_VISION_TOOL_ENABLED=false`), including the automatic call — a disabled vision tool just fails that one call gracefully (no `initial_description`, the rest of the request proceeds).

Coordinates, dates, CRS, polarization, orbit, bands, size, and file paths always come from the HTTP body (or settings defaults / prior trusted outputs) via `trusted_args_for_tool()`. If a temporal mission/chain needs two scenes and neither files nor post dates exist → **clarify**. If Tool 8 or Pipeline A/B needs LULC and `lulc_raster_path` is empty → **clarify**.

Imagery tools need `bbox`. Weather accepts `bbox` **or** `latitude` + `longitude`.

## Run it

From the SatQuery root (the folder that contains `backend/` and `.env`):

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
curl -s http://127.0.0.1:8000/api/v1/query -H "Content-Type: application/json" -d "{
  \"query\": \"Fetch Sentinel-2 optical imagery for Delhi\",
  \"bbox\": [77.1, 28.5, 77.3, 28.7],
  \"start_date\": \"2025-01-01\",
  \"end_date\": \"2025-01-31\"
}"
```

Without HTTP:

```powershell
.\.venv\Scripts\python.exe -m backend.demo
```

Copy `.env.example` to `.env`. Tools 1–3 need `SENTINEL_CLIENT_ID` / `SENTINEL_CLIENT_SECRET`. Unit tests stub `execute_tool` and never hit live APIs.

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

## HTTP outcomes

JSON `status` is semantic. HTTP codes:

| Graph status | Typical HTTP |
|---|---|
| `success` / `ok` | 200 |
| `clarify` (missing location / mission inputs / LULC) | 400 |
| `error` (bad input / planner reject) | 400 |
| `error` (no matching scene / no weather) | 404 |
| `error` (Sentinel Hub / Open-Meteo failed) | 502 |
| `error` (import / unknown tool / crash) | 500 |

`/api/v1/query/stream` doesn't map status to an HTTP code the same way — the connection
itself is always `200`, and the real semantic `status` (plus `errors`, if any) travels
inside the closing `{"type":"final",...}` SSE event instead.
