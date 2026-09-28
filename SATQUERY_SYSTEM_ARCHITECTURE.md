# SatQuery Geospatial Intelligence Suite — Visual Architecture Guide

> **Interactive Reference Architecture for Frontend, Backend, LangGraph, and Orchestration Systems**

---

## 1. System Overview & End-to-End Architecture

**SatQuery** is an autonomous Earth Observation (EO) and geospatial intelligence platform. It transforms raw satellite imagery (Sentinel-2, Sentinel-1 SAR), meteorological data (Open-Meteo, ERA5), and global terrain rasters into interactive intelligence reports through agentic reasoning and computer vision.

### 1.1 High-Level Architecture Diagram

```mermaid
flowchart TB
    %% Styling Definitions
    classDef clientStyle fill:#e0f2fe,stroke:#0284c7,stroke-width:2px,color:#0f172a,rx:8px,ry:8px;
    classDef apiStyle fill:#f3e8ff,stroke:#9333ea,stroke-width:2px,color:#0f172a,rx:8px,ry:8px;
    classDef graphStyle fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#0f172a,rx:8px,ry:8px;
    classDef toolStyle fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#0f172a,rx:8px,ry:8px;
    classDef cloudStyle fill:#fee2e2,stroke:#dc2626,stroke-width:2px,color:#0f172a,rx:8px,ry:8px;

    subgraph Tier1 ["🖥️ Tier 1: Frontend User Experience (React + Vite)"]
        UI["Interactive Dashboard<br/><i>(App.jsx)</i>"]
        VIEWER["Dual Raster Canvas & ROI Selector<br/><i>(ImageSlot.jsx)</i>"]
        COMPARE["Swipe & Flicker Comparison<br/><i>(TemporalComparisonViewer.jsx)</i>"]
        SPECTRAL["Multi-Band Spectral Inspector<br/><i>(SpectralInspector.jsx)</i>"]
        TIMELINE["Real-Time Execution Timeline<br/><i>(StepTimeline.jsx)</i>"]
    end

    subgraph Tier2 ["⚡ Tier 2: FastAPI Gateway & Streaming Bridge"]
        GATEWAY["API Gateway & Lifespan Controller<br/><i>(main.py)</i>"]
        STREAMER["Server-Sent Events (SSE) Engine<br/><i>(/api/v1/query/stream)</i>"]
        UPLOADER["Chunked Raster Ingest & Storage<br/><i>(/api/v1/upload-raster)</i>"]
        RENDERER["Dynamic GeoTIFF Preview Renderer<br/><i>(raster_preview.py)</i>"]
    end

    subgraph Tier3 ["🧠 Tier 3: LangGraph Autonomous Core"]
        INGEST_G["Upload Ingestion Pipeline<br/><i>(ingest_graph.py)</i>"]
        QUERY_G["Query Orchestration Workflow<br/><i>(graph.py)</i>"]
        LOOP_G["Dynamic Tool-Loop Subgraph<br/><i>(tool_loop_graph.py)</i>"]
        PLANNER["LLM Planner & Semantic Parser<br/><i>(llm.py)</i>"]
        SYNTH["Intelligence Synthesis Engine<br/><i>(synthesis.py)</i>"]
    end

    subgraph Tier4 ["🔬 Tier 4: Geospatial Tool Engines & Vision Models"]
        EO_TOOLS["Satellite Ingestion Suite<br/><i>(Tools 1–3: Optical, Multispectral, SAR)</i>"]
        ENV_TOOLS["Weather & Hydrology Engine<br/><i>(Tool 4: Open-Meteo & ERA5)</i>"]
        INDEX_TOOLS["Vectorized Biophysical Engines<br/><i>(Tools 5–8: Indices, QA, Change, GIS)</i>"]
        GEO_TOOLS["Geocoding & Affine Math<br/><i>(Tools 9–11: Web Intel, POI, Affine)</i>"]
        VLM_MODELS["Computer Vision Interpreters<br/><i>(Anthropic Claude / InternVL)</i>"]
    end

    subgraph Tier5 ["🛰️ Tier 5: External Providers & Remote Data Sources"]
        SENTINEL["Copernicus Sentinel Hub<br/><i>(Sentinel-2 L2A & Sentinel-1 GRD)</i>"]
        METEO["Open-Meteo & ECMWF<br/><i>(ERA5 Reanalysis Time-Series)</i>"]
        TAVILY["Tavily Web Intelligence<br/><i>(Ground-Truth Disaster Reports)</i>"]
        OSM["LocationIQ & OpenStreetMap<br/><i>(Nominatim Reverse Geocoding)</i>"]
    end

    %% Inter-Tier Connections
    Tier1 -->|1. HTTP / SSE Stream| Tier2
    Tier2 -->|2. Invoke Ingestion Graph| INGEST_G
    Tier2 -->|3. Stream Query Execution| QUERY_G
    QUERY_G -->|4. Coordinate Decision Loop| LOOP_G
    LOOP_G <-->|5. Step-by-Step Reasoning| PLANNER
    LOOP_G -->|6. Execute Trusted Tools| Tier4
    Tier4 -->|7. Query Remote Satellite APIs| Tier5
    Tier4 -->|8. Raw Products & Telemetry| Tier3
    QUERY_G -->|9. Generate Final Narrative| SYNTH
    Tier3 -->|10. SSE Steps & Artifacts| Tier2
    Tier2 -->|11. Live Updates to Client| Tier1

    %% Apply Styles
    class UI,VIEWER,COMPARE,SPECTRAL,TIMELINE clientStyle;
    class GATEWAY,STREAMER,UPLOADER,RENDERER apiStyle;
    class INGEST_G,QUERY_G,LOOP_G,PLANNER,SYNTH graphStyle;
    class EO_TOOLS,ENV_TOOLS,INDEX_TOOLS,GEO_TOOLS,VLM_MODELS toolStyle;
    class SENTINEL,METEO,TAVILY,OSM cloudStyle;
```

