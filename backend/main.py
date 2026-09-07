"""
FastAPI application factory for SatQuery AI.

This file owns app creation, CORS, lifespan hooks, and router mounting.
Business logic lives in backend/orchestrator and backend/tools.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# pyrefly: ignore [missing-import]
from fastapi import FastAPI
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware

from backend.api.errors import register_exception_handlers
from backend.api.routes.query import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("SatQuery API starting up — importing graph...")
    from backend.orchestrator.graph import satquery_graph  # noqa: F401
    logger.info("Graph ready.")
    yield
    logger.info("SatQuery API shutting down.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="SatQuery AI",
        description=(
            "Agentic remote-sensing assistant for Tools 1–8. "
            "POST /api/v1/query with a natural-language query plus location "
            "(bbox / lat-lon) for fetch tools, or GeoTIFF paths for analysis "
            "tools 5–8. Open /docs and pick an example."
        ),
        version="0.3.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    register_exception_handlers(app)

    return app


app = create_app()
