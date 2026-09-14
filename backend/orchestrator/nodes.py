"""LangGraph nodes for SatQuery."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from backend.orchestrator.handshake import apply_advance, build_plan_update
from backend.orchestrator import llm as llm_module
from backend.orchestrator.registry import format_tool_success
from backend.orchestrator.state import SatQueryState, trace_entry
from backend.orchestrator.synthesis import synthesize_final_answer
from backend.tools.executor import execute_tool

logger = logging.getLogger("satquery.pipeline")


def clean_final_output(text: str) -> str:
    """Sanitize user-facing output against internal handshake tags or prompt leakage."""
    if not text:
        return ""
    # Strip multi-line or single-line thought/reasoning blocks
    text = re.sub(r"^(?:Thought|Plan|Reasoning|Observation|Handshake):\s*[^\n]*(?:\n+|$)", "", text, flags=re.IGNORECASE)
    # Strip handshake step markers like "Completed 2-step handshake. "
    text = re.sub(r"^Completed \d+-step handshake\.\s*", "", text, flags=re.IGNORECASE)
    # Strip bracketed provider prefixes like "[Tavily] " or "[DuckDuckGo (Fail-safe)] "
    text = re.sub(r"^\[(?:Tavily|DuckDuckGo|Web)[^\]]*\]\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def validate_input(state: SatQueryState) -> dict[str, Any]:
    logger.info("[REQUEST RECEIVED] query=%r", (state.get("query") or "").strip())
    if state.get("input_file"):
        logger.info("[IMAGE RECEIVED] input_file=%s", state.get("input_file"))

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
    if errors:
        logger.info("[VALIDATION FAILED] %s", "; ".join(errors))
    else:
        logger.info("[VALIDATION OK]")

    return {
        "errors": errors,
        "execution_trace": [trace_entry("validate", summary)],
    }


def plan(state: SatQueryState) -> dict[str, Any]:
    provider = llm_module.settings.orchestrator_provider
    logger.info(
        "[ORCHESTRATOR INITIATED] provider=%s model=%s",
        provider,
        llm_module.settings.orchestrator_model if provider != "mock" else "keyword-planner",
    )
    update = build_plan_update(state, llm_module.plan_single_tool)
    planned = update.get("plan") or {}
    action = planned.get("action")
    tool = planned.get("tool")
    reason = planned.get("reason") or ""
    summary = f"action={action}" + (f" tool={tool}" if tool else "")
    if action == "call_tool":
        logger.info("[ORCHESTRATOR TOOL CALL] tool=%s reason=%r", tool, reason)
    else:
        logger.info("[ORCHESTRATOR DECISION] action=%s reason=%r", action, reason)
    update["execution_trace"] = [trace_entry("plan", summary)]
    return update


def execute(state: SatQueryState) -> dict[str, Any]:
    planned = state.get("plan")
    if not planned or planned.get("action") != "call_tool" or not planned.get("tool"):
        return {
            "errors": ["execute node ran without a call_tool plan."],
            "handshake_complete": True,
            "execution_trace": [trace_entry("execute", "skipped: no call_tool plan")],
        }

    tool_name = planned["tool"]
    args = dict(planned.get("args") or {})
    if not args:
        from backend.orchestrator.registry import (
            location_ready_for_tool,
            trusted_args_for_tool,
        )

        if not location_ready_for_tool(tool_name, state):
            return {
                "errors": [f"{tool_name} is missing a required input."],
                "handshake_complete": True,
                "execution_trace": [
                    trace_entry("execute", f"blocked {tool_name}: missing input")
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
        "tool_results": [{
            "tool": tool_name,
            "result": result,
            "duration_ms": duration_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
        "execution_trace": [
            trace_entry("execute", f"{tool_name} status={result.get('status', 'unknown')}")
        ],
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


def advance(state: SatQueryState) -> dict[str, Any]:
    update = apply_advance(state)
    hops = update.get("handshake_hops")
    complete = update.get("handshake_complete")
    summary = f"hops={hops} complete={complete}"
    if update.get("errors"):
        summary += " gated"
    logger.info(
        "[ORCHESTRATOR ADVANCE] hops=%s complete=%s%s",
        hops,
        complete,
        " (more steps -> back to plan)" if not complete else " (handshake finished -> respond)",
    )
    update["execution_trace"] = [trace_entry("advance", summary)]
    return update

def respond(state: SatQueryState) -> dict[str, Any]:
    errors = state.get("errors") or []

    if errors:
        logger.info("[ORCHESTRATOR DECISION] status=error errors=%s", errors)
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
        logger.info("[ORCHESTRATOR DECISION] status=error reason=%r", planned.get("reason"))
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
        reason = (planned.get("reason") or "").strip()
        guide = (
            "I can fetch optical, multispectral, or SAR imagery, "
            "weather, vegetation indices, GeoTIFF inspection, temporal change, "
            "or land-cover/terrain analysis. Provide the required input: "
            "bbox [min_lon, min_lat, max_lon, max_lat] "
            "(Delhi: [77.10, 28.50, 77.30, 28.70]), "
            "latitude and longitude for weather, "
            "input_file for indices/inspection, "
            "raster_before_path and raster_after_path for change detection, "
            "post_start_date and post_end_date for a T2 fetch window, "
            "or lulc_raster_path for land cover."
        )
        logger.info("[ORCHESTRATOR DECISION] status=clarify reason=%r", reason)
        return {
            "status": "clarify",
            "final_answer": f"{reason} {guide}".strip() if reason else guide,
            "execution_trace": [
                trace_entry("respond", "clarify")
            ],
        }

    if action == "chat":
        logger.info("[ORCHESTRATOR DECISION] status=ok (chat, no tool needed)")
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
        logger.info("[ORCHESTRATOR DECISION] status=error (no tool output collected)")
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
            # Some tools' internal pre-flight checks (e.g. Tool 7's grid-
            # misalignment / band-resolution / no-valid-pixels errors, Tool
            # 8's no-valid-LULC-data error) return a top-level "message"
            # instead of nesting it under "error" -- these are often the
            # most specific, actionable messages available, so check here
            # before falling back to a generic one.
            or latest.get("message")
            or "Tool execution failed."
        )
        logger.info("[ORCHESTRATOR DECISION] status=error tool=%s message=%r", tool_name, message)
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

    synthesized = synthesize_final_answer(state, results)
    raw_answer = synthesized or format_tool_success(tool_name, latest)
    final_answer = clean_final_output(raw_answer)
    logger.info(
        "[ORCHESTRATOR DECISION] status=success tool=%s narrative=%s final_answer=%r",
        tool_name,
        "synthesized" if synthesized else "templated",
        final_answer,
    )

    return {
        "status": "success",
        "final_answer": final_answer,
        "execution_trace": [
            trace_entry("respond", "success (synthesized)" if synthesized else "success")
        ],
    }
