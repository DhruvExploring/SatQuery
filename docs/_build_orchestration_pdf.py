"""Generate SatQuery orchestration walkthrough PDF. Run from SatQuery/: python docs/_build_orchestration_pdf.py"""

from __future__ import annotations

# Staleness marker — bump and regenerate the PDF after orchestrator/registry changes.
SOURCE_STAMP = (
    "2026-09-06 — LangGraph Tools 1–4 + HTTP 200/400/502/500; "
    "regenerate after orchestrator/registry changes"
)

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT = Path(__file__).resolve().parent / "SatQuery_Orchestration_Guide.pdf"

NAVY = colors.HexColor("#1B3A4B")
TEAL = colors.HexColor("#2A6F7F")
INK = colors.HexColor("#1A1A1A")
MUTED = colors.HexColor("#4A5560")
RULE = colors.HexColor("#D0D5DA")
PALE = colors.HexColor("#F4F7F8")
WARN = colors.HexColor("#8A5A00")
OK = colors.HexColor("#1F6B4A")


def styles():
    base = getSampleStyleSheet()
    s = {
        "cover_kicker": ParagraphStyle(
            "cover_kicker",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=TEAL,
            tracking=1.2,
            spaceAfter=6,
        ),
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=8,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            textColor=MUTED,
            spaceAfter=4,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=NAVY,
            spaceBefore=14,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=15,
            textColor=TEAL,
            spaceBefore=10,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.2,
            textColor=INK,
            alignment=TA_JUSTIFY,
            spaceAfter=7,
        ),
        "hi": ParagraphStyle(
            "hi",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=9.5,
            leading=13.2,
            textColor=MUTED,
            alignment=TA_JUSTIFY,
            spaceAfter=7,
        ),
        "note": ParagraphStyle(
            "note",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=INK,
            backColor=PALE,
            borderPadding=6,
            spaceAfter=8,
        ),
        "cell": ParagraphStyle(
            "cell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=INK,
        ),
        "cell_h": ParagraphStyle(
            "cell_h",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=colors.white,
        ),
        "code": ParagraphStyle(
            "code",
            parent=base["Code"],
            fontName="Courier",
            fontSize=7.5,
            leading=10.5,
            textColor=INK,
            backColor=PALE,
            leftIndent=4,
            rightIndent=4,
            spaceBefore=4,
            spaceAfter=8,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=INK,
            leftIndent=8,
        ),
        "footer": ParagraphStyle(
            "footer",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=MUTED,
        ),
    }
    return s


def P(text: str, style):
    return Paragraph(text.replace("\n", "<br/>"), style)


def table(headers, rows, col_widths):
    s = styles()
    head = [P(h, s["cell_h"]) for h in headers]
    body = [[P(c, s["cell"]) for c in row] for row in rows]
    data = [head] + body
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                ("GRID", (0, 0), (-1, -1), 0.3, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, A4[1] - 12, A4[0], 12, fill=1, stroke=0)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(18 * mm, 10 * mm, "SatQuery — orchestration walkthrough  ·  internal onboarding")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"page {doc.page}")
    canvas.setStrokeColor(RULE)
    canvas.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
    canvas.restoreState()


def bullets(items, s):
    return ListFlowable(
        [ListItem(P(i, s["bullet"]), leftIndent=12, bulletColor=TEAL) for i in items],
        bulletType="bullet",
        start="•",
        leftIndent=10,
        bulletFontName="Helvetica",
        bulletFontSize=9,
        spaceAfter=8,
    )


