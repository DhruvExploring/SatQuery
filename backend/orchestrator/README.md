# SatQuery orchestration layer

This package is the **LangGraph controller** for Tools 1–4. It turns one HTTP request into a plan, optionally runs a fetch tool, and returns a JSON answer.

It does **not** download rasters itself. Sentinel Hub / Open-Meteo work lives in `Tool_1_…` through `Tool_4_…`. Tools 5–8 and `satquery_server.py` / `satquery_workflows.py` are a separate MCP/science surface and are **not** on this graph.

Canonical path:

```text
POST /api/v1/query
  → backend/api/routes/query.py
  → satquery_graph.invoke(state)
  → backend/tools/executor.py
  → Tool_1 … Tool_4
```

## Graph

```text
START → validate → plan → (router) → execute → respond → END
                            └── respond → END
```

| Node | File | Job |
|---|---|---|
| `validate` | `nodes.py` | Check query, bbox, lat/lon. Append `errors`. |
| `plan` | `nodes.py` → `llm.py` | Choose `call_tool`, `clarify`, `chat`, or `respond_error`. |
| router | `router.py` | `call_tool` + a tool name → `execute`; otherwise `respond`. |
| `execute` | `nodes.py` → `executor.py` | Call the real Python tool with **trusted args**. |
| `respond` | `nodes.py` | Build `status` + `final_answer` from errors, plan, or tool output. |

One tool per request. No checkpointer — each HTTP call is stateless.

## Files

| File | Role |
|---|---|
| `graph.py` | Wiring only. `build_graph()` / `satquery_graph`. |
| `state.py` | `SatQueryState` clipboard + `empty_state()`. |
| `registry.py` | Tool names, keywords, location rules, arg builders, success text. |
| `llm.py` | Keyword planner or LLM planner. Never copies model JSON into args. |
| `router.py` | Deterministic next-node name after `plan`. |
| `nodes.py` | The four node functions. |
| `__init__.py` | Re-exports `build_graph`, `satquery_graph`. |

Related (outside this folder):

- `backend/main.py` — FastAPI app
- `backend/api/` — request/response models, `/health`, `/api/v1/query`, HTTP status mapping
- `backend/tools/executor.py` — name → `fetch_optical_imagery` / `fetch_multispectral_imagery` / `fetch_sar_imagery` / `fetch_weather_environment`
- `backend/config/settings.py` — planner flags and fetch defaults
- `backend/demo.py` — same graph, no HTTP

## Planner

`SATQUERY_MOCK_PLANNER=true` (default, used in tests) → keyword scan.

`SATQUERY_MOCK_PLANNER=false` → LLM (`SATQUERY_LLM_PROVIDER` / `_MODEL` / `_BASE_URL` / `_API_KEY`). On LLM failure, keyword planner is the fallback.

Keyword priority (first match wins):

1. SAR / flood / radar → `fetch_sar_imagery`
2. Weather / rain / climate → `fetch_weather_environment`
3. Vegetation / NDVI / crop health → `fetch_multispectral_imagery`
4. Optical RGB / Sentinel-2 / “show imagery” → `fetch_optical_imagery`

The model may pick **which** tool. Coordinates, dates, CRS, polarization, orbit, bands, and size always come from the HTTP body (or settings defaults) via `trusted_args_for_tool()`. If the chosen tool needs a location that is missing, the plan is downgraded to `clarify`.

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
| `clarify` (missing location) | 400 |
| `error` (bad input / planner reject) | 400 |
| `error` (no matching scene / no weather) | 404 |
| `error` (Sentinel Hub / Open-Meteo failed) | 502 |
| `error` (import / unknown tool / crash) | 500 |
