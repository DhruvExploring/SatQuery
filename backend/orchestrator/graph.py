"""Compile the SatQuery Week-1 graph.

    START → validate → plan → (router) → execute → respond → END
                                 └── respond → END

Wiring lives here. Business logic lives in nodes.py / router.py.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from backend.orchestrator.nodes import execute, plan, respond, validate_input
from backend.orchestrator.router import route_after_plan
from backend.orchestrator.state import SatQueryState


def build_graph():
    graph = StateGraph(SatQueryState)

    graph.add_node("validate", validate_input)
    graph.add_node("plan", plan)
    graph.add_node("execute", execute)
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
    graph.add_edge("execute", "respond")
    graph.add_edge("respond", END)

    # Stateless per request: no checkpointer. Do not compile this singleton
    # with a checkpointer — that would persist state across HTTP requests
    # unless you switch to per-thread / per-session graphs.
    return graph.compile()


satquery_graph = build_graph()
