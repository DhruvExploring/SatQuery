"""
FastAPI application factory for SatQuery AI.

This file owns:
  - App creation and metadata
  - CORS configuration (for React dev server)
  - Lifespan (startup / shutdown hooks — currently just logging)
  - Mounting the API router

Business logic lives in:
  backend/orchestrator/   ← LangGraph graph, planner, nodes
  backend/tools/          ← Tool executor

This file never imports Sentinel Hub, LLM clients, or LangGraph internals
directly. It only wires FastAPI → router → graph.

Run with:
    uvicorn backend.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes.query import router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — runs once at startup and shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Startup: pre-import the graph so the first request is not slow.
    Shutdown: nothing to clean up yet (no DB connections, no background tasks).
    """
    logger.info("SatQuery API starting up — importing graph...")
    # Importing here triggers LangGraph compilation once, not per-request.
    from backend.orchestrator.graph import satquery_graph  # noqa: F401
    logger.info("Graph ready.")
    yield
    logger.info("SatQuery API shutting down.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
def create_app() -> FastAPI:
    app = FastAPI(
        title="SatQuery AI",
        description=(
            "Agentic remote-sensing assistant. "
            "Send a natural-language query; get satellite imagery metadata back."
        ),
        version="0.3.0",
        lifespan=lifespan,
    )

    # CORS — allow the React dev server (port 3000/5173) during development.
    # Tighten `allow_origins` to your production domain before deployment.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",   # Create React App
            "http://localhost:5173",   # Vite
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount the single router — all routes live in backend/api/routes/
    app.include_router(router)

    return app


# Module-level instance used by uvicorn
app = create_app()