---

### 1.2 End-to-End Data Journey (Step-by-Step Flowchart)

```mermaid
flowchart LR
    classDef stepStyle fill:#ffffff,stroke:#3b82f6,stroke-width:2px,color:#1e293b,rx:6px,ry:6px;
    classDef actStyle fill:#eff6ff,stroke:#2563eb,stroke-width:2px,color:#1e3a8a,rx:6px,ry:6px;

    subgraph Step1 ["Step 1: User Request"]
        A1["User inputs prompt:<br/>'Detect forest loss in AOI'"] --> A2["(Optional) Draws ROI Box<br/>on satellite canvas"]
    end

    subgraph Step2 ["Step 2: Stream Dispatch"]
        B1["POST /api/v1/query/stream"] --> B2["SSE Stream Opened<br/>Client connects live"]
    end

    subgraph Step3 ["Step 3: Agentic Reasoning"]
        C1["Planner chooses Tool<br/>(e.g. compute_vegetation_indices)"] --> C2["Backend builds Trusted Args<br/>(BBox, Dates, Filepaths)"]
        C2 --> C3["Executor runs Python engine"]
    end

    subgraph Step4 ["Step 4: Output Synthesis"]
        D1["SSE delivers live step pulses<br/>StepTimeline lights up"] --> D2["Generated GeoTIFF displayed<br/>in comparison viewer"]
        D2 --> D3["Narrative intelligence briefing<br/>rendered in chat"]
    end

    Step1 --> Step2 --> Step3 --> Step4

    class A1,A2,B1,B2,C1,C2,C3,D1,D2,D3 stepStyle;
```

---

### 1.3 Core System Design Contracts

