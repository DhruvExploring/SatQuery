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
| `describe_region_auto` | `nodes.py` (`describe_region_if_marked`) | Always runs, regardless of whether a knowledge base was found. No-ops unless both `region_bbox` and `input_file` are set on state, in which case it calls `describe_marked_region` (crop + vision + reverse-geocode — see below) exactly once and records it as a `tool_results` entry, same as `vlm_initial_description` does. This exists because leaving it to the tool-loop planner's own judgment was observed to sometimes skip it entirely (the planner decided the whole-image description, or an earlier conversation turn's answer, already covered it) — making it deterministic guarantees a marked region is always actually looked at. Runs *before* `tool_loop`, so it sees a `region_bbox` that arrived with the request (e.g. from the frontend's drawn ROI) **or** one `vlm_initial_description` just derived from its own automatic call's bbox (see the vision-tool-family paragraph above) — both run ahead of this node in the same graph pass. Only a `region_bbox` derived mid-*tool_loop*, from a planner-chosen `mark_region_in_image` call (see `tool` row below), necessarily post-dates this node; `prompts/planner_system.md` tells the planner to call `describe_marked_region` itself for that specific case instead of assuming it already ran. |
| `tool_loop` | `tool_loop_graph.py`, embedded via `_tool_loop_node` in `graph.py` | A separate compiled subgraph — see below. |
| `respond` | `nodes.py` | Build `status` + `final_answer` from errors, plan, or the last tool output (now possibly including the initial VLM description and/or the marked-region description). For `action == "clarify"`, `final_answer` is the plan's own `reason` verbatim (the planner's specific question back to the user, e.g. "what feature or region would you like to mark?") — no generic tool-list boilerplate appended after it; a fixed fallback string covers the rare case of an empty `reason`. |

### The `tool_loop` subgraph (`tool_loop_graph.py`)

```text
START → llm → (router)
                ├── call_tool → tool → llm   (loop)
                └── clarify / chat / respond_error → END
```