def build():
    s = styles()
    story = []

    story.append(P("SATQUERY  ·  INTERNAL ONBOARDING", s["cover_kicker"]))
    story.append(P("What is what, and how the orchestration layer actually works", s["cover_title"]))
    story.append(
        P(
            "A senior-to-junior walkthrough of the SatQuery repo: the eight Earth-observation "
            "tools, the LangGraph controller, the FastAPI bridge, and how to test every path "
            "by hand.",
            s["cover_sub"],
        )
    )
    story.append(P("Codebase snapshot: SatQuery / Week-1 orchestrator (Tools 1–4 wired). 5 Sep 2026.", s["cover_sub"]))
    story.append(Spacer(1, 8))
    story.append(
        P(
            "<b>In one line:</b> the user writes a request in plain English. FastAPI receives it as "
            "JSON. LangGraph decides which tool to run. The tool hits the real satellite/weather "
            "API. The response comes back as JSON. Tools 5–8 are science engines that already "
            "exist, but they are not wired into the graph yet.",
            s["hi"],
        )
    )

    # 1
    story.append(P("1. Picture this like a restaurant", s["h1"]))
    story.append(
        P(
            "Thinking of SatQuery as a restaurant removes most of the confusion. "
            "The waiter is FastAPI. The head chef (planner) reads the order and decides "
            "<i>what to cook</i>. The line cooks are Tools 1–8. The pass (respond node) "
            "plates a short English sentence plus the raw kitchen tickets (tool_results). "
            "The dining room never walks into the kitchen — the HTTP layer never does "
            "satellite math itself.",
            s["body"],
        )
    )
    story.append(
        P(
            "This repo actually contains <b>two products sitting next to each other</b>. "
            "Product A is the scientific suite: eight Python engines that fetch Sentinel imagery, "
            "pull ERA5 weather, compute NDVI, check GeoTIFF alignment, detect change, and "
            "profile landcover/terrain. Product B is the Week-1 orchestration layer: a LangGraph "
            "state machine + FastAPI that currently knows how to plan and run only Tools 1–4. "
            "The common junior mistake is reading the README and assuming the graph already "
            "runs all 8 tools. It does not — the graph is currently limited to the fetch layer.",
            s["body"],
        )
    )
    story.append(
        table(
            ["Layer", "Metaphor", "Code", "Allowed to do"],
            [
                [
                    "HTTP",
                    "Waiter",
                    "backend/main.py, backend/api/",
                    "JSON in / JSON out. CORS. Health check. No Sentinel math.",
                ],
                [
                    "Orchestrator",
                    "Head chef + pass",
                    "backend/orchestrator/",
                    "Validate, plan, route, summarise. One tool per request today.",
                ],
                [
                    "Executor",
                    "Ticket to a station",
                    "backend/tools/executor.py",
                    "Name → real Python function for Tools 1–4.",
                ],
                [
                    "Tools 1–4",
                    "Hot line (network)",
                    "Tool_1 … Tool_4 folders",
                    "Download imagery / weather. Needs Sentinel Hub or Open-Meteo.",
                ],
                [
                    "Tools 5–8",
                    "Pastry / butchery (offline)",
                    "Tool_5 … Tool_8 folders",
                    "Local NumPy/Rasterio. Not in the graph yet.",
                ],
                [
                    "MCP + workflows",
                    "Banquet catering",
                    "satquery_server.py, satquery_workflows.py",
                    "Same engines for Claude Desktop or Pipelines A/B/C.",
                ],
            ],
            [28 * mm, 32 * mm, 52 * mm, 63 * mm],
        )
    )

    # 2
    story.append(P("2. What each thing actually is", s["h1"]))
    story.append(P("2.1 The eight scientific tools", s["h2"]))
    story.append(
        P(
            "These tools are independent micro-engines. Each one has its own folder, Pydantic "
            "request model, sample_input.json, and README. The orchestrator imports and calls "
            "them — it never copy-pastes their logic.",
            s["hi"],
        )
    )
    story.append(
        table(
            ["Tool", "Job", "Plain-English intuition", "Network?"],
            [
                [
                    "1 Optical",
                    "Sentinel-2 true-color RGB GeoTIFF + AOI cloud QA (SCL).",
                    "The photo you'd recognize by eye. Recommends a SAR fallback when cloud "
                    "cover is too high.",
                    "Sentinel Hub",
                ],
                [
                    "2 Multispectral",
                    "Calibrated surface-reflectance bands (B02–B12 etc.).",
                    "Raw ingredients for NDVI / NBR — science bands, not a viewable RGB image.",
                    "Sentinel Hub",
                ],
                [
                    "3 SAR",
                    "Sentinel-1 C-band radar in decibels, cloud-penetrating.",
                    "Radar that sees through clouds. Used for flood / monsoon monitoring.",
                    "Sentinel Hub",
                ],
                [
                    "4 Weather",
                    "ERA5 / Open-Meteo temperature, rain, soil moisture, ET0.",
                    "Weather context alongside the satellite data. Does not formally prove "
                    "drought.",
                    "Open-Meteo (no key)",
                ],
                [
                    "5 Indices",
                    "NDVI, EVI, NBR, NDMI… on a local GeoTIFF.",
                    "Turns spectral bands into formulas. Pure computation, no download.",
                    "Offline",
                ],
                [
                    "6 Inspect",
                    "CRS, transform, NoData, pair alignment (rtol 1e-5).",
                    "QA before combining two rasters. A mismatched grid means invalid math.",
                    "Offline",
                ],
                [
                    "7 Change",
                    "T2 − T1 difference raster + integer change_mask.tif.",
                    "Before vs. after. Produces a loss / stable / gain mask.",
                    "Offline",
                ],
                [
                    "8 LULC / terrain",
                    "WorldCover patches, DEM slope, zonal cross-tab of the mask.",
                    "Answers which land-cover class and slope the change actually occurred on.",
                    "Offline",
                ],
            ],
            [28 * mm, 52 * mm, 58 * mm, 37 * mm],
        )
    )
    story.append(Spacer(1, 6))
    story.append(
        P(
            "Tool 7 → Tool 8 handshake: Tool 7 emits change_mask.tif. Tool 8 takes that path as "
            "zone_mask_path and asks: of the pixels that changed, how many were forest vs cropland, "
            "and on what slope? Continuous math (floats) and categorical GIS (integer class codes) "
            "are kept as separate tools for exactly this reason — do not mix them.",
            s["body"],
        )
    )

    story.append(P("2.2 Orchestration files — ownership map", s["h2"]))
    story.append(
        table(
            ["File", "Owns", "Must not own"],
            [
                [
                    "backend/main.py",
                    "App factory, CORS, lifespan (compile graph once).",
                    "Sentinel Hub, Groq, LangGraph internals.",
                ],
                [
                    "backend/api/models.py",
                    "QueryRequest / QueryResponse Pydantic shapes.",
                    "Planning or tool execution.",
                ],
                [
                    "backend/api/routes/query.py",
                    "GET /health, POST /api/v1/query → graph.invoke.",
                    "If / else on SAR vs optical. That is the planner.",
                ],
                [
                    "backend/config/settings.py",
                    "Dates, CRS, orchestrator/vision-tool provider, model, and key.",
                    "Per-request logic.",
                ],
                [
                    "orchestrator/state.py",
                    "SatQueryState clipboard. tool_results and errors use add reducer.",
                    "I/O.",
                ],
                [
                    "orchestrator/graph.py",
                    "START→validate→plan→(router)→execute→respond→END.",
                    "Business logic. Comment in file says wiring only.",
                ],
                [
                    "orchestrator/nodes.py",
                    "validate_input, plan, execute, respond.",
                    "HTTP models.",
                ],
                [
                    "orchestrator/router.py",
                    "call_tool + tool set → execute, else respond.",
                    "Prompts or MCP.",
                ],
                [
                    "orchestrator/llm.py",
                    "Keyword planner OR Groq structured JSON Plan.",
                    "Running tools.",
                ],
                [
                    "tools/executor.py",
                    "Build request objects, call Tool_1..4, wrap errors.",
                    "Choosing which tool. Planner already chose.",
                ],
            ],
            [48 * mm, 72 * mm, 55 * mm],
        )
    )

    story.append(P("2.3 Two other front doors (not FastAPI)", s["h2"]))
    story.append(
        P(
            "<b>satquery_server.py</b> is a FastMCP server. Claude Desktop (or any MCP client) "
            "can call all eight tools over JSON-RPC stdio. This is not an orchestrator — it "
            "wraps the tool functions directly. The calling agent decides which tool to use "
            "and when.",
            s["body"],
        )
    )
    story.append(
        P(
            "<b>satquery_workflows.py</b> holds hard-coded scientific pipelines, not LangGraph: "
            "Pipeline A wildfire (2→5→6→7→8), Pipeline B flood (3→6→7→4→8), Pipeline C drought "
            "(2→5 + 4). This is where the demo/science narrative comes from. The Week-1 graph "
            "does not invoke these directly.",
            s["body"],
        )
    )

    # 3
    story.append(P("3. The clipboard: SatQueryState", s["h1"]))
    story.append(
        P(
            "Every request in LangGraph is a shared dict. Nodes don't return the whole state — "
            "only the fields that changed. tool_results and errors are annotated with "
            "Annotated[..., add], meaning each new list is appended onto the previous one, "
            "never overwritten.",
            s["hi"],
        )
    )
    story.append(
        P(
            "Input side (what the client sends): query, optional bbox [min_lon, min_lat, max_lon, "
            "max_lat], optional latitude/longitude (weather), start_date / end_date, bands, "
            "max_cloud_cover, width/height, SAR polarization / orbit / scene_selection.",
            s["body"],
        )
    )
    story.append(
        P(
            "Working side (what the graph fills in): plan {action, tool, args, reason}, "
            "tool_results [{tool, result}], errors [], final_answer, status. empty_state() "
            "defaults: cloud 30%, 512×512, CRS EPSG:4326, dates 2025-01-01 → 2025-01-31 if "
            "omitted.",
            s["body"],
        )
    )
    story.append(
        P(
            "<b>Common junior mistake:</b> bbox is a separate field in the API body, not part "
            "of the query string. If a user writes 'get me imagery for Delhi' but the JSON has "
            "no bbox, the planner will ask for clarification — the LLM does not geocode a city "
            "name into a bbox in Week-1.",
            s["note"],
        )
    )

    # 4
    story.append(P("4. One request, step by step", s["h1"]))
    story.append(
        P(
            "Example: POST { query: 'Fetch Sentinel-2 optical imagery for Delhi', "
            "bbox: [77.10, 28.50, 77.30, 28.70], start_date: '2025-01-01', end_date: '2025-01-31' }",
            s["body"],
        )
    )

    story.append(P("Step 0 — FastAPI waiter", s["h2"]))
    story.append(
        P(
            "uvicorn backend.main:app. The lifespan hook has already compiled satquery_graph "
            "before the first request. run_query() puts the QueryRequest into empty_state(...) "
            "and runs satquery_graph.invoke(state). An unhandled exception → HTTP 500. Normal "
            "planner/tool failures stay HTTP 200, with status='error' or 'clarify' in the body. "
            "That's intentional: this is an agent protocol, not CRUD.",
            s["body"],
        )
    )

    story.append(P("Step 1 — validate node", s["h2"]))
    story.append(
        bullets(
            [
                "Empty query → error (Pydantic can already return 422 if query is '').",
                "bbox must be 4 numbers, lon ∈ [-180,180], lat ∈ [-90,90], min &lt; max.",
                "latitude / longitude same range checks if present.",
                "This node never runs a tool. It only populates the errors list.",
            ],
            s,
        )
    )

    story.append(P("Step 2 — plan node", s["h2"]))
    story.append(
        P(
            "The plan node only calls make_plan(state). When SATQUERY_ORCHESTRATOR_PROVIDER=mock, "
            "that's the keyword planner. When it's openai or anthropic, ChatOpenAI/ChatAnthropic "
            "(model SATQUERY_ORCHESTRATOR_MODEL, e.g. gpt-5.2) returns structured JSON instead. "
            "If the LLM call fails, it logs a warning and falls back to the keyword planner. The "
            "planner never executes tools itself — it just writes the kitchen ticket.",
            s["body"],
        )
    )
    story.append(P("Keyword planner priority (first match wins):", s["body"]))
    story.append(
        table(
            ["#", "If query contains", "Needs", "Plan"],
            [
                ["1", "sar, radar, sentinel-1, backscatter", "bbox", "call_tool fetch_sar_imagery"],
                [
                    "2",
                    "multispectral, surface reflectance, ndvi, band(s)",
                    "bbox",
                    "call_tool fetch_multispectral_imagery",
                ],
                [
                    "3",
                    "weather, rain, precipitation, temperature, era5, drought, soil moisture…",
                    "bbox or lat+lon",
                    "call_tool fetch_weather_environment",
                ],
                [
                    "4",
                    "optical, imagery, sentinel-2, rgb, geotiff, satellite, fetch, download",
                    "bbox",
                    "call_tool fetch_optical_imagery",
                ],
                ["5", "none of the above", "—", "chat"],
                ["—", "needed location missing", "—", "clarify"],
                ["—", "state.errors already set", "—", "respond_error"],
            ],
            [12 * mm, 62 * mm, 38 * mm, 63 * mm],
        )
    )
    story.append(Spacer(1, 4))
    story.append(
        P(
            "The live LLM planner has to return the same four actions. If action=call_tool "
            "and args come back empty, trusted_args_for_tool fills bbox/dates in from state. "
            "Temperature is 0 — the planner won't write a creative essay.",
            s["body"],
        )
    )

    story.append(P("Step 3 — router (not a node)", s["h2"]))
    story.append(
        P(
            "route_after_plan is a plain function, not a graph node — it's attached via "
            "add_conditional_edges. The rule is small: if plan.action == 'call_tool' AND "
            "plan.tool is truthy → 'execute', otherwise 'respond'. clarify, chat, "
            "respond_error, and a missing tool all skip execute and go straight to respond.",
            s["body"],
        )
    )

    story.append(P("Step 4 — execute node", s["h2"]))
    story.append(
        P(
            "Safety check first: if the plan isn't call_tool, return an error. Otherwise "
            "execute_tool(tool_name, args) runs. The executor builds a Pydantic request "
            "(OpticalSatelliteRequest etc.) and calls the real fetch_* function. ValueError → "
            "validation_error, ImportError → import_error (usually a wrong working directory), "
            "anything else → service_error. An unknown tool name → unknown_tool.",
            s["body"],
        )
    )
    story.append(
        P(
            "<b>Production never uses mock tools.</b> The live server always hits Sentinel / "
            "Open-Meteo. Only pytest, via conftest.py, stubs execute_tool so CI never burns "
            "quota.",
            s["note"],
        )
    )

    story.append(P("Step 5 — respond node", s["h2"]))
    story.append(
        table(
            ["Condition", "status", "final_answer style"],
            [
                ["errors list non-empty", "error", "'Request could not be processed: …'"],
                ["action == clarify", "clarify", "Ask for bbox or lat/lon. Delhi example given."],
                ["action == chat", "ok", "I am SatQuery's controller for Tools 1–4…"],
                ["no tool_results", "error", "No tool output was collected."],
                ["tool status != success", "error", "'{tool} failed: {message}'"],
                ["weather success", "success", "Mean temperature / precipitation one-liners."],
                ["imagery success", "success", "Scene id, cloud cover, GeoTIFF path."],
            ],
            [50 * mm, 28 * mm, 97 * mm],
        )
    )
    story.append(Spacer(1, 6))
    story.append(
        P(
            "The HTTP response always sends { status, final_answer, plan, tool_results, errors }. "
            "The frontend gets the raw tool JSON, not just a sentence — reading plan.reason "
            "should be the first debugging habit a junior engineer builds.",
            s["body"],
        )
    )

    story.append(PageBreak())

    # 5
    story.append(P("5. ASCII of the graph", s["h1"]))
    story.append(
        Preformatted(
            """
  HTTP POST /api/v1/query
           │
           ▼
   empty_state(...)          ← clipboard create
           │
           ▼
      ┌─────────┐
      │ validate│  bbox / lat / query checks
      └────┬────┘
           ▼
      ┌─────────┐
      │  plan   │  keyword OR Groq → Plan
      └────┬────┘
           │
     route_after_plan
        │            │
        │ call_tool  │ clarify / chat / error
        ▼            ▼
   ┌─────────┐   ┌─────────┐
   │ execute │   │ respond │
   └────┬────┘   └────▲────┘
        │             │
        └─────────────┘
              │
              ▼
             END  → QueryResponse JSON
""",
            s["code"],
        )
    )

    # 6
    story.append(P("6. Credentials and flags", s["h1"]))
    story.append(
        P(
            "Copy .env.example → .env. Tools 1–3 need SENTINEL_CLIENT_ID and SENTINEL_CLIENT_SECRET "
            "(Copernicus Data Space / Sentinel Hub). Tool 4 needs nothing. Tools 5–8 need nothing. "
            "Planner: SATQUERY_ORCHESTRATOR_PROVIDER=mock for keywords; openai or anthropic plus "
            "SATQUERY_ORCHESTRATOR_MODEL / _API_KEY for a live LLM. Secrets are never written into "
            "this PDF — never commit your .env file.",
            s["body"],
        )
    )
    story.append(
        P(
            "Checked-in defaults in settings.py: orchestrator provider defaults to mock if the "
            "env var is missing, dates default to Jan 2025, cloud 30%, 512 px, EPSG:4326. Your "
            "local .env might have a live provider enabled instead — so the same curl request "
            "could pick a different tool than the keyword planner would. Always verify plan.tool "
            "when testing.",
            s["hi"],
        )
    )

    # 7
    story.append(P("7. How to test everything by hand", s["h1"]))
    story.append(
        P(
            "There are three separate test ladders below. Don't mix them, or you'll confuse "
            "'the API failed' with 'Sentinel quota exhausted' with 'the planner picked the "
            "wrong tool'.",
            s["hi"],
        )
    )

    story.append(P("Ladder A — unit tests (no network, stubbed tools)", s["h2"]))
    story.append(
        Preformatted(
            "cd D:\\downloads\\satquery\\SatQuery\n"
            "pytest -q\n"
            "# or targeted:\n"
            "pytest tests/test_router.py tests/test_api.py tests/test_graph_mock.py -q",
            s["code"],
        )
    )
    story.append(
        P(
            "conftest.py forces SATQUERY_ORCHESTRATOR_PROVIDER=mock, replaces make_plan with "
            "_keyword_plan, and makes execute_tool return fake success JSON (scene_id "
            "S2_OPTICAL_MOCK etc.). So a green pytest run means: graph wiring, routing, and HTTP "
            "shapes are correct — it does not mean Sentinel actually works.",
            s["body"],
        )
    )
    story.append(
        bullets(
            [
                "GET /health → {status: ok}",
                "Optical / SAR / weather queries → plan.tool correct, status success",
                "Missing bbox → status clarify",
                "bbox longitude 200 → status error, tool_results empty",
                "query '' → HTTP 422 (Pydantic)",
                "Unrelated query → action chat, status ok",
            ],
            s,
        )
    )

    story.append(P("Ladder B — live FastAPI (real Tools 1–4)", s["h2"]))
    story.append(
        P(
            "Terminal 1 — server. The working directory must be the SatQuery/ project root so "
            "the Tool_* imports resolve.",
            s["body"],
        )
    )
    story.append(
        Preformatted(
            "cd D:\\downloads\\satquery\\SatQuery\n"
            "uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000",
            s["code"],
        )
    )
    story.append(
        P(
            "Browser: http://127.0.0.1:8000/docs (Swagger — the easiest manual UI). "
            "http://127.0.0.1:8000/redoc is also available. Health: http://127.0.0.1:8000/health",
            s["body"],
        )
    )
    story.append(P("B0. Health (5 seconds)", s["h2"]))
    story.append(
        Preformatted(
            "curl http://127.0.0.1:8000/health",
            s["code"],
        )
    )
    story.append(P('Expect: {"status":"ok"}', s["body"]))

    story.append(P("B1. Clarify path — imagery without bbox (no Sentinel call)", s["h2"]))
    story.append(
        Preformatted(
            "curl -s http://127.0.0.1:8000/api/v1/query -H \"Content-Type: application/json\" -d "
            "\"{\\\"query\\\":\\\"Fetch Sentinel-2 optical imagery for Delhi\\\"}\"",
            s["code"],
        )
    )
    story.append(
        P(
            "Expect status=clarify, tool_results=[], and final_answer asking for a location. "
            "If a tool actually runs here, the planner's bbox check is broken.",
            s["body"],
        )
    )

    story.append(P("B2. Chat path — unrelated (no Sentinel call)", s["h2"]))
    story.append(
        Preformatted(
            "curl -s http://127.0.0.1:8000/api/v1/query -H \"Content-Type: application/json\" -d "
            "\"{\\\"query\\\":\\\"What is the capital of France?\\\"}\"",
            s["code"],
        )
    )
    story.append(P("Expect plan.action=chat, status=ok.", s["body"]))

    story.append(P("B3. Validation error — illegal bbox (no Sentinel call)", s["h2"]))
    story.append(
        Preformatted(
            "curl -s http://127.0.0.1:8000/api/v1/query -H \"Content-Type: application/json\" -d "
            "\"{\\\"query\\\":\\\"Fetch Sentinel-2 optical imagery for Delhi\\\",\\\"bbox\\\":[200,28.5,77.3,28.7]}\"",
            s["code"],
        )
    )
    story.append(P("Expect status=error, errors mentioning longitude range, tool_results empty.", s["body"]))

    story.append(P("B4. Empty query — HTTP layer", s["h2"]))
    story.append(
        Preformatted(
            "curl -i http://127.0.0.1:8000/api/v1/query -H \"Content-Type: application/json\" -d "
            "\"{\\\"query\\\":\\\"\\\"}\"",
            s["code"],
        )
    )
    story.append(P("Expect HTTP 422 Unprocessable Entity. The request never reaches the graph.", s["body"]))

    story.append(P("B5. Live optical (Tool 1) — Sentinel Hub, ~5–20 s", s["h2"]))
    story.append(
        Preformatted(
            "curl -s http://127.0.0.1:8000/api/v1/query -H \"Content-Type: application/json\" -d \"{\n"
            "  \\\"query\\\": \\\"Fetch Sentinel-2 optical imagery for Delhi\\\",\n"
            "  \\\"bbox\\\": [77.10, 28.50, 77.30, 28.70],\n"
            "  \\\"start_date\\\": \\\"2025-01-01\\\",\n"
            "  \\\"end_date\\\": \\\"2025-01-31\\\"\n"
            "}\"",
            s["code"],
        )
    )
    story.append(
        bullets(
            [
                "plan.tool = fetch_optical_imagery, action = call_tool",
                "status = success (or error with Sentinel message if creds/quota/scene fail)",
                "tool_results[0].result.data.file_path → sih_satellite_data/*.tif",
                "final_answer scene id + cloud cover + path",
            ],
            s,
        )
    )

    story.append(P("B6. Live multispectral (Tool 2)", s["h2"]))
    story.append(
        P(
            "Same bbox/dates, but write 'multispectral' or 'NDVI' in the query. The keyword "
            "planner matches multispectral before optical. Expect "
            "plan.tool=fetch_multispectral_imagery. Optional: "
            "\"bands\": [\"B02\",\"B03\",\"B04\",\"B08\"].",
            s["body"],
        )
    )

    story.append(P("B7. Live SAR (Tool 3)", s["h2"]))
    story.append(
        P(
            "Query: 'Download SAR radar imagery for Mumbai' with bbox [72.8, 18.9, 73.0, 19.1]. "
            "Optional polarization [\"VV\",\"VH\"], orbit_direction BOTH. Cloud cover is "
            "irrelevant — it's radar. The output file should be a FLOAT32 dB GeoTIFF.",
            s["body"],
        )
    )

    story.append(P("B8. Live weather (Tool 4) — Open-Meteo only, ~1 s", s["h2"]))
    story.append(
        Preformatted(
            "curl -s http://127.0.0.1:8000/api/v1/query -H \"Content-Type: application/json\" -d \"{\n"
            "  \\\"query\\\": \\\"Get weather and rainfall for this location\\\",\n"
            "  \\\"latitude\\\": 28.61,\n"
            "  \\\"longitude\\\": 77.21,\n"
            "  \\\"start_date\\\": \\\"2025-01-01\\\",\n"
            "  \\\"end_date\\\": \\\"2025-01-31\\\"\n"
            "}\"",
            s["code"],
        )
    )
    story.append(
        P(
            "Passing a bbox instead of lat/lon also works. Sentinel credentials are not needed "
            "for this test. Expect observed_metrics.temperature_2m_mean_c and "
            "precipitation_sum_mm in tool_results.",
            s["body"],
        )
    )

    story.append(P("B9. Graph without HTTP — backend/demo.py", s["h2"]))
    story.append(
        Preformatted(
            "cd D:\\downloads\\satquery\\SatQuery\npython -m backend.demo",
            s["code"],
        )
    )
    story.append(
        P(
            "This skips FastAPI entirely and calls satquery_graph.invoke directly. If the demo "
            "works but /query fails, the problem is in the HTTP layer. If it's the other way "
            "around, look at routing vs. the uvicorn working directory.",
            s["body"],
        )
    )

    story.append(P("Ladder C — scientific tools outside the graph", s["h2"]))
    story.append(
        P(
            "Tools 5–8 don't run through FastAPI. Test them via each folder's sample JSON, "
            "notebooks, or the phase runner scripts.",
            s["body"],
        )
    )
    story.append(
        Preformatted(
            "cd D:\\downloads\\satquery\\SatQuery\n"
            "python scripts/run_phase2.py\n"
            "# offline synthetic harness + Pipelines A/B/C\n"
            "python scripts/test_phase2_integration.py\n"
            "python scripts/verify_all_tools.py",
            s["code"],
        )
    )
    story.append(
        P(
            "Per-tool pattern: each Tool_N folder goes sample_input.json → function → "
            "sample_output.json shape. After a live fetch, feed Tool 5 the downloaded "
            "multispectral path, check alignment with Tool 6, run Tool 7 on the indices from "
            "two dates, then Tool 8 on the mask plus LULC/DEM. This is the full end-to-end "
            "science path — the Week-1 /query endpoint does not chain it automatically.",
            s["body"],
        )
    )

    story.append(P("Ladder D — MCP server (optional)", s["h2"]))
    story.append(
        Preformatted("python satquery_server.py", s["code"])
    )
    story.append(
        P(
            "A stdio MCP process. Configure command/args/env in the Claude Desktop config. "
            "Manual test: use the MCP inspector, or ask Claude to 'fetch optical for this "
            "bbox'. This is a door parallel to the graph, not a replacement for it.",
            s["body"],
        )
    )

    story.append(P("PowerShell note (Windows)", s["h2"]))
    story.append(
        P(
            "PowerShell aliases curl to Invoke-WebRequest. Use this recipe instead:",
            s["body"],
        )
    )
    story.append(
        Preformatted(
            "Invoke-RestMethod -Uri http://127.0.0.1:8000/health\n\n"
            '$body = @{\n'
            '  query      = "Fetch Sentinel-2 optical imagery for Delhi"\n'
            '  bbox       = @(77.10, 28.50, 77.30, 28.70)\n'
            '  start_date = "2025-01-01"\n'
            '  end_date   = "2025-01-31"\n'
            '} | ConvertTo-Json\n'
            "Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/query -Method Post "
            "-ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 12",
            s["code"],
        )
    )

    # 8
    story.append(P("8. What 'end to end' means today vs later", s["h1"]))
    story.append(
        table(
            ["Journey", "Today", "How you test it"],
            [
                [
                    "NL → fetch optical TIFF",
                    "Yes, via /api/v1/query",
                    "B5 curl / Swagger",
                ],
                [
                    "NL → multi / SAR / weather",
                    "Yes",
                    "B6–B8",
                ],
                [
                    "NL → NDVI → change → LULC report",
                    "No (graph is single-tool, Tools 5–8 unwired)",
                    "Manual Python or satquery_workflows.py",
                ],
                [
                    "Optical cloudy → auto SAR fallback",
                    "Spec'd, not in Week-1 graph",
                    "Call Tool 1 then Tool 3 yourself",
                ],
                [
                    "React UI",
                    "CORS allows 3000/5173; no frontend in repo",
                    "API only until UI exists",
                ],
            ],
            [48 * mm, 62 * mm, 65 * mm],
        )
    )

    # 9
    story.append(P("9. Debugging cheatsheet", s["h1"]))
    story.append(
        table(
            ["Symptom", "Likely cause", "What to look at"],
            [
                [
                    "status clarify though you named Delhi",
                    "bbox field missing",
                    "JSON body. Query text is not geocoded.",
                ],
                [
                    "Wrong tool (optical instead of SAR)",
                    "Keyword order / LLM drift",
                    "plan.reason. Set SATQUERY_ORCHESTRATOR_PROVIDER=mock to lock in keyword "
                    "routing.",
                ],
                [
                    "import_error in tool_results",
                    "Wrong working directory",
                    "Run uvicorn from SatQuery/, not parent.",
                ],
                [
                    "service_error / 401 from Sentinel",
                    "Bad or missing .env credentials",
                    "SENTINEL_CLIENT_ID / SECRET. Never log them.",
                ],
                [
                    "pytest green, live curl fails",
                    "Expected: tests stub tools",
                    "Live path needs creds + network.",
                ],
                [
                    "HTTP 500",
                    "Unhandled exception in graph",
                    "uvicorn traceback. Planner/tool errors should be 200.",
                ],
                [
                    "Weather works, imagery fails",
                    "Open-Meteo vs Sentinel Hub",
                    "Tool 4 has no key. Tools 1–3 do.",
                ],
            ],
            [52 * mm, 55 * mm, 68 * mm],
        )
    )

    story.append(P("10. Mental model to remember tomorrow", s["h1"]))
    story.append(
        P(
            "1) User intent is a string; geometry is a separate field. 2) The planner decides, "
            "the executor runs, respond speaks. 3) The router is just a yes/no on whether to "
            "execute. 4) One request, one tool — there is no loop in Week-1. 5) The 8 science "
            "engines already exist; the controller is currently just a waiter for the first 4 "
            "fetch tools. 6) Test three ways: pytest (the brain), curl/Swagger (brain + hands + "
            "network), run_phase2 (the science kitchen).",
            s["body"],
        )
    )
    story.append(
        P(
            "When someone asks 'where is the orchestration?' — the answer is: "
            "backend/orchestrator/graph.py is the wiring, nodes.py is the behavior, llm.py is "
            "the decision-making, executor.py is the hands, and query.py is the doorbell. "
            "Remember that much, and you own the system instead of just visiting it.",
            s["hi"],
        )
    )

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="SatQuery orchestration walkthrough",
        author="SatQuery onboarding",
    )
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    build()