| Contract Principle | What It Does | Why It Matters | Implementation File |
| :--- | :--- | :--- | :--- |
| **Separation of Concerns** | Decouples satellite fetchers, offline numpy math, GIS engines, and web search. | Modular testing; offline engines run without internet or API keys. | [backend/tools/executor.py](file:///Users/shrishtigaur/Documents/SatQuery-main/backend/tools/executor.py) |
| **Anti-Hallucination Guard** | Models choose *what* tool to run, but backend supplies the real coordinates, file paths, and dates. | Eliminates fabricated bounding boxes and invalid filepaths. | [backend/orchestrator/registry.py](file:///Users/shrishtigaur/Documents/SatQuery-main/backend/orchestrator/registry.py) |
| **Deterministic Grounding** | Applies closed-form affine matrix math to project vision model pixels to real WGS84 lat/long. | Replaces approximate AI visual guesses with sub-millimeter geographic accuracy. | [Tool_11_deterministic_affine_markup](file:///Users/shrishtigaur/Documents/SatQuery-main/Tool_11_deterministic_affine_markup) |
| **The Handshake Protocol** | Continuous differential rasters ($\Delta = T_2 - T_1$) feed directly into discrete categorical GIS models. | Seamlessly answers: *"How many square kilometers of cropland were flooded?"* | [AGENT_WORKFLOW_AND_INTEGRATION_SPEC.md](file:///Users/shrishtigaur/Documents/SatQuery-main/AGENT_WORKFLOW_AND_INTEGRATION_SPEC.md) |
| **Ground Truth Precedence** | Real reverse-geocoded place names strictly override vision model guesses. | Guarantees place name correctness in final synthesized reports. | [backend/orchestrator/synthesis.py](file:///Users/shrishtigaur/Documents/SatQuery-main/backend/orchestrator/synthesis.py) |

---

## 2. Frontend Architecture (`frontend/`)

The frontend is an interactive geospatial analyst workbench built with **React 18** and **Vite**, styled using a bespoke **Vanilla CSS design system** ([index.css](file:///Users/shrishtigaur/Documents/SatQuery-main/frontend/src/index.css)).

### 2.1 Workspace Layout & Visual Organization

```mermaid
flowchart TD
    classDef panelStyle fill:#f8fafc,stroke:#64748b,stroke-width:2px,color:#0f172a,rx:8px,ry:8px;
    classDef subStyle fill:#ffffff,stroke:#94a3b8,stroke-width:1px,color:#334155,rx:4px,ry:4px;

    subgraph Screen ["🖥️ Analyst Workspace View (App.jsx)"]
        HEADER["Top Navigation Bar: System Health Status · Orchestrator Model Badge · Single / Pair Mode Switcher"]
        
        subgraph StageArea ["Left Panel: Visual Stage (60% Width)"]
            SLOT_VIEW["Dual Raster Stages (ImageSlot A / ImageSlot B)<br/>• Interactive Canvas ROI Drag-to-Select<br/>• Full-Resolution GeoTIFF Visualizer<br/>• Metadata Badges (CRS, GSD, Pixel Size)"]
            CAROUSEL["Generated Product Carousel (ImageHistoryToggle)<br/>• Thumbnail history of all generated/uploaded rasters<br/>• 1-Click activation of prior outputs into Stage"]
        end

        subgraph ChatArea ["Right Panel: Agent Chat & Timeline (40% Width)"]
            MSG_FEED["Chat Stream (ChatMessage.jsx)<br/>• Rich Markdown with Mathematical Formulas<br/>• Tool Execution Result Badges<br/>• Direct Links to Generated GeoTIFFs"]
            LIVE_TIMELINE["Live Workflow Timeline (StepTimeline.jsx)<br/>• Real-time SSE node status indicators<br/>• Node execution duration in milliseconds"]
            INPUT_BOX["Interactive Query Input Bar<br/>• Prompt input with automatic ROI context chip<br/>• Quick Workflow Mission Presets button"]
        end

        subgraph Overlays ["Modal Dialogs & Slide-Out Panels"]
            MODAL_PRESET["Mission Presets Launcher (WorkflowPresets.jsx)"]
            MODAL_SPECTRAL["Spectral Band & Index Inspector (SpectralInspector.jsx)"]
            MODAL_FULLSCREEN["Full-Resolution Pan & Zoom Modal (RasterModal.jsx)"]
            DRAWER_LOGS["Telemetry & Knowledge Base Explorer (DetailedLogsSidebar.jsx)"]
        end

        HEADER --> StageArea & ChatArea
        StageArea -.-> Overlays
        ChatArea -.-> Overlays
    end

    class Screen,StageArea,ChatArea,Overlays panelStyle;
    class HEADER,SLOT_VIEW,CAROUSEL,MSG_FEED,LIVE_TIMELINE,INPUT_BOX,MODAL_PRESET,MODAL_SPECTRAL,MODAL_FULLSCREEN,DRAWER_LOGS subStyle;
```

---

### 2.2 Mouse ROI Selection to Geographic Coordinate Flowchart

```mermaid
flowchart LR
    classDef mathStyle fill:#eff6ff,stroke:#3b82f6,stroke-width:2px,color:#1e3a8a,rx:6px,ry:6px;

    M1["1. Mouse Drag on Canvas<br/>(Start: x1, y1 | End: x2, y2)"] --> M2["2. Compute Normalized Bounding Box<br/>x = min(x1, x2) / width<br/>y = min(y1, y2) / height<br/>w = abs(x2 - x1) / width<br/>h = abs(y2 - y1) / height"]
    M2 --> M3["3. Linear Coordinate Interpolation (geo.js)<br/>min_lon = bounds.min_lon + x * delta_lon<br/>max_lat = bounds.max_lat - y * delta_lat<br/>max_lon = min_lon + w * delta_lon<br/>min_lat = max_lat - h * delta_lat"]
    M3 --> M4["4. Output Validated WGS84 BBox<br/>[min_lon, min_lat, max_lon, max_lat]<br/>Injected into region_bbox payload"]

    class M1,M2,M3,M4 mathStyle;
```

---

### 2.3 Key Frontend Components Reference

| Component | File Path | Visual Role | Key Interactive Features |
| :--- | :--- | :--- | :--- |
| **`ImageSlot`** | [ImageSlot.jsx](file:///Users/shrishtigaur/Documents/SatQuery-main/frontend/src/components/ImageSlot.jsx) | Primary satellite raster canvas | Interactive mouse ROI box drawing, metadata overlays, resolution badges. |
| **`TemporalComparisonViewer`** | [TemporalComparisonViewer.jsx](file:///Users/shrishtigaur/Documents/SatQuery-main/frontend/src/components/TemporalComparisonViewer.jsx) | Before/after comparison | Split-slider swipe view, side-by-side sync zoom, 500ms optical flicker mode. |
| **`SpectralInspector`** | [SpectralInspector.jsx](file:///Users/shrishtigaur/Documents/SatQuery-main/frontend/src/components/SpectralInspector.jsx) | Biophysical spectral analyzer | Multi-band value extraction, 13+ index breakdowns, canopy vigor charts. |
| **`StepTimeline`** | [StepTimeline.jsx](file:///Users/shrishtigaur/Documents/SatQuery-main/frontend/src/components/StepTimeline.jsx) | Live execution graph | Real-time node pulses driven by Server-Sent Events from the backend. |
| **`DetailedLogsSidebar`** | [DetailedLogsSidebar.jsx](file:///Users/shrishtigaur/Documents/SatQuery-main/frontend/src/components/DetailedLogsSidebar.jsx) | Telemetry & telemetry drawer | JSON tree inspection, tool execution timings, upload knowledge base audit. |
| **`WorkflowPresets`** | [WorkflowPresets.jsx](file:///Users/shrishtigaur/Documents/SatQuery-main/frontend/src/components/WorkflowPresets.jsx) | Mission quick-launcher | 1-click execution cards for Wildfire, Flood, Drought, and Deforestation. |

---

## 3. Backend Gateway Architecture (`backend/`)

The backend is built with **FastAPI** and acts as the secure, high-speed gateway between browser clients, satellite APIs, and the LangGraph engine.

### 3.1 Dynamic Raster Rendering Pipeline Flowchart

Satellite rasters are stored as 16-bit or 32-bit floating-point GeoTIFFs. The pipeline below dynamically converts them into optimized, high-contrast browser PNG previews:

```mermaid
flowchart TD
    classDef pipeStyle fill:#f8fafc,stroke:#0284c7,stroke-width:2px,color:#0f172a,rx:6px,ry:6px;

    R1["1. GET /api/v1/raster-preview?path=...&size=1024"] --> R2["2. Security Sandbox Validation<br/>Verify path is inside project root; reject traversal attempts"]
    R2 --> R3["3. Windowed Native Read (Rasterio)<br/>Calculate decimated overview factor to prevent memory spikes"]
    R3 --> R4{"4. Coordinate System Check"}
    R4 -- Native != EPSG:4326/3857 --> R5["Reproject Window on-the-fly<br/>rasterio.warp.reproject"]
    R4 -- Native is Standard --> R6["Extract Raw Pixel Array"]
    R5 --> R6
    R6 --> R7["5. Dynamic Contrast Stretch<br/>Compute 2nd and 98th percentiles across valid data pixels<br/>Clips outliers and scales to 8-bit dynamic range (0–255)"]
    R7 --> R8{"6. Region Polygon Mask?"}
    R8 -- Yes --> R9["Apply Polygon Mask<br/>Set non-feature pixels to black"]
    R8 -- No --> R10["Direct 8-bit RGB/RGBA Encoding"]
    R9 --> R10
    R10 --> R11["7. Return HTTP 200 image/png Stream"]

    class R1,R2,R3,R4,R5,R6,R7,R8,R9,R10,R11 pipeStyle;
```

---

### 3.2 Vision Model (VLM) Interpretation Pipeline Flowchart

```mermaid
flowchart LR
    classDef vlmStyle fill:#faf5ff,stroke:#9333ea,stroke-width:2px,color:#3b0764,rx:6px,ry:6px;

    V1["1. Visual Question<br/>'Where is the flooded area?'"] --> V2["2. Region Crop & PNG Render<br/>Window cropped from source raster"]
    V2 --> V3["3. Vision Provider Factory<br/>Dispatches to Anthropic Claude (Sonnet 5, Haiku 4.5, Opus 5.5)"]
    V3 --> V4["4. Parse Structured JSON<br/>Extracts description + fractional coordinates"]
    V4 --> V5["5. Tool 11 Inversion Engine<br/>Closed-form inverse affine transform"]
    V5 --> V6["6. Exact Real-World Coordinates<br/>WGS84 BBox & Centroid output"]

    class V1,V2,V3,V4,V5,V6 vlmStyle;
```

---

### 3.3 Backend API Endpoint Reference

| Method | Endpoint | Purpose | Key Parameters | Response Type |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/query/stream` | Primary streaming query route | `query`, `bbox`, `region_bbox`, `input_file` | Server-Sent Events (`text/event-stream`) |
| `POST` | `/api/v1/query` | Synchronous query execution | `query`, `bbox`, `start_date`, `end_date` | `application/json` (full execution summary) |
| `POST` | `/api/v1/upload-raster` | Ingests user GeoTIFF files | Multipart `file` (up to 500 MB) | `{"path": "...", "knowledge_base": {...}}` |
| `GET` | `/api/v1/raster-preview` | Renders contrast-stretched PNG | `path`, `size` (default: 1024px) | `image/png` |
| `GET` | `/api/v1/raster-file` | Downloads raw GeoTIFF raster | `path` | `application/octet-stream` |
| `GET` | `/api/v1/models` | Active model configuration | None | JSON status of orchestrator & vision models |
| `POST` | `/api/v1/conversation/reset` | Resets conversation session | `session_id`, `temp_files` | Deletes temporary uploads and clears context |

---

## 4. LangGraph Architecture & Graph Implementations

SatQuery separates raster preparation from query execution by employing **two distinct LangGraph graphs**:
1. **The Ingestion Graph** (`ingest_graph.py`): Runs once upon file upload to profile, validate, and build a local knowledge base.
2. **The Query Graph** (`graph.py`): Runs on every prompt to coordinate multi-hop tool execution.

### 4.1 Ingestion Graph Flowchart (Upload-Time Profiling)

```mermaid
flowchart TD
    classDef nodeStyle fill:#f0fdf4,stroke:#16a34a,stroke-width:2px,color:#14532d,rx:6px,ry:6px;
    classDef decisionStyle fill:#fefce8,stroke:#ca8a04,stroke-width:2px,color:#713f12,rx:6px,ry:6px;

    I_START([START: User Uploads .tif File]) --> I_COUNT["count_images: Validate single-file payload"]
    I_COUNT --> I_VAL["inspect_and_validate: Tool 6 Rasterio QA Check"]
    I_VAL --> I_DECISION{"Is file a valid GeoTIFF?"}
    
    I_DECISION -- No --> I_ERR([END: HTTP 400 'Please enter a valid GeoTIFF'])
    I_DECISION -- Yes --> I_EXTRACT["extract_fields: Derive band names, GSD, and WGS84 Centroid"]
    I_EXTRACT --> I_GEO["resolve_place_name: Tool 10 Reverse Geocode Centroid"]
    I_GEO --> I_KB["build_knowledge_base: Assemble & Write <filename>.kb.json"]
    I_KB --> I_SUCCESS([END: Success JSON + Knowledge Base])

    class I_COUNT,I_VAL,I_EXTRACT,I_GEO,I_KB nodeStyle;
    class I_DECISION decisionStyle;
```

---

### 4.2 Query Graph Flowchart (Query-Time Multi-Hop Execution)

```mermaid
flowchart TD
    classDef qStyle fill:#f0fdf4,stroke:#16a34a,stroke-width:2px,color:#14532d,rx:6px,ry:6px;
    classDef qDec fill:#fefce8,stroke:#ca8a04,stroke-width:2px,color:#713f12,rx:6px,ry:6px;

    Q_START([START: Incoming Query]) --> Q_VAL["validate: Bounds, Coordinate Limits & String Checks"]
    Q_VAL --> Q_VDEC{"Input Valid?"}
    
    Q_VDEC -- Errors --> Q_RESP["respond: Output Error Details"]
    Q_VDEC -- Valid --> Q_LKB["load_knowledge_base: Load <file>.kb.json from disk"]
    
    Q_LKB --> Q_KDEC{"KB Found?"}
    Q_KDEC -- Yes --> Q_VLM["vlm_initial_description: Grounded First-Pass Visual Description"]
    Q_KDEC -- No --> Q_AUTO["describe_region_auto: Deterministic Marked Region Crop & QA"]
    Q_VLM --> Q_AUTO
    
    Q_AUTO --> Q_LOOP["tool_loop: Compiled Subgraph (Multi-Hop Planner Loop)"]
    Q_LOOP --> Q_RESP
    Q_RESP --> Q_END([END: Return Final Answer & SSE Stream])

    class Q_VAL,Q_LKB,Q_VLM,Q_AUTO,Q_LOOP,Q_RESP qStyle;
    class Q_VDEC,Q_KDEC qDec;
```

---

### 4.3 Subgraph Reducer Slicing Mechanics Flowchart

When the recursive `tool_loop_subgraph` completes, LangGraph's list reducers (`Annotated[list, add]`) could duplicate items if returned raw. The diagram below shows how `_tool_loop_node` prevents duplicates:

```mermaid
flowchart TD
    classDef sliceStyle fill:#f8fafc,stroke:#475569,stroke-width:2px,color:#0f172a,rx:6px,ry:6px;

    S1["Parent State at Subgraph Entry<br/>tool_results: [R1]<br/>execution_trace: [T1, T2]<br/>prior_len = 1 (results), 2 (trace)"] --> S2["Invoke tool_loop_subgraph<br/>Executes multiple hops internally"]
    S2 --> S3["Subgraph Returns Full Result<br/>tool_results: [R1, R2, R3]<br/>execution_trace: [T1, T2, T3, T4]"]
    S3 --> S4["Slice Out Prior Entries<br/>delta_results = result['tool_results'][prior_len:] -> [R2, R3]<br/>delta_trace = result['execution_trace'][prior_len:] -> [T3, T4]"]
    S4 --> S5["Parent Graph Appends Delta Only<br/>Zero duplicate steps in StepTimeline!"]

    class S1,S2,S3,S4,S5 sliceStyle;
```

---

### 4.4 LangGraph State Dictionary (`SatQueryState`)

| State Field | Type | Lifecycle & Source | Consumer Nodes |
| :--- | :--- | :--- | :--- |
| **`query`** | `str` | User prompt from HTTP request | `validate`, `llm`, `synthesis` |
| **`bbox`** | `list[float]` | Request body or derived from Tool 6 inspection | Imagery fetch tools (Tools 1–3) |
| **`region_bbox`** | `list[float]` | Drawn on frontend canvas or located by VLM | `describe_region_auto`, Tool 11 |
| **`region_polygon`** | `list[dict]` | Feature boundary traced by VLM | Region masking, Tool 11 |
| **`region_centroid`** | `dict` | Computed path centroid of polygon | Anchor point for weather (Tool 4) & reverse geocoding |
| **`place_name`** | `str` | Extracted by LLM planner from prompt | Forward geocoding (Tool 10) |
| **`input_file`** | `str` | Uploaded raster or prior tool output path | Tools 5, 6, 8, vision tools |
| **`tool_results`** | `list[ToolResult]` | Appended by `tool_node` on every execution | Planner continuation context, `synthesis` |
| **`execution_trace`** | `list[TraceEntry]` | Appended by `trace_entry()` in every node | Real-time SSE stream, frontend `StepTimeline` |

---

## 5. Autonomous Orchestrator Architecture

The orchestrator is SatQuery's cognitive planner. It replaces legacy rigid intent classification with **autonomous multi-hop reasoning**, picking tools dynamically based on real-time evidence.

### 5.1 Autonomous Multi-Hop Decision Loop Flowchart

```mermaid
flowchart TD
    classDef planStyle fill:#eff6ff,stroke:#2563eb,stroke-width:2px,color:#1e3a8a,rx:6px,ry:6px;
    classDef checkStyle fill:#fefce8,stroke:#ca8a04,stroke-width:2px,color:#713f12,rx:6px,ry:6px;

    O_START([START: Enter tool_loop]) --> O_CHECK{"Hops >= 10?"}
    O_CHECK -- Yes --> O_FORCE_STOP["Stop: Exceeded max tool hops"]
    O_CHECK -- No --> O_LLM["llm_node: Consult Planner (llm.py)"]
    
    O_LLM --> O_ACT{"Plan Action?"}
    O_ACT -- finish / chat / clarify --> O_END([Exit Subgraph to respond])
    O_ACT -- call_tool --> O_READY{"location_ready_for_tool?<br/>Are BBox & Inputs present?"}
    
    O_READY -- Missing Inputs --> O_CLARIFY["Downgrade to Clarify Action<br/>Request missing info from user"]
    O_READY -- Inputs Ready --> O_ARGS["trusted_args_for_tool<br/>Construct parameters from verified state"]
    
    O_ARGS --> O_EXEC["tool_node: Execute Tool via executor.py"]
    O_EXEC --> O_UPDATE["Update State:<br/>• Set input_file to newly generated GeoTIFF<br/>• Append output to tool_results<br/>• Increment tool_hops count"]
    O_UPDATE --> O_CHECK

    class O_LLM,O_FORCE_STOP,O_CLARIFY,O_ARGS,O_EXEC,O_UPDATE planStyle;
    class O_CHECK,O_ACT,O_READY checkStyle;
```

---

### 5.2 The Tool 7 $\rightarrow$ Tool 8 Analytical Handshake Flowchart

```mermaid
flowchart TD
    classDef t7Style fill:#f0f9ff,stroke:#0284c7,stroke-width:2px,color:#0c4a6e,rx:6px,ry:6px;
    classDef t8Style fill:#fefce8,stroke:#ca8a04,stroke-width:2px,color:#713f12,rx:6px,ry:6px;
    classDef outStyle fill:#f0fdf4,stroke:#16a34a,stroke-width:2px,color:#14532d,rx:6px,ry:6px;

    subgraph Tool7 ["Tool 7: Continuous Differential Engine"]
        T1["Pre-Event Raster (T1)<br/>e.g. Pre-fire NBR index"]
        T2["Post-Event Raster (T2)<br/>e.g. Post-fire NBR index"]
        DIFF["Differential Algebra:<br/>Delta = T2 - T1"]
        THRESH["Noise Thresholding & Categorization"]
        
        T1 & T2 --> DIFF --> THRESH
        THRESH --> MASK["change_mask.tif<br/>(-1=Loss, 0=Stable, +1=Gain)"]
    end

    subgraph Tool8 ["Tool 8: Categorical GIS & Terrain Profiler"]
        LULC["ESA WorldCover 10m<br/>(Forest, Cropland, Water, Urban)"]
        DEM["Copernicus DEM 30m<br/>(Elevation Model)"]
        
        MASK -.->|The Handshake: Passed as zone_mask_path| ALIGN["Grid Alignment & Resampling<br/>Nearest for Mask/LULC; Bilinear for DEM"]
        LULC & DEM --> ALIGN
        
        ALIGN --> ZONAL["Zonal Cross-Tabulation Matrix<br/>(Change Zone x Land Cover Class)"]
        ALIGN --> SLOPE["2D Spatial Slope Gradient Derivation"]
        ALIGN --> FRAG["8-Connectivity Patch Fragmentation"]
    end

    subgraph FinalReport ["Multi-Dimensional Decision Intelligence"]
        ZONAL & SLOPE & FRAG --> REP["Actionable Report:<br/>'42.3 km2 of Dense Forest was destroyed on 15°-25° steep slopes,\ncreating severe post-fire landslide risks.'"]
    end

    class T1,T2,DIFF,THRESH,MASK t7Style;
    class LULC,DEM,ALIGN,ZONAL,SLOPE,FRAG t8Style;
    class REP outStyle;
```

---

### 5.3 Ground Truth Precedence Hierarchy (Conflict Resolution)

```mermaid
flowchart TD
    classDef tierStyle fill:#ffffff,stroke:#64748b,stroke-width:2px,color:#0f172a,rx:8px,ry:8px;

    T1["🥇 Tier 1: Physical Pixel Measurements (Highest Authority)<br/>Mathematical values computed by Tools 5, 7, and 8 strictly override any numbers in user prompts."]
    T2["🥈 Tier 2: Verified Geographic Lookups<br/>Reverse-geocoded place names from Tool 10 strictly override AI visual guesses."]
    T3["🥉 Tier 3: User-Drawn Regional Intent<br/>The user-drawn ROI box (region_bbox) strictly takes precedence over AI-suggested boxes."]
    T4["🏅 Tier 4: Vision Model Qualitative Interpretations<br/>VLM visual descriptions and approximate object localizations."]
    T5["🎖️ Tier 5: General LLM Knowledge (Lowest Authority)<br/>Parametric memory used solely for grammar, formatting, and general context."]

    T1 --> T2 --> T3 --> T4 --> T5

    class T1,T2,T3,T4,T5 tierStyle;
```

---

### 5.4 Autonomous Missions Reference Matrix (`satquery_workflows.py`)

| Mission Pipeline | Target Event | Step-by-Step Tool Sequence | Key Output Artifacts | Primary Metric |
| :--- | :--- | :--- | :--- | :--- |
| **Pipeline A: Wildfire Burn Severity** | Forest fires, burn scars, post-fire erosion risk | **Tool 5** (Pre/Post NBR) $\rightarrow$ **Tool 6** (QA) $\rightarrow$ **Tool 7** ($\Delta\text{NBR}$) $\rightarrow$ **Tool 8** (Zonal LULC & Slope) | `nbr_pre.tif`<br>`delta_nbr.tif`<br>`burn_severity.tif` | Destroyed forest area ($\text{km}^2$) and high-slope landslide risk exposure. |
| **Pipeline B: Radar Flood Inundation** | Cyclone flooding, monsoon inundation through cloud cover | **Tool 6** (QA) $\rightarrow$ **Tool 7** (SAR backscatter drop $\le -3\,\text{dB}$) $\rightarrow$ **Tool 4** (Rainfall check) $\rightarrow$ **Tool 8** (Flooded LULC) | `sar_diff.tif`<br>`flood_mask.tif` | Inundated cropland & urban infrastructure area ($\text{km}^2$). |
| **Pipeline C: Agricultural Drought** | Canopy dehydration, regional crop moisture stress | **Tool 5** (NDMI & NDVI) $\rightarrow$ **Tool 4** (ERA5 Soil Moisture Anomaly) $\rightarrow$ Statistical Correlation Engine | `ndmi_canopy.tif`<br>`ndvi_vigor.tif` | Soil-moisture-to-canopy deficit correlation index ($[-1.0, 1.0]$). |

---

## 6. Complete 11-Tool Ecosystem Matrix

| Tool ID | Name | Technology | Input Requirements | Generated Outputs |
| :---: | :--- | :--- | :--- | :--- |
| **Tool 1** | `fetch_optical_imagery` | Sentinel-2 L2A | Bounding Box, Date range, Max cloud % | True-Color RGB GeoTIFF + Cloud Quality JSON |
| **Tool 2** | `fetch_multispectral_imagery` | Sentinel-2 L2A | Bounding Box, Date range, Band list | 12-Band Surface Reflectance GeoTIFF + Band Mapping |
| **Tool 3** | `fetch_sar_imagery` | Sentinel-1 GRD | Bounding Box, Date range, Polarization | Cloud-penetrating Backscatter GeoTIFF (dB) |
| **Tool 4** | `fetch_weather_environment` | Open-Meteo & ERA5 | Bounding Box or Point, Date range | Weather time series, Moisture deficit, Drought stress |
| **Tool 5** | `compute_vegetation_indices` | Vectorized NumPy | Multi-band GeoTIFF, Index names | Multi-band Index GeoTIFF (FLOAT32) + Canopy Area |
| **Tool 6** | `inspect_geotiff_metadata` | Local Rasterio | GeoTIFF path, Optional compare path | Dimensions, CRS, GSD, NoData count, Grid compatibility |
| **Tool 7** | `analyze_temporal_change` | Differential Algebra | $T_1$ and $T_2$ GeoTIFFs, Thresholds | `difference_raster.tif`, `change_mask.tif` (-1, 0, +1) |
| **Tool 8** | `analyze_spatial_landcover_terrain` | WorldCover & DEM | LULC GeoTIFF, DEM, Zone Mask | Landcover composition, Patch fragmentation, Slope |
| **Tool 9** | `fetch_web_intelligence` | Tavily Search API | Query, Location hint | Verified ground-truth news & incident citations |
| **Tool 10**| `spatial_geocoding_poi` | LocationIQ / OSM | Place name, Lat/Lon, or BBox | Verified coordinates, Address, In-scene POI list |
| **Tool 11**| `deterministic_affine_markup` | Affine Math & Pillow | GeoTIFF path, Feature list | Subpixel projected coordinate markup on PNG preview |

---

## 7. Project Sitemap & Quick Links

```text
SatQuery Architecture Sitemap
├── 🖥️ Frontend (React 18 + Vite)
│   ├── Application Coordinator   → frontend/src/App.jsx
│   ├── Raster Canvas Stage       → frontend/src/components/ImageSlot.jsx
│   ├── Comparison Viewers       → frontend/src/components/TemporalComparisonViewer.jsx
│   ├── Spectral Inspector        → frontend/src/components/SpectralInspector.jsx
│   ├── Live Workflow Graph       → frontend/src/components/StepTimeline.jsx
│   ├── Mission Presets           → frontend/src/components/WorkflowPresets.jsx
│   └── Client Geo Library        → frontend/src/lib/geo.js
│
├── ⚡ Backend Gateway (FastAPI)
│   ├── Application Factory       → backend/main.py
│   ├── Runtime Settings          → backend/config/settings.py
│   ├── Query & SSE Routes        → backend/api/routes/query.py
│   ├── Upload Handling Routes    → backend/api/routes/uploads.py
│   ├── Preview Renderer          → backend/rendering/raster_preview.py
│   └── Tool Execution Gateway    → backend/tools/executor.py
│
├── 🧠 LangGraph Orchestrator
│   ├── Shared State Definition   → backend/orchestrator/state.py
│   ├── Query Graph Workflow      → backend/orchestrator/graph.py
│   ├── Ingestion Graph Workflow  → backend/orchestrator/ingest_graph.py
│   ├── Tool-Loop Subgraph        → backend/orchestrator/tool_loop_graph.py
│   ├── Tool Registry & Schemas   → backend/orchestrator/registry.py
│   ├── LLM Planner Engine        → backend/orchestrator/llm.py
│   └── Intelligence Synthesis    → backend/orchestrator/synthesis.py
│
└── 🔬 Scientific Tools (Tools 1–11)
    ├── Optical & Multispectral   → Tool_1_... / Tool_2_...
    ├── SAR Radar & Weather       → Tool_3_... / Tool_4_...
    ├── Biophysical Math & GIS    → Tool_5_... / Tool_6_... / Tool_7_... / Tool_8_...
    ├── Geocoding & Affine Math   → Tool_9_... / Tool_10_... / Tool_11_...
    └── Autonomous Missions       → satquery_workflows.py
```