| Node | Job |
|---|---|
| `llm` | Calls `plan_single_tool(state)` (`llm.py` — keyword matcher or a live LLM). Before consulting, checks `tool_hops >= MAX_TOOL_HOPS` (10) and force-stops with `respond_error` if exceeded. |
| `tool` | Dispatches via `execute_tool` + `trusted_args_for_tool`. Records path outputs onto state: `input_file` for fetch/indices/inspect results, `last_change_mask_path` for `analyze_temporal_change`, `bbox`/`latitude`/`longitude` for a successful `inspect_geotiff_metadata` (`derive_grounding_fields`), `region_bbox` (plus `region_polygon`/`region_centroid` when the vision model returned a polygon for an elongated/curved target) for a successful `mark_region_in_image`/`analyze_imagery_vlm` call whose vision-model geometry the executor affine-converted to WGS84 (`backend/tools/executor.py::_geometry_to_region_fields`) — only if `region_bbox` isn't already set, so a user-drawn region always wins over a later AI guess — `bbox` for a successful `geocode_place_to_coordinates` call whose `best_match` carries a real `bounding_box_wgs84` (a river/park/district's own extent from Nominatim/LocationIQ, not a guess) — only if `bbox` isn't already set, making a named-place fetch request (e.g. "give me the image of the Yamuna river") reachable on the next hop instead of dead-ending on a clarify — and, since there's no agenda "role" (t1/t2) any more, a simple first-fetch-is-before/second-fetch-is-after heuristic for `raster_before_path`/`raster_after_path`/`index_before_path`/`index_after_path`. |

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
   `backend/tools/executor.py::_run_describe_region`. When `region_polygon` is
   also present (an elongated/curved feature's own affine-converted path --
   see the vision-tool-family paragraph below and Tool_11's own README §6),
   every pixel outside that path is masked to black first
   (`raster_preview.py::_mask_to_polygon`, given the polygon's WGS84 vertices,
   the raster's native CRS/transform, and the crop window/scale, so it can
   place each vertex in the *output* image's own pixel space) -- `region_bbox`
   still supplies the (inherently rectangular) crop *window*, but the vision
   model only ever sees the polygon's own shape inside it, not the wider
   rectangle a non-rectangular feature's bounding box necessarily includes.
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
   use the region's anchor point (`registry.py::_region_center`/`_effective_point`)
   -- `region_centroid` (an elongated feature's own path centroid: the mean of its
   vertices, appropriate for a *path*, not a filled-area centroid) when a polygon
   was resolved, since `region_bbox`'s own geometric center (the intersection of
   its two diagonals) can land nowhere near a diagonal/curved feature's actual
   course; otherwise that plain bbox midpoint -- and
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
6. **Synthesis must ground numbers in tool output, not in the request's own
   text.** `region_bbox` reaches the backend two ways: the structured field
   (full precision, drives all actual backend behavior) and, previously, a
   plain-text note the frontend appended to the query itself (`App.jsx`'s
   `roiNoteFor`, *"(Focus specifically on the region roughly bounded by
   ...)"*, rounded). A real, observed bug: once a region was marked, that
   same rounded text rode along in *every* later question (recap included,
   since `buildRecap` folds prior turns' full text back in) — so a later,
   unrelated question ("mark the area with the most vegetation") got
   answered with the *original* marked region's coordinates, echoed straight
   from that note, instead of that turn's own new `mark_region_in_image`
   result. Fixed two ways: the frontend note no longer carries coordinates
   at all (§9 of the top-level README) -- nothing functional depended on the
   number being there, only `region_bbox` itself does -- and
   `prompts/synthesis_system.md` now explicitly warns against treating a
   number that merely appears in the user's own request text as if it were a
   verified tool result. Left unchanged: `describe_region_auto` still
   deterministically re-describes the marked region on every hop while
   `region_bbox` is set (point 1 above) — that's still correct; the model
   itself is responsible for recognizing which of possibly several
   tool_results entries (the marked region's own description vs. this
   turn's new finding) actually answers the current question, and is now no
   longer being handed a duplicate, potentially-stale set of numbers in the
   query text to short-circuit that reasoning with.

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
| `state.py` | `SatQueryState` clipboard + `empty_state()`. Includes `knowledge_base`, `initial_description`, `tool_hops`, `region_bbox` (plus `region_polygon`/`region_centroid`, set only when a vision-tool call's marked region was elongated/curved enough to return a polygon), `geocoded_landmarks`. |
| `registry.py` | Tool names (incl. `get_place_name_from_coordinates`, `mark_region_in_image`, `compare_images_visually`, Tools 9–11's `fetch_web_intelligence`/`geocode_place_to_coordinates`/`resolve_scene_identity`/`discover_points_of_interest`/`deterministic_affine_markup`, and `describe_marked_region`), keywords (now including the 3 mission tools — previously keyword-unreachable), location rules, arg builders, success text, `derive_grounding_fields()`, `_geocoded_features_for_markup()`, and `_effective_point()`/`_effective_bbox()`/`_region_center()` — a marked region's center (`region_centroid`, an elongated feature's own path centroid, when set; otherwise `region_bbox`'s plain intersection-of-diagonals midpoint) takes priority over a plain latitude/longitude, and `region_bbox` itself takes priority over the whole image's `bbox`, for any location-based tool (`fetch_weather_environment`, `get_place_name_from_coordinates`, `resolve_scene_identity`, `discover_points_of_interest`) — SAR-aware Tool 7 threshold defaults. |
| `llm.py` | Keyword planner or LLM planner for every hop — no more single-tool-only restriction; mission `workflow_*` tools are LLM-selectable (previously explicitly blocked). The entire system prompt (identity, rules, tool list, routing hints) lives in one editable file, `prompts/planner_system.md` — see `prompts.py`. `resolve_llm_tool()` maps a model-chosen name (or a known alias, e.g. `fetch_satellite_imagery` → `fetch_optical_imagery`) onto a canonical tool via `_LLM_TOOL_ALIASES` or normalized-token matching. `_llm_plan` also recovers when a model puts a resolvable tool name in the `action` field instead of `tool` (the two are separate fields in `_PLAN_SCHEMA`, and not every provider enforces `action`'s enum strictly) — it's treated as `action="call_tool"` for that tool rather than raising `LLM returned unknown action`. |
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
| `prompts/synthesis_system.md` | `synthesis.py` — `load_prompt("synthesis_system")` | `_SYSTEM_PROMPT` | `synthesize_final_answer()`, only when `SATQUERY_ORCHESTRATOR_PROVIDER` is not `mock` and `SATQUERY_ORCHESTRATOR_SYNTHESIZE_ANSWER=true` (the default). Writes the short narrative final answer from the collected `tool_results`; on any failure it returns `None` and `respond()` falls back to the templated `format_tool_success()` string untouched by this file. Also the rule that a reverse-geocoded `place_name` field beats a vision model's own guessed place name — see "Marked-region grounding" point 5 above — and, since point 6, that a number appearing only in the user's own request text (a recap, a marked-region focus note) is never itself a verified tool result. |

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

### Tools never parse natural language themselves — `place_name` / `landmark_names`

The backend always builds a tool's trusted arguments from `state` (bbox, dates, file
paths, credentials), never from whatever the LLM put in its own `args` — this is the
core anti-hallucination guarantee and hasn't changed. But two arguments are inherently
a piece of *extracted meaning* from the user's raw question — "what place name should I
search for," "which landmark(s) did they name" — with no deterministic backend source.
Previously, `geocode_place_to_coordinates`/`resolve_scene_identity` papered over this by
having Tool 10 itself regex-parse the raw query (`_clean_entity_string`,
`_extract_landmarks_from_query` in
`Tool_10_spatial_geocoding_poi/spatial_geocoding_poi.py`) — fragile, and the direct cause
of a real production bug: those regexes collapsed a query like `"give me the image of the
yamuna river"` down to an empty string (the filler-stripping rules weren't anchored to
only match a trailing clause, so they deleted from wherever they first matched to the end
of the string), which fell back to sending the *entire raw sentence* to the geocoder, which
found nothing, which fell through to a third-tier retry that called
`_trim_query_for_fallback` — a function that was referenced but never defined anywhere in
the file, an unconditional `NameError` crash.

The fix moves this extraction to the one place that's actually already read and understood
the query — the LLM planner itself:

- `llm.py::_PLAN_SCHEMA` adds two nullable fields the model fills in directly:
  `place_name` (a clean name, e.g. `"Yamuna River"`, only when `tool` is
  `geocode_place_to_coordinates`) and `landmark_names` (a list of clean names, only when
  `tool` is `resolve_scene_identity` and the question names specific landmark(s)) —
  `prompts/planner_system.md`'s routing hints tell it exactly when and how to populate
  each, and to never hand over the full question text.
- `_llm_plan` injects whichever field the model populated onto a **per-hop copy** of
  state (`{**state, "place_name": ...}`) — never the real graph state, so it can never
  leak into a later, unrelated hop — before calling `trusted_args_for_tool`/
  `enforce_call_tool_location` (both of which rebuild args from state, same as always).
- `registry.py::trusted_args_for_tool`'s `TOOL_GEOCODE_FORWARD` branch reads
  `state.get("place_name") or state.get("query")` (falls back to the raw query only for
  the mock/keyword planner, which has no LLM to do this extraction — a known, pre-existing
  capability gap for that fallback path, not a regression); `TOOL_SCENE_IDENTITY` reads
  `state.get("landmark_names")` directly.
- Tool 10 itself now does **zero** natural-language interpretation: `forward_geocode`
  trusts its `query` argument as already-clean (only `.strip()`, no regex); the dangling
  `_trim_query_for_fallback` call and its whole retry tier were deleted rather than fixed,
  since a caller passing an already-clean name makes that tier unnecessary;
  `resolve_scene_identity` takes an explicit `landmark_names: list[str] | None` parameter
  instead of deriving it from `query` (which it still accepts, but only for
  context/logging, never parsed); `_is_valid_landmark_candidate` lost its
  keyword-matched-against-the-query "did they explicitly ask for a hotel/restaurant/shop"
  override and now filters purely on the geocoder's own structured result metadata
  (class/type/importance) — never on interpreting what the user meant.

Every other tool (1–9, 11) and the vision providers (`backend/vision/`) were already
correct: they either consume already-structured arguments the backend builds from state,
or (the vision tools) hand the full natural-language query straight through to an
LLM/VLM call without any tool-side parsing of their own — confirmed by an explicit
audit before this change, so this fix is scoped to Tool 10 alone, not "every tool."

A separate, independently configurable **vision tool family** (`backend/vision/`) can be called like any other tool to interpret a rendered image on request — `analyze_imagery_vlm` (general description; also the one call `vlm_initial_description` fires automatically per query when a knowledge base is present), `mark_region_in_image` (same, plus where that thing is when the query asks to locate/mark something: a `bbox` for a compact/blob-shaped target, or -- for an elongated/curved one (a river, road, coastline) where a box would include far more area than the feature -- a `polygon` tracing its actual path (its own bounding envelope still also set as `bbox`); its placement is a rough visual estimate either way, not a dedicated grounding model, but its coordinates are then made exact, see below), `compare_images_visually` (qualitative two-image comparison, no grid-alignment requirement). Backed by an OpenAI vision model or a local model server (InternVL-1B / EarthMind-4B, see `local_model_server/README.md`; `compare` isn't implemented on the local provider, and neither is `polygon` -- only the OpenAI provider's schema supports it). Off by default (`SATQUERY_VISION_TOOL_ENABLED=false`), including the automatic call — a disabled vision tool just fails that one call gracefully (no `initial_description`, the rest of the request proceeds).

When the interpreted image is a georeferenced GeoTIFF, `_run_vlm_analysis`
(`backend/tools/executor.py`) affine-converts any returned `bbox`/`polygon` into exact
WGS84 fields via Tool 11's `fractional_bbox_to_wgs84`/`polygon_pixels_to_wgs84`
(`_geometry_to_region_fields` helper, which prefers the polygon's own tighter geometry
whenever both are present) — projecting every corner/vertex through the raster's own
affine transform rather than approximating from the whole scene's `bounds_wgs84`, so a
rotated/skewed transform is still handled correctly. This turns a vision model's visual
guess at *where* something is (and, for a polygon, *what shape* it traces) into an exact
real-world coordinate/path for that guess (the conversion is error-free; the visual
localization it's converting is still only as good as the model's own estimate) —
`region_bbox` always, plus `region_polygon` (the exact path) and `region_centroid` (the
path's own vertex mean, a far more accurate anchor point for an elongated feature than
`region_bbox`'s plain midpoint) whenever a polygon was resolved.

That `region_bbox` (and `region_polygon`/`region_centroid`) gets threaded onto state
from **two separate call sites**, since `analyze_imagery_vlm` runs through two
different code paths depending on when it fires: `tool_loop_graph.py`'s `tool` node for
a planner-chosen call (mid-loop, either `mark_region_in_image` or `analyze_imagery_vlm`),
and `nodes.py::vlm_initial_description` for the one automatic call that fires before the
planner is ever consulted (§2.2) — both call `execute_tool()` directly rather than
sharing a code path, so both independently apply the same "only fill an empty
`region_bbox`" merge. This matters because a query whose wording alone triggers a
bbox/polygon (e.g. "mark the river..." — the shared vision prompt decides this from the
question, not the tool name, see §Vision tool family above) can get its geometry from
that very first automatic call, before `describe_region_auto` even runs — missing the
merge there meant `region_bbox` was silently dropped and the crop/reverse-geocode
pipeline never saw it, even though the executor had already computed it correctly (fixed;
previously only the `tool_loop_graph.py` call site had this merge). Once either site sets
it, `describe_marked_region`/`deterministic_affine_markup` treat a region the AI located
the same way they treat one the user drew — including, when a polygon was resolved,
masking `describe_marked_region`'s crop to that exact path rather than its wider
bounding rectangle (see "Marked-region grounding" above) — see `describe_region_auto`
above and `registry.py`'s row below.

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
