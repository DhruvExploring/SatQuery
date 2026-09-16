"""Compile the SatQuery LangGraph orchestration."""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from backend.config.settings import settings
from backend.orchestrator.nodes import (
    describe_region_if_marked,
    load_knowledge_base,
    respond,
    validate_input,
    vlm_initial_description,
)
from backend.orchestrator.router import route_after_load_kb, route_after_validate
from backend.orchestrator.state import SatQueryState
from backend.orchestrator.tool_loop_graph import tool_loop_subgraph

logger = logging.getLogger(__name__)

GRAPH_INVOKE_CONFIG = {"recursion_limit": 50}

_REDUCER_LIST_FIELDS = ("tool_results", "errors", "execution_trace")


def _tool_loop_node(state: SatQueryState) -> dict[str, Any]:
    """Invoke the tool_loop_subgraph and return only its DELTA for
    reducer-typed list fields (tool_results/errors/execution_trace).

    A compiled StateGraph invoked directly returns its *full* resulting
    state, reducer fields included. Adding it as a node as-is would hand
    that full state back to this outer graph's own `Annotated[list, add]`
    reducers, which then concatenate it onto what's already there --
    double-counting every entry the subgraph merely inherited from the
    parent at entry. Slicing off the length already present at entry keeps
    only what the subgraph actually added.
    """
    result = tool_loop_subgraph.invoke(state)
    update: dict[str, Any] = {}
    for key, value in result.items():
        if key in _REDUCER_LIST_FIELDS:
            prior_len = len(state.get(key) or [])
            update[key] = value[prior_len:]
        else:
            update[key] = value
    return update


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
    graph.add_node("load_knowledge_base", load_knowledge_base)
    graph.add_node("vlm_initial_description", vlm_initial_description)
    # Deterministic, runs regardless of the tool-loop planner's discretion --
    # see describe_region_if_marked's docstring for why this can't be left
    # to the planner to decide on its own.
    graph.add_node("describe_region_auto", describe_region_if_marked)
    # See _tool_loop_node's docstring for why this wraps tool_loop_subgraph
    # instead of adding the compiled subgraph directly as a node. It loops
    # start(llm) <-> tool internally until the planner decides no more
    # tools are needed, then falls through here to respond().
    graph.add_node("tool_loop", _tool_loop_node)
    graph.add_node("respond", respond)

    graph.add_edge(START, "validate")
    graph.add_conditional_edges(
        "validate",
        route_after_validate,
        {
            "error": "respond",
            "continue": "load_knowledge_base",
        },
    )
    graph.add_conditional_edges(
        "load_knowledge_base",
        route_after_load_kb,
        {
            "describe": "vlm_initial_description",
            "skip": "describe_region_auto",
        },
    )
    graph.add_edge("vlm_initial_description", "describe_region_auto")
    graph.add_edge("describe_region_auto", "tool_loop")
    graph.add_edge("tool_loop", "respond")
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
