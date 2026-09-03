"""Compile the SatQuery graph.

    START → validate → plan → (router) → execute → respond → END
                                 └── respond → END

Wiring lives here. Business logic lives in nodes.py / router.py.

Memory (Milestone 7):
  - MemorySaver checkpointer: stores in-thread conversation turns (session history)
  - BaseStore (InMemoryStore or PostgresStore): stores cross-thread user memories (LangMem)

Both are optional — if memory_backend="none", the graph runs stateless as before.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from backend.config.settings import settings
from backend.orchestrator.nodes import execute, plan, respond, validate_input
from backend.orchestrator.router import route_after_plan
from backend.orchestrator.state import SatQueryState

logger = logging.getLogger(__name__)


def _build_store() -> object | None:
    """
    Build a LangGraph BaseStore for cross-thread (long-term) memory.
    Returns None when memory_backend is "none" — graph runs stateless.
    """
    backend = settings.memory_backend.lower()

    if backend == "none":
        return None

    if backend == "in_memory":
        try:
            from langgraph.store.memory import InMemoryStore
            store = InMemoryStore(
                index={
                    "dims": 1536,
                    "embed": settings.memory_embed_model,
                }
            )
            logger.info("LangMem: using InMemoryStore (dev mode — lost on restart).")
            return store
        except Exception as exc:  # noqa: BLE001
            logger.warning("InMemoryStore failed to initialise (%r) — memory disabled.", exc)
            return None

    if backend == "postgres":
        if not settings.memory_db_url:
            logger.warning(
                "SATQUERY_MEMORY_BACKEND=postgres but SATQUERY_MEMORY_DB_URL is not set "
                "— memory disabled."
            )
            return None
        try:
            from langgraph.store.postgres import PostgresStore
            store = PostgresStore.from_conn_string(
                settings.memory_db_url,
                index={"dims": 1536, "embed": settings.memory_embed_model},
            )
            logger.info("LangMem: using PostgresStore.")
            return store
        except Exception as exc:  # noqa: BLE001
            logger.warning("PostgresStore failed to initialise (%r) — memory disabled.", exc)
            return None

    logger.warning("Unknown SATQUERY_MEMORY_BACKEND=%r — memory disabled.", backend)
    return None


def _build_checkpointer() -> object | None:
    """
    Build a MemorySaver for in-thread session history.
    Only enabled when a store is also active (memory_backend != "none").
    """
    if settings.memory_backend == "none":
        return None
    try:
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()
    except Exception as exc:  # noqa: BLE001
        logger.warning("MemorySaver failed (%r) — checkpointer disabled.", exc)
        return None


def build_graph():
    g = StateGraph(SatQueryState)

    g.add_node("validate", validate_input)
    g.add_node("plan", plan)
    g.add_node("execute", execute)
    g.add_node("respond", respond)

    g.add_edge(START, "validate")
    g.add_edge("validate", "plan")
    g.add_conditional_edges(
        "plan",
        route_after_plan,
        {
            "execute": "execute",
            "respond": "respond",
        },
    )
    g.add_edge("execute", "respond")
    g.add_edge("respond", END)

    store = _build_store()
    checkpointer = _build_checkpointer()

    compile_kwargs: dict = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer
    if store is not None:
        compile_kwargs["store"] = store

    return g.compile(**compile_kwargs)


satquery_graph = build_graph()
