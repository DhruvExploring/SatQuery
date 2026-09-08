# SatQuery orchestration layer

This package is the **LangGraph controller** for Tools 1–8 plus named science missions. One `POST /api/v1/query` can **fetch** (Tools 1–4) then **analyze** (Tools 5–8), or delegate to `satquery_workflows.py` for Pipelines A/B/C.

It does **not** download rasters itself. Sentinel Hub / Open-Meteo work lives in `Tool_1_…` through `Tool_4_…`. Offline analysis lives in Tools 5–8. ESA WorldCover / Copernicus DEM are still **user-supplied paths** — the graph never fetches them.

Canonical path:

```text
POST /api/v1/query
  → backend/api/routes/query.py
  → invoke_satquery(state)
  → backend/tools/executor.py
  → Tool_1 … Tool_8  or  satquery_workflows.workflow_*
```

## Graph

Bounded handshake loop (max 10 tool hops):

```text
START → validate → plan → (router) → execute → advance → plan → …
                                              └── respond → END
                            └── respond → END
```

| Node | File | Job |
|---|---|---|
| `validate` | `nodes.py` | Check query, bbox, lat/lon. Append `errors`. |
| `plan` | `nodes.py` → `handshake.py` / `llm.py` | Classify intent once, build an agenda, emit the next `call_tool` / `clarify` / `chat`. Later hops **do not** re-scan keywords. For `single_tool` intent, an exhausted agenda or a failed tool call re-consults the planner instead of stopping — see "Single-tool continuation" below. |
| router | `router.py` | After plan: `call_tool` → `execute`, else `respond`. After advance: more agenda → `plan`, else `respond`. `single_tool` intent is exempt from the "agenda exhausted → respond" shortcut so re-consultation above actually gets a turn. |
| `execute` | `nodes.py` → `executor.py` | Call the tool with **planned trusted args** (T2 dates, file paths). |
| `advance` | `nodes.py` → `handshake.py` | Store T1/T2 paths, Tool 6 alignment gate, Tool 1→3 SAR fallback, step the agenda, `derive_grounding_fields()` (writes a successful `inspect_geotiff_metadata`'s `bbox`/centroid lat-lon back onto state if not already set). For `single_tool` intent, a tool failure or a Tool-6-incompatible pair sets `handshake_complete=False` instead of hard-stopping — mission/chain intents keep the original hard-stop. |
| `respond` | `nodes.py` | Build `status` + `final_answer` from errors, plan, or the last tool output. |

### Single-tool continuation

Only `single_tool` intent gets this — missions/chains keep their original
fixed-length-agenda, hard-stop-on-failure behavior. After a call, the planner may be
re-consulted with `tool_results_so_far` (including a *failed* call's own error
message) in context, and can: gather more grounding before answering (e.g. ground a
vision-model's place guess against `inspect_geotiff_metadata`'s real coordinates), or
recover from a failure by picking a different tool (e.g. `analyze_temporal_change`
fails on grid misalignment → `compare_images_visually` instead). Bounded by the same
10-hop cap.

`satquery_workflows.py` is the **mission engine** (wildfire / flood / drought science constants). The graph only gathers inputs, then calls `workflow_*` once.

## Handshake intents

Classified from `query` **before** single-tool keywords (`"flood"` is Pipeline B, not a lone Tool 3 call):

| Intent | Agenda |
|---|---|
| `mission_wildfire` | Tool 2 T1/T2 if paths missing, then `workflow_wildfire_burn_severity` (needs `lulc_raster_path`) |
| `mission_flood` | Tool 3 T1/T2, then `workflow_flood_inundation_impact` (needs LULC) |
| `mission_drought` | Tool 2 if no `input_file`, then `workflow_agricultural_drought_canopy_stress` |
| `chain_temporal` | Two scenes → Tool 5 each if fetched → Tool 6 → stop if not aligned → Tool 7 → Tool 8 if LULC (`last_change_mask_path` → `zone_mask_path`) |
| `chain_indices` | Tool 2 then Tool 5. Never feed Tool 1 RGB into Tool 5. |
| `single_tool` | Current registry keywords / LLM planner |

T1 uses `start_date` / `end_date`. T2 uses `post_start_date` / `post_end_date`. Generic Tool 7's `threshold_value`, when not given explicitly, is picked by `registry.py::_default_change_threshold` from the file names: `0.15` normally, `3.0` dB if either path contains `"sar"` (SAR backscatter noise alone is several dB — the index-tuned default would flag nearly every pixel "changed"). `bipolar_3class` either way. Missions keep workflow constants (wildfire `0.10` + 5-class; flood `3.0` dB, no relative % on SAR). A `single_tool` change question that fails Tool 6/7 alignment can fall back to `compare_images_visually` instead of erroring (see "Single-tool continuation" above); `chain_temporal` still hard-stops.

The LLM planner (`SATQUERY_ORCHESTRATOR_PROVIDER=openai` or `anthropic`) is used only for `single_tool` / chat. It cannot override a detected mission or chain.

## Files

| File | Role |
|---|---|
| `graph.py` | Wiring + `invoke_satquery()` (recursion limit for the loop). |
| `state.py` | `SatQueryState` clipboard + `empty_state()`. |
| `handshake.py` | Intent, agenda, T1/T2 dates, LULC clarify, Tool 6 gate, optical→SAR fallback, `derive_grounding_fields()`, single-tool failure/exhaustion re-consultation. |
| `registry.py` | Tool names (incl. `mark_region_in_image`, `compare_images_visually`), keywords, location rules, arg builders, success text, SAR-aware Tool 7 threshold default. |
| `llm.py` | Keyword planner or LLM planner for **single-tool** hops. Never copies model JSON into args. On a continuation hop, sees `tool_results_so_far` (successes *and* failures) in context. |
| `router.py` | Next-node name after `plan` and after `advance`. |
| `nodes.py` | Node functions. |
| `synthesis.py` | Optional orchestrator-written narrative final answer; falls back to templated text on any failure. |

Related (outside this folder):

- `backend/main.py` — FastAPI app
- `backend/api/` — request/response models, `/health`, `/api/v1/query` (+ `/api/v1/query/stream`, SSE — one event per graph node as it completes, then a closing `final` event), `/api/v1/upload-raster`, `/api/v1/models`, `/api/v1/raster-preview` + `/api/v1/raster-file`, HTTP status mapping
- `backend/tools/executor.py` — Tools 1–8, `analyze_imagery_vlm` / `mark_region_in_image` / `compare_images_visually` (vision tools, all dispatch through `_run_vlm_analysis`/`_run_visual_compare`), plus `workflow_wildfire_burn_severity` / `workflow_flood_inundation_impact` / `workflow_agricultural_drought_canopy_stress`
- `backend/vision/` — vision-tool provider interface + OpenAI / local-model-server backends
- `backend/rendering/raster_preview.py` — GeoTIFF → PNG rendering shared by the raster-preview route and the vision tool
- `satquery_workflows.py` — Pipeline A/B/C bodies
- `backend/config/settings.py` — orchestrator/vision-tool model roles and fetch defaults
- `backend/demo.py` — same graph, no HTTP
- `local_model_server/` — separate service serving InternVL-1B / EarthMind-4B for the vision tool's `local` provider

## Planner

`SATQUERY_ORCHESTRATOR_PROVIDER=mock` (default, used in tests) → keyword scan for single-tool queries.

`SATQUERY_ORCHESTRATOR_PROVIDER=openai` or `anthropic` → a live LLM (`SATQUERY_ORCHESTRATOR_MODEL` / `_API_KEY` / `_BASE_URL`, e.g. `gpt-5.2` or `claude-sonnet-5`) for single-tool / chat only — including any continuation re-consultation (above). When this is enabled, `respond()` also asks the same model to write the final narrative answer (`SATQUERY_ORCHESTRATOR_SYNTHESIZE_ANSWER=true`, the default) instead of the templated `format_tool_success()` string — see `synthesis.py`. `synthesis.py::_extract_text` handles a provider returning content as a list of blocks (e.g. Anthropic extended-thinking models) rather than a plain string — keeps only `text`-type blocks, never the raw thinking block. Synthesis failures fall back to the template; this is a reliability safety net, not a local/API mode switch. Mode selection stays a static per-deployment choice. Note: `ChatAnthropic` is constructed without `temperature` — some Claude models reject it outright.

A separate, independently configurable **vision tool family** (`backend/vision/`) can be called like any other tool to interpret a rendered image on request — `analyze_imagery_vlm` (general description), `mark_region_in_image` (same, plus an approximate `bbox` when the query asks to locate/mark something — a rough visual estimate, not a dedicated grounding model), `compare_images_visually` (qualitative two-image comparison, no grid-alignment requirement). Backed by an OpenAI vision model or a local model server (InternVL-1B / EarthMind-4B, see `local_model_server/README.md`; `compare` isn't implemented on the local provider). Off by default (`SATQUERY_VISION_TOOL_ENABLED=false`).

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
| `clarify` (missing location / T2 dates / LULC) | 400 |
| `error` (bad input / planner reject) | 400 |
| `error` (no matching scene / no weather) | 404 |
| `error` (Sentinel Hub / Open-Meteo failed) | 502 |
| `error` (import / unknown tool / crash) | 500 |

`/api/v1/query/stream` doesn't map status to an HTTP code the same way — the connection
itself is always `200`, and the real semantic `status` (plus `errors`, if any) travels
inside the closing `{"type":"final",...}` SSE event instead.
