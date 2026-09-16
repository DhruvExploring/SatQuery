"""Tool 9: fetch_web_intelligence (Ground Truth, Event Context & Geospatial Web Intelligence)

Fills the critical real-world narrative gap between satellite observations and ground truth.
Satellite imagery produces numerical reflectances, SAR backscatter dB, and area calculations;
Web Intelligence provides the factual ground story: event causes, barrage discharge levels,
infrastructure project names, reverse geocoding context, and disaster response reports.

Search Engine Architecture:
  1. Primary Provider: Tavily Search API (optimized for AI agents with synthesized answers).
  2. Automatic Fail-Safe: DuckDuckGo Search (zero-config, keyless fallback if Tavily quota/rate limit is reached).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator

# Ensure project root is on sys.path and load environment variables
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

load_dotenv(ROOT_DIR / ".env")

logger = logging.getLogger("satquery.tool9_web_intelligence")

try:
    from fastmcp import FastMCP
except (ImportError, Exception):
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        FastMCP = None


# =============================================================================
# 1. Configuration & Models
# =============================================================================

@dataclass(frozen=True)
class WebIntelligenceConfig:
    default_max_results: int = 5
    default_search_depth: str = "basic"
    timeout_s: float = 15.0


CONFIG = WebIntelligenceConfig()


class WebIntelligenceRequest(BaseModel):
    query: str = Field(..., min_length=2, description="Natural language search query or topic to look up.")
    max_results: int = Field(default=5, ge=1, le=15, description="Maximum number of search results to return.")
    search_depth: Literal["basic", "advanced"] = Field(
        default="basic",
        description="Search depth for Tavily ('basic' is fast, 'advanced' performs deeper crawls)."
    )
    include_domains: Optional[list[str]] = Field(default=None, description="Optional list of domains to restrict search to.")
    exclude_domains: Optional[list[str]] = Field(default=None, description="Optional list of domains to exclude from search.")
    location_hint: Optional[str] = Field(default=None, description="Optional geographic location name or hint to ground the query.")
    bbox: Optional[list[float]] = Field(default=None, description="Optional bounding box [min_lon, min_lat, max_lon, max_lat] for geospatial context.")
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0, description="Optional latitude.")
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0, description="Optional longitude.")

    @field_validator("query")
    @classmethod
    def clean_query(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Search query must not be empty.")
        return cleaned


# =============================================================================
# 2. Search Execution Functions (Tavily & DuckDuckGo)
# =============================================================================

def _build_search_query(req: WebIntelligenceRequest) -> str:
    """Enrich the user query with location context if available."""
    q = req.query.strip()
    if req.location_hint and req.location_hint.lower() not in q.lower():
        q = f"{q} {req.location_hint}"
    return q


def _execute_tavily_search(
    query: str,
    api_key: str,
    max_results: int = 5,
    search_depth: str = "basic",
    include_domains: Optional[list[str]] = None,
    exclude_domains: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Execute search using Tavily Python client."""
    from tavily import TavilyClient

    client = TavilyClient(api_key=api_key)
    kwargs: dict[str, Any] = {
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "include_answer": True,
        "include_raw_content": False,
    }
    if include_domains:
        kwargs["include_domains"] = include_domains
    if exclude_domains:
        kwargs["exclude_domains"] = exclude_domains

    response = client.search(**kwargs)
    raw_results = response.get("results") or []
    answer = response.get("answer") or ""

    results = []
    for item in raw_results:
        results.append({
            "title": item.get("title") or "Untitled",
            "url": item.get("url") or "",
            "content": item.get("content") or item.get("snippet") or "",
            "score": item.get("score"),
        })

    # If Tavily did not return an explicit synthesized answer, create one from top snippets
    if not answer and results:
        top_snippets = [r["content"] for r in results[:2] if r.get("content")]
        answer = " ".join(top_snippets).strip()

    return {
        "status": "success",
        "provider": "tavily",
        "fallback_triggered": False,
        "fallback_reason": None,
        "query": query,
        "results_count": len(results),
        "summary": answer or "Web intelligence retrieved successfully.",
        "results": results,
    }


def _execute_duckduckgo_search(
    query: str,
    max_results: int = 5,
    fallback_reason: Optional[str] = None,
) -> dict[str, Any]:
    """Execute fail-safe search using DuckDuckGo (DDGS)."""
    from duckduckgo_search import DDGS

    logger.info("[WEB INTELLIGENCE] Executing DuckDuckGo search for query: %r", query)
    ddgs = DDGS(timeout=CONFIG.timeout_s)
    raw_results = list(ddgs.text(query, max_results=max_results))

    results = []
    snippets: list[str] = []
    for item in raw_results:
        title = item.get("title") or "Untitled"
        url = item.get("href") or item.get("url") or item.get("link") or ""
        body = item.get("body") or item.get("snippet") or ""
        if body:
            snippets.append(body)
        results.append({
            "title": title,
            "url": url,
            "content": body,
            "score": None,
        })

    summary = " ".join(snippets[:3]).strip() if snippets else "DuckDuckGo search completed."
    if len(summary) > 600:
        summary = summary[:597] + "..."

    return {
        "status": "success",
        "provider": "duckduckgo",
        "fallback_triggered": bool(fallback_reason),
        "fallback_reason": fallback_reason,
        "query": query,
        "results_count": len(results),
        "summary": summary,
        "results": results,
    }


# =============================================================================
# 3. Core Tool Function
# =============================================================================

FORBIDDEN_WEB_TERMS: tuple[str, ...] = (
    "python",
    "affine transform",
    "affine projection",
    "raster math",
    "pixel coordinates",
    "pixel coordinate",
    "pixel grid",
    "system internals",
    "import ",
    "numpy",
    "rasterio",
    "matrix multiplication",
    "transform matrix",
    "calculate pixel",
)


