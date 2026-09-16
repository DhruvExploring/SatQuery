# Tool 9: fetch_web_intelligence (Ground Truth & Event Intelligence)

**`fetch_web_intelligence`** is a dedicated external research and grounding tool built for Model Context Protocol (MCP) clients and LangGraph autonomous agents. Its primary responsibility is to bridge the gap between **satellite pixel-level observations** (NDVI, SAR backscatter dB, inundated hectares, burn severity) and **real-world context** (barrage discharge cusecs, historical record comparisons, infrastructure project names, and disaster management reports).

---

## 1. Why Web Intelligence in Remote Sensing?

Satellite imagery produces numerical reflectances and geometric boundaries, but lacks human and operational metadata:
1. **Disaster Root Causes**: Satellite radar shows inundated flood polygons; Web Intelligence explains *why* (e.g., Hathnikund barrage release of 3.59 lakh cusecs, jammed ITO barrage gates, 208.66m record level).
2. **Infrastructure Identification**: Identifies specific highways (e.g., Delhi-Dehradun Expressway, Dwarka Expressway), solar parks, or port expansions visible in newly cleared land.
3. **Coordinate & Location Grounding**: Resolves ambiguous locations or names for unlabelled bounding boxes.

---

## 2. Search Engine Architecture: Dual-Provider Strategy

```mermaid
flowchart TD
    A[Agent / User Request] --> B[WebIntelligenceRequest Validation]
    B --> C{Tavily Key Available & Provider=tavily?}
    C -- Yes --> D[Execute Tavily Search API]
    D -- Success (Direct AI Answer + Sources) --> G[Format Unified Response]
    D -- Failure / 429 Quota Exceeded / Error --> E[Automatic Fail-Safe Engaged]
    C -- No / Force DuckDuckGo --> E
    E --> F[Execute DuckDuckGo Search (DDGS)]
    F --> G
    G --> H[LangGraph State & UI Badge]
```

- **Primary Provider**: **Tavily Search API** — Generates concise, agent-optimized answers with high-relevance source links.
- **Fail-Safe Fallback**: **DuckDuckGo Search** — Direct, keyless web search engine ensuring zero downtime even when Tavily's 1000 monthly searches are exhausted.

---

## 3. Pydantic Request Schema

```json
{
  "query": "string (min 2 chars, required)",
  "max_results": "integer (1-15, default: 5)",
  "search_depth": "string ('basic' | 'advanced', default: 'basic')",
  "location_hint": "string (optional location context)",
  "include_domains": ["list of strings (optional)"],
  "exclude_domains": ["list of strings (optional)"]
}
```

---

## 4. Response Output Schema

```json
{
  "status": "success",
  "provider": "tavily" | "duckduckgo",
  "fallback_triggered": false,
  "fallback_reason": null,
  "query": "What caused the July 2023 Delhi Yamuna flood...",
  "results_count": 5,
  "summary": "In July 2023, the Yamuna River in Delhi reached 208.66m due to heavy discharge from Hathnikund barrage...",
  "results": [
    {
      "title": "2023 Delhi flood - Wikipedia",
      "url": "https://en.wikipedia.org/wiki/2023_Delhi_flood",
      "content": "In July 2023, Delhi experienced its worst flood in 45 years...",
      "score": 0.965
    }
  ]
}
```

---

## 5. CLI Usage & FastMCP

### Standalone CLI
```bash
python Tool_9_fetch_web_intelligence/fetch_web_intelligence.py --query "Delhi Yamuna flood July 2023 Hathnikund barrage"
```

### FastMCP Tool
```python
from Tool_9_fetch_web_intelligence.fetch_web_intelligence import mcp_fetch_web_intelligence

response = mcp_fetch_web_intelligence(
    query="Delhi flood 2023 Hathnikund barrage discharge",
    max_results=5
)
```
