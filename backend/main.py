"""
FastAPI application factory for SatQuery AI.

This file owns app creation, CORS, lifespan hooks, and router mounting.
Business logic lives in backend/orchestrator and backend/tools.
"""

from __future__ import annotations

import os
from pathlib import Path

# Sanitize PROJ environment so rasterio/GDAL/pyproj uses its own bundled PROJ database
# rather than an incompatible system version (e.g. from PostgreSQL/PostGIS).
try:
    import rasterio
    _rproj = Path(rasterio.__file__).parent / "proj_data"
    if (_rproj / "proj.db").is_file():
        os.environ["PROJ_LIB"] = str(_rproj)
        os.environ["PROJ_DATA"] = str(_rproj)
except Exception:
    pass

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# pyrefly: ignore [missing-import]
from fastapi import FastAPI
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware

from backend.api.errors import register_exception_handlers
from backend.api.routes.models import router as models_router
from backend.api.routes.query import router
from backend.api.routes.rasters import router as rasters_router
from backend.api.routes.uploads import router as uploads_router
from backend.config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


def _warm_up_llm_clients() -> None:
    """Eagerly import/build the LLM SDKs this deployment actually uses.

    langchain_openai/langchain_anthropic each pull in hundreds of submodules
    (the openai SDK alone has ~500 files) on first import. Left lazy, that
    cold-import cost lands on whichever live request happens to be first —
    which looks exactly like a hung request, especially on a memory-constrained
    machine where the extra disk I/O can stall for minutes. Paying that cost
    once here, at startup, keeps it out of request latency entirely.
    """
    if settings.orchestrator_provider != "mock":
        try:
            logger.info(
                "Warming up orchestrator LLM client (provider=%s)...",
                settings.orchestrator_provider,
            )
            from backend.orchestrator.llm import _build_llm_client

            _build_llm_client()
            logger.info("Orchestrator LLM client ready.")
        except Exception as exc:
            logger.warning(
                "Orchestrator LLM warm-up failed (%r) — will build lazily on first request.",
                exc,
            )

    if settings.vision_tool_enabled and settings.vision_tool_provider == "openai":
        try:
            logger.info("Warming up vision tool SDK import (openai)...")
            import langchain_openai  # noqa: F401

            logger.info("Vision tool SDK ready.")
        except Exception as exc:
            logger.warning(
                "Vision tool warm-up failed (%r) — will import lazily on first call.",
                exc,
            )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("SatQuery API starting up — importing graph...")
    from backend.orchestrator.graph import satquery_graph  # noqa: F401
    logger.info("Graph ready.")
    _warm_up_llm_clients()
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
        allow_origins=list(settings.cors_allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    app.include_router(rasters_router)
    app.include_router(models_router)
    app.include_router(uploads_router)
    register_exception_handlers(app)

    # Mount frontend dashboard (serves compiled React dist if built, otherwise frontend root)
    from pathlib import Path
    from fastapi.staticfiles import StaticFiles

    frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    target_dir = frontend_dist if frontend_dist.is_dir() else frontend_dir
    if target_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(target_dir), html=True), name="frontend")

    return app


app = create_app()
