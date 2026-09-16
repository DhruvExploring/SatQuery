"""The recursive tool-calling loop: start -> llm -> tool -> end.

`llm` consults the planner for one action; if it decides a tool is needed,
`tool` runs it and control loops back to `llm` with the result folded into
state. Otherwise the subgraph ends and the outer graph's respond node takes
over. Compiled once and embedded as a single node in the outer satquery_graph
(backend/orchestrator/graph.py) -- it shares SatQueryState, so it can be
added directly as a node there.

This replaces the old handshake.py deterministic agenda system: every query
(including former "mission" workflows) is now driven purely by the LLM
planner deciding one hop at a time, guided by the routing hints in llm.py.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from langgraph.graph import END, START, StateGraph

from backend.orchestrator import llm as llm_module
from backend.orchestrator.registry import (
    TOOL_AFFINE_MARKUP,
    TOOL_GEOCODE_FORWARD,
    TOOL_SCENE_IDENTITY,
    derive_grounding_fields,
    location_ready_for_tool,
    trusted_args_for_tool,
)
from backend.orchestrator.state import SatQueryState, trace_entry
from backend.tools.executor import execute_tool

logger = logging.getLogger("satquery.pipeline")

MAX_TOOL_HOPS = 10

_FETCH_TOOLS = {
    "fetch_satellite_imagery",
    "fetch_optical_imagery",
    "fetch_multispectral_imagery",
    "fetch_sar",
    "fetch_sar_imagery",
}


def llm_node(state: SatQueryState) -> dict[str, Any]:
    if state.get("errors"):
        plan = {
            "action": "respond_error",
            "tool": None,
            "args": {},
            "reason": "Input validation failed; skip tool selection.",
        }
        return {
            "plan": plan,
            "execution_trace": [trace_entry("llm", "validation errors, skipping planner")],
        }

    hops = state.get("tool_hops") or 0
    if hops >= MAX_TOOL_HOPS:
        plan = {
            "action": "respond_error",
            "tool": None,
            "args": {},
            "reason": "Exceeded max tool hops.",
        }
        return {
            "plan": plan,
            "errors": ["Exceeded max tool hops."],
            "execution_trace": [trace_entry("llm", "max hops exceeded")],
        }

    plan = llm_module.plan_single_tool(state)
    action = plan.get("action")
    tool = plan.get("tool")
    reason = plan.get("reason") or ""
    summary = f"action={action}" + (f" tool={tool}" if tool else "")
    if action == "call_tool":
        logger.info("[ORCHESTRATOR TOOL CALL] tool=%s reason=%r", tool, reason)
    else:
        logger.info("[ORCHESTRATOR DECISION] action=%s reason=%r", action, reason)
    return {"plan": plan, "execution_trace": [trace_entry("llm", summary)]}


def route_after_llm(state: SatQueryState) -> str:
    plan = state.get("plan") or {}
    return "tool" if plan.get("action") == "call_tool" else "end"


def tool_node(state: SatQueryState) -> dict[str, Any]:
    planned = state.get("plan")
    if not planned or planned.get("action") != "call_tool" or not planned.get("tool"):
        return {
            "errors": ["tool node ran without a call_tool plan."],
            "execution_trace": [trace_entry("tool", "skipped: no call_tool plan")],
        }

    tool_name = planned["tool"]
    args = dict(planned.get("args") or {})
    if not args:
        if not location_ready_for_tool(tool_name, state):
            return {
                "errors": [f"{tool_name} is missing a required input."],
                "execution_trace": [
                    trace_entry("tool", f"blocked {tool_name}: missing input")
                ],
            }
        args = trusted_args_for_tool(tool_name, state)

    logger.info("[TOOL CALL] %s args=%s", tool_name, args)
    started = time.perf_counter()
    result = execute_tool(tool_name, args)
    duration_ms = (time.perf_counter() - started) * 1000.0
    logger.info(
        "[TOOL OUTPUT] %s status=%s duration_ms=%.0f",
        tool_name,
        result.get("status", "unknown"),
        duration_ms,
    )

    update: dict[str, Any] = {
        "tool_hops": (state.get("tool_hops") or 0) + 1,
        "tool_results": [{
            "tool": tool_name,
            "result": result,
            "duration_ms": duration_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
        "execution_trace": [
            trace_entry("tool", f"{tool_name} status={result.get('status', 'unknown')}")
        ],
    }

    if result.get("status") == "success":
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        if tool_name in _FETCH_TOOLS:
            path = data.get("file_path") or result.get("file_path")
            if path:
                update["input_file"] = path
                # No agenda role (t1/t2) to key off any more -- first fetch
                # fills "before", the next fills "after".
                if not state.get("raster_before_path"):
                    update["raster_before_path"] = path
                elif not state.get("raster_after_path"):
                    update["raster_after_path"] = path
        elif tool_name == "compute_vegetation_indices":
            path = data.get("file_path") or result.get("file_path")
            if path:
                update["input_file"] = path
                if not state.get("index_before_path"):
                    update["index_before_path"] = path
                elif not state.get("index_after_path"):
                    update["index_after_path"] = path
        elif tool_name == "inspect_geotiff_metadata":
            path = (result.get("file") or {}).get("file_path")
            if path:
                update["input_file"] = path
            # Any successful inspection reveals the file's real location --
            # make it available to whatever tool gets picked next (e.g. a
            # fetch_* tool that was only missing a bbox) instead of ending
            # the request on a clarify.
            for field, value in derive_grounding_fields(result).items():
                if not state.get(field):
                    update[field] = value
        elif tool_name == "analyze_temporal_change":
            products = result.get("generated_products") or {}
            if products.get("change_mask_path"):
                update["last_change_mask_path"] = products["change_mask_path"]
        elif tool_name == TOOL_GEOCODE_FORWARD:
            best = result.get("best_match") or {}
            if best.get("latitude") is not None and best.get("longitude") is not None:
                landmark = {
                    "name": best.get("name") or state.get("query") or "location",
                    "latitude": best["latitude"],
                    "longitude": best["longitude"],
                }
                update["geocoded_landmarks"] = (state.get("geocoded_landmarks") or []) + [landmark]
                if state.get("latitude") is None:
                    update["latitude"] = best["latitude"]
                    update["longitude"] = best["longitude"]
        elif tool_name == TOOL_SCENE_IDENTITY:
            landmarks = [
                {"name": item.get("name"), "latitude": item.get("latitude"), "longitude": item.get("longitude")}
                for item in (result.get("landmarks") or [])
                if item.get("latitude") is not None and item.get("longitude") is not None
            ]
            if landmarks:
                update["geocoded_landmarks"] = (state.get("geocoded_landmarks") or []) + landmarks
            centroid = result.get("centroid") or {}
            if state.get("latitude") is None and centroid.get("latitude") is not None:
                update["latitude"] = centroid["latitude"]
                update["longitude"] = centroid["longitude"]
        elif tool_name == TOOL_AFFINE_MARKUP:
            path = result.get("marked_image_path")
            if path:
                update["input_file"] = path

    return update


def _build_tool_loop_graph():
    graph = StateGraph(SatQueryState)

    graph.add_node("llm", llm_node)
    graph.add_node("tool", tool_node)

    graph.add_edge(START, "llm")
    graph.add_conditional_edges(
        "llm",
        route_after_llm,
        {"tool": "tool", "end": END},
    )
    graph.add_edge("tool", "llm")

    return graph.compile()


tool_loop_subgraph = _build_tool_loop_graph()
