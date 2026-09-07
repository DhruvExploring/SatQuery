"""LangGraph nodes for SatQuery."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from backend.orchestrator.llm import make_plan
from backend.orchestrator.registry import (
    format_tool_success,
    location_ready_for_tool,
    trusted_args_for_tool,
)
from backend.orchestrator.state import SatQueryState, trace_entry
from backend.tools.executor import execute_tool


def validate_input(state: SatQueryState) -> dict[str, Any]:
    errors: list[str] = []
    query = (state.get("query") or "").strip()

    if not query:
        errors.append("query must not be empty.")

    bbox = state.get("bbox")
    if bbox is not None:
        if not isinstance(bbox, list) or len(bbox) != 4:
            errors.append(
                "bbox must be [min_lon, min_lat, max_lon, max_lat]."
            )
        else:
            try:
                min_lon, min_lat, max_lon, max_lat = (
                    float(x) for x in bbox
                )
            except (TypeError, ValueError):
                errors.append("bbox values must be numbers.")
            else:
                if not -180 <= min_lon <= 180 or not -180 <= max_lon <= 180:
                    errors.append(
                        "bbox longitude must be between -180 and 180."
                    )
                if not -90 <= min_lat <= 90 or not -90 <= max_lat <= 90:
                    errors.append(
                        "bbox latitude must be between -90 and 90."
                    )
                if min_lon >= max_lon:
                    errors.append(
                        "bbox min_lon must be smaller than max_lon."
                    )
                if min_lat >= max_lat:
                    errors.append(
                        "bbox min_lat must be smaller than max_lat."
                    )

    for name in ("latitude", "longitude"):
        value = state.get(name)
        if value is None:
            continue

        try:
            number = float(value)
        except (TypeError, ValueError):
            errors.append(f"{name} must be a number.")
            continue

        if name == "latitude" and not -90 <= number <= 90:
            errors.append("latitude must be between -90 and 90.")

        if name == "longitude" and not -180 <= number <= 180:
            errors.append("longitude must be between -180 and 180.")

    summary = (
        "input ok"
        if not errors
        else f"{len(errors)} validation error(s)"
    )

    return {
        "errors": errors,
        "execution_trace": [trace_entry("validate", summary)],
    }


def plan(state: SatQueryState) -> dict[str, Any]:
    planned = make_plan(state)

    action = planned.get("action")
    tool = planned.get("tool")
    summary = f"action={action}" + (
        f" tool={tool}" if tool else ""
    )

    return {
        "plan": planned,
        "execution_trace": [trace_entry("plan", summary)],
    }


def execute(state: SatQueryState) -> dict[str, Any]:
    planned = state.get("plan")
    if not planned or planned.get("action") != "call_tool" or not planned.get("tool"):
        return {"errors": ["execute node ran without a call_tool plan."], "execution_trace": [trace_entry("execute", "skipped: no call_tool plan")]}

    tool_name = planned["tool"]
    if not location_ready_for_tool(tool_name, state):
        return {"errors": [f"{tool_name} is missing a required input."], "execution_trace": [trace_entry("execute", f"blocked {tool_name}: missing input")]}

    args = trusted_args_for_tool(tool_name, state)
    started = time.perf_counter()
    result = execute_tool(tool_name, args)
    duration_ms = (time.perf_counter() - started) * 1000.0

    update: dict[str, Any] = {
        "tool_results": [{"tool": tool_name, "result": result, "duration_ms": duration_ms, "timestamp": datetime.now(timezone.utc).isoformat()}],
        "execution_trace": [trace_entry("execute", f"{tool_name} status={result.get('status', 'unknown')}" )],
    }

    if result.get("status") == "success":
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        if tool_name in (
            "fetch_satellite_imagery",
            "fetch_optical_imagery",
            "fetch_multispectral_imagery",
            "fetch_sar",
            "fetch_sar_imagery",
        ):
            path = data.get("file_path") or result.get("file_path")
            if path:
                update["input_file"] = path
        elif tool_name == "compute_vegetation_indices":
            path = data.get("file_path") or result.get("file_path")
            if path:
                update["input_file"] = path
        elif tool_name == "inspect_geotiff_metadata":
            path = (result.get("file") or {}).get("file_path")
            if path:
                update["input_file"] = path
        elif tool_name == "analyze_temporal_change":
            products = result.get("generated_products") or {}
            if products.get("change_mask_path"):
                update["last_change_mask_path"] = products["change_mask_path"]

    return update

def respond(state: SatQueryState) -> dict[str, Any]:
    errors = state.get("errors") or []

    if errors:
        return {
            "status": "error",
            "final_answer": (
                "Request could not be processed: "
                + " ".join(errors)
            ),
            "execution_trace": [
                trace_entry("respond", "error")
            ],
        }

    planned = state.get("plan") or {
        "action": "chat",
        "tool": None,
        "args": {},
        "reason": "",
    }

    action = planned.get("action")

    if action == "respond_error":
        return {
            "status": "error",
            "final_answer": (
                planned.get("reason")
                or "Request could not be processed."
            ),
            "execution_trace": [
                trace_entry("respond", "respond_error")
            ],
        }

    if action == "clarify":
        return {
            "status": "clarify",
            "final_answer": (
                "I can fetch optical, multispectral, or SAR imagery, "
                "or weather context, or run raster analysis. I need the required input. Provide "
                "bbox [min_lon, min_lat, max_lon, max_lat] "
                "(Delhi: [77.10, 28.50, 77.30, 28.70]), "
                "or for weather latitude and longitude."
            ),
            "execution_trace": [
                trace_entry("respond", "clarify")
            ],
        }

    if action == "chat":
        return {
            "status": "ok",
            "final_answer": (
                "I am SatQuery's controller for remote-sensing tools. "
                "Ask me to fetch optical, multispectral, SAR imagery, weather, "
                "compute indices, inspect a GeoTIFF, detect temporal change, "
                "or analyze land cover and terrain."
            ),
            "execution_trace": [
                trace_entry("respond", "chat")
            ],
        }

    results = state.get("tool_results") or []

    if not results:
        return {
            "status": "error",
            "final_answer": "No tool output was collected.",
            "execution_trace": [
                trace_entry(
                    "respond",
                    "error: no tool output",
                )
            ],
        }

    latest = results[-1]["result"]
    tool_name = results[-1]["tool"]

    if latest.get("status") != "success":
        error = latest.get("error") or {}
        message = (
            error.get("message")
            or "Tool execution failed."
        )
        return {
            "status": "error",
            "final_answer": f"{tool_name} failed: {message}",
            "execution_trace": [
                trace_entry(
                    "respond",
                    f"error: {tool_name}",
                )
            ],
        }

    return {
        "status": "success",
        "final_answer": format_tool_success(
            tool_name,
            latest,
        ),
        "execution_trace": [
            trace_entry("respond", "success")
        ],
    }