def fetch_web_intelligence(req: WebIntelligenceRequest) -> dict[str, Any]:
    """Fetch ground-truth real-world context, event causes, disaster reports,
    infrastructure project names, and location background via web search.

    Uses Tavily as the primary search engine and automatically fails over to DuckDuckGo
    if Tavily is unconfigured, rate-limited (1000/mo quota), or encounters an error.
    """
    search_query = _build_search_query(req)
    q_lower = search_query.lower()

    for forbidden in FORBIDDEN_WEB_TERMS:
        if forbidden in q_lower:
            msg = (
                f"Web Intelligence is strictly reserved for real-world ground truth, events, and disaster facts. "
                f"Meta/programming query containing prohibited keyword '{forbidden}' was blocked."
            )
            logger.warning("[WEB INTELLIGENCE] Blocked prohibited query: %r (matched %r)", search_query, forbidden)
            return {
                "status": "error",
                "error": {
                    "type": "invalid_web_query",
                    "message": msg,
                },
            }

    tavily_key = (
        os.getenv("TAVILY_API_KEY")
        or os.getenv("SATQUERY_TAVILY_API_KEY")
        or ""
    ).strip()
    provider_pref = (os.getenv("SATQUERY_WEB_SEARCH_PROVIDER") or "tavily").strip().lower()

    # If provider is explicitly forced to duckduckgo or no Tavily key is provided
    if provider_pref == "duckduckgo" or not tavily_key:
        reason = "Tavily API key not configured" if not tavily_key else "Provider set to DuckDuckGo"
        logger.info("[WEB INTELLIGENCE] Using DuckDuckGo direct (%s)", reason)
        try:
            return _execute_duckduckgo_search(
                query=search_query,
                max_results=req.max_results,
                fallback_reason=reason if not tavily_key else None,
            )
        except Exception as exc:
            logger.error("[WEB INTELLIGENCE] DuckDuckGo search failed: %s", exc, exc_info=True)
            return {
                "status": "error",
                "error": {
                    "type": "search_service_error",
                    "message": f"Web search failed across both providers: {exc}",
                },
            }

    # Primary path: Tavily Search
    try:
        logger.info("[WEB INTELLIGENCE] Calling Tavily Search for %r", search_query)
        return _execute_tavily_search(
            query=search_query,
            api_key=tavily_key,
            max_results=req.max_results,
            search_depth=req.search_depth,
            include_domains=req.include_domains,
            exclude_domains=req.exclude_domains,
        )
    except Exception as exc:
        # Catch Tavily quota exhaustion (429), auth error (401), invalid key, network timeout
        fallback_msg = f"Tavily search failed ({exc}) — automatic fail-safe to DuckDuckGo engaged"
        logger.warning("[WEB INTELLIGENCE] %s", fallback_msg)

        try:
            return _execute_duckduckgo_search(
                query=search_query,
                max_results=req.max_results,
                fallback_reason=fallback_msg,
            )
        except Exception as ddg_exc:
            logger.error("[WEB INTELLIGENCE] DuckDuckGo fallback also failed: %s", ddg_exc, exc_info=True)
            return {
                "status": "error",
                "error": {
                    "type": "search_service_error",
                    "message": f"Tavily error: {exc}. DuckDuckGo fallback error: {ddg_exc}",
                },
            }


# =============================================================================
# 4. FastMCP Tool Registration
# =============================================================================

if FastMCP is None:
    class _DummyMCP:
        def tool(self, *args, **kwargs):
            return lambda fn: fn
    mcp = _DummyMCP()
else:
    mcp = FastMCP("SatQuery Tool 9 - Web Search Intelligence")


@mcp.tool(
    name="fetch_web_intelligence",
    description=(
        "Fetch ground-truth real-world context, event causes, disaster reports, "
        "infrastructure project names, and location background via web search "
        "(Tavily AI with automatic DuckDuckGo fail-safe fallback)."
    )
)
def mcp_fetch_web_intelligence(
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
    location_hint: Optional[str] = None,
    include_domains: Optional[list[str]] = None,
    exclude_domains: Optional[list[str]] = None,
) -> dict[str, Any]:
    try:
        req = WebIntelligenceRequest(
            query=query,
            max_results=max_results,
            search_depth=search_depth,  # type: ignore[arg-type]
            location_hint=location_hint,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
        )
        return fetch_web_intelligence(req)
    except ValueError as e:
        return {"status": "error", "error": {"type": "validation_error", "message": str(e)}}
    except Exception as e:
        return {"status": "error", "error": {"type": "service_error", "message": str(e)}}


# =============================================================================
# 5. Standalone Execution Entrypoint
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Tool 9: fetch_web_intelligence CLI")
    parser.add_argument("--query", "-q", type=str, help="Search query string")
    parser.add_argument("--config", "-c", type=str, help="Path to JSON request configuration file")
    parser.add_argument("--max-results", "-n", type=int, default=5, help="Max results count")
    args = parser.parse_args()

    if args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            data = json.load(f)
        req = WebIntelligenceRequest(**data)
        res = fetch_web_intelligence(req)
        print(json.dumps(res, indent=2))
    elif args.query:
        req = WebIntelligenceRequest(query=args.query, max_results=args.max_results)
        res = fetch_web_intelligence(req)
        print(json.dumps(res, indent=2))
    else:
        print("Tool 9: fetch_web_intelligence ready. Usage: python fetch_web_intelligence.py --query 'Delhi Yamuna flood July 2023'")
