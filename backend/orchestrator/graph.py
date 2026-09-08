"""Compile the SatQuery LangGraph orchestration."""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from backend.config.settings import settings
from backend.orchestrator.nodes import advance, execute, plan, respond, validate_input
from backend.orchestrator.router import route_after_advance, route_after_plan
from backend.orchestrator.state import SatQueryState

logger = logging.getLogger(__name__)

GRAPH_INVOKE_CONFIG = {"recursion_limit": 50}


def _build_store() -> object | None:
    """Build the optional cross-thread memory store."""
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
            logger.info(
                "LangMem: using InMemoryStore (dev mode — lost on restart)."
            )
            return store
        except Exception as exc:
            logger.warning(
                "InMemoryStore failed to initialise (%r) — memory disabled.",
                exc,
            )
            return None

    if backend == "postgres":
        if not settings.memory_db_url:
            logger.warning(
                "SATQUERY_MEMORY_BACKEND=postgres but "
                "SATQUERY_MEMORY_DB_URL is not set — memory disabled."
            )
            return None

        try:
            from langgraph.store.postgres import PostgresStore

            store = PostgresStore.from_conn_string(
                settings.memory_db_url,
                index={
                    "dims": 1536,
                    "embed": settings.memory_embed_model,
                },
            )
            logger.info("LangMem: using PostgresStore.")
            return store
        except Exception as exc:
            logger.warning(
                "PostgresStore failed to initialise (%r) — memory disabled.",
                exc,
            )
            return None

    logger.warning(
        "Unknown SATQUERY_MEMORY_BACKEND=%r — memory disabled.",
        backend,
    )
    return None


def _build_checkpointer() -> object | None:
    """Build the optional in-thread memory checkpointer."""
    if settings.memory_backend == "none":
        return None

    try:
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()
    except Exception as exc:
        logger.warning(
            "MemorySaver failed (%r) — checkpointer disabled.",
            exc,
        )
        return None


def build_graph():
    graph = StateGraph(SatQueryState)

    graph.add_node("validate", validate_input)
    graph.add_node("plan", plan)
    graph.add_node("execute", execute)
    graph.add_node("advance", advance)
    graph.add_node("respond", respond)

    graph.add_edge(START, "validate")
    graph.add_edge("validate", "plan")
    graph.add_conditional_edges(
        "plan",
        route_after_plan,
        {
            "execute": "execute",
            "respond": "respond",
        },
    )
    graph.add_edge("execute", "advance")
    graph.add_conditional_edges(
        "advance",
        route_after_advance,
        {
            "continue": "plan",
            "respond": "respond",
        },
    )
    graph.add_edge("respond", END)

    store = _build_store()
    checkpointer = _build_checkpointer()

    compile_kwargs: dict = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer
    if store is not None:
        compile_kwargs["store"] = store

    return graph.compile(**compile_kwargs)


def invoke_satquery(state: SatQueryState, graph=None):
    compiled = graph if graph is not None else satquery_graph
    return compiled.invoke(state, GRAPH_INVOKE_CONFIG)


satquery_graph = build_graph()
