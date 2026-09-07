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
| `plan` | `nodes.py` → `handshake.py` / `llm.py` | Classify intent once, build an agenda, emit the next `call_tool` / `clarify` / `chat`. Later hops **do not** re-scan keywords. |
| router | `router.py` | After plan: `call_tool` → `execute`, else `respond`. After advance: more agenda → `plan`, else `respond`. |
| `execute` | `nodes.py` → `executor.py` | Call the tool with **planned trusted args** (T2 dates, file paths). |
| `advance` | `nodes.py` → `handshake.py` | Store T1/T2 paths, Tool 6 alignment gate, Tool 1→3 SAR fallback, step the agenda. |
| `respond` | `nodes.py` | Build `status` + `final_answer` from errors, plan, or the last tool output. |

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

T1 uses `start_date` / `end_date`. T2 uses `post_start_date` / `post_end_date`. Generic Tool 7 stays `threshold_value=0.15` + `bipolar_3class`. Missions keep workflow constants (wildfire `0.10` + 5-class; flood `3.0` dB, no relative % on SAR).

The LLM planner (`SATQUERY_MOCK_PLANNER=false`) is used only for `single_tool` / chat. It cannot override a detected mission or chain.

## Files

| File | Role |
|---|---|
| `graph.py` | Wiring + `invoke_satquery()` (recursion limit for the loop). |
| `state.py` | `SatQueryState` clipboard + `empty_state()`. |
| `handshake.py` | Intent, agenda, T1/T2 dates, LULC clarify, Tool 6 gate, optical→SAR fallback. |
| `registry.py` | Tool names, keywords, location rules, arg builders, success text. |
| `llm.py` | Keyword planner or LLM planner for **single-tool** hops. Never copies model JSON into args. |
| `router.py` | Next-node name after `plan` and after `advance`. |
| `nodes.py` | Node functions. |

Related (outside this folder):

- `backend/main.py` — FastAPI app
- `backend/api/` — request/response models, `/health`, `/api/v1/query`, HTTP status mapping
- `backend/tools/executor.py` — Tools 1–8 plus `workflow_wildfire_burn_severity` / `workflow_flood_inundation_impact` / `workflow_agricultural_drought_canopy_stress`
- `satquery_workflows.py` — Pipeline A/B/C bodies
- `backend/config/settings.py` — planner flags and fetch defaults
- `backend/demo.py` — same graph, no HTTP

## Planner

`SATQUERY_MOCK_PLANNER=true` (default, used in tests) → keyword scan for single-tool queries.

`SATQUERY_MOCK_PLANNER=false` → LLM (`SATQUERY_LLM_PROVIDER` / `_MODEL` / `_BASE_URL` / `_API_KEY`) for single-tool / chat only.

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
