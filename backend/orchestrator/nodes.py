"""LangGraph nodes for SatQuery."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from backend.orchestrator.registry import (
    TOOL_DESCRIBE_REGION,
    format_tool_success,
    trusted_args_for_tool,
)
from backend.orchestrator.state import SatQueryState, trace_entry
from backend.orchestrator.synthesis import synthesize_final_answer
from backend.tools.executor import execute_tool

logger = logging.getLogger("satquery.pipeline")


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


def load_knowledge_base(state: SatQueryState) -> dict[str, Any]:
    """Load the per-image knowledge base built at upload time (see
    ingest_graph.py) so the VLM's first description can be grounded in it.
    """
    if state.get("knowledge_base"):
        update: dict[str, Any] = {
            "execution_trace": [trace_entry("load_knowledge_base", "provided inline")]
        }
        kb_file_path = state["knowledge_base"].get("file_path")
        if kb_file_path and not state.get("lulc_raster_path"):
            update["lulc_raster_path"] = kb_file_path
        return update

    input_file = state.get("input_file")
    if not input_file:
        return {
            "execution_trace": [trace_entry("load_knowledge_base", "no input_file")]
        }

    kb_path = Path(input_file).with_suffix(".kb.json")
    if not kb_path.exists():
        update = {
            "execution_trace": [
                trace_entry("load_knowledge_base", "no knowledge base on disk")
            ]
        }
        if not state.get("lulc_raster_path"):
            update["lulc_raster_path"] = input_file
        return update

    try:
        knowledge_base = json.loads(kb_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not load knowledge base from %s: %r", kb_path, exc)
        update = {
            "execution_trace": [trace_entry("load_knowledge_base", "failed to load")]
        }
        if not state.get("lulc_raster_path"):
            update["lulc_raster_path"] = input_file
        return update

    update = {
        "knowledge_base": knowledge_base,
        "execution_trace": [trace_entry("load_knowledge_base", "loaded from disk")],
    }
    kb_file_path = knowledge_base.get("file_path") or input_file
    if kb_file_path and not state.get("lulc_raster_path"):
        update["lulc_raster_path"] = kb_file_path
    return update


def vlm_initial_description(state: SatQueryState) -> dict[str, Any]:
    """Ground the first response in the upload-time knowledge base: ask the
    vision model to describe the image with the known bands/lat/long/place
    name already in hand, before any further tool calls are considered.

    Recorded into tool_results (not just initial_description) so the
    tool-loop subgraph's continuation planner sees it as already-gathered
    evidence -- it can decide "that's enough, finish" or "I still need
    another tool" using the exact same logic as any other hop.
    """
    input_file = state.get("input_file")
    if not input_file:
        return {
            "execution_trace": [
                trace_entry("vlm_initial_description", "no image to describe")
            ]
        }

    knowledge_base = state.get("knowledge_base") or {}
    query = state.get("query") or ""
    contextualized_query = (
        f"{query}\n\nKnown metadata about this image: {json.dumps(knowledge_base)}"
    )

    result = execute_tool(
        "analyze_imagery_vlm",
        {"image_path": input_file, "query": contextualized_query},
    )
    if result.get("status") != "success":
        logger.info("[INITIAL DESCRIPTION FAILED] %s", result.get("error"))
        return {
            "execution_trace": [trace_entry("vlm_initial_description", "failed")]
        }

    description = result.get("text") or ""
    logger.info("[INITIAL DESCRIPTION] chars=%d", len(description))
    update: dict[str, Any] = {
        "initial_description": description,
        "tool_hops": (state.get("tool_hops") or 0) + 1,
        "tool_results": [{
            "tool": "analyze_imagery_vlm",
            "result": result,
        }],
        "execution_trace": [trace_entry("vlm_initial_description", "generated")],
    }

    # This automatic call goes through execute_tool() directly, not
    # tool_loop_graph.py's tool_node -- so it needs its own copy of the same
    # region-fields-from-affine-converted-geometry merge (see that module's
    # tool_node for TOOL_MARK_REGION/TOOL_VLM), or a query like "mark the
    # river" that happens to get its bbox/polygon from this initial call
    # (fired before the planner is even consulted) would never surface
    # region_bbox at all -- silently skipping describe_region_auto right
    # after this node and leaving the frontend showing only the raw,
    # ungeoreferenced guess.
    region_bbox = result.get("region_bbox")
    if region_bbox and not state.get("region_bbox"):
        update["region_bbox"] = region_bbox
        if result.get("region_polygon"):
            update["region_polygon"] = result["region_polygon"]
        if result.get("region_centroid"):
            update["region_centroid"] = result["region_centroid"]

    return update


def describe_region_if_marked(state: SatQueryState) -> dict[str, Any]:
    """Ground a user-marked sub-region (region_bbox) exactly once per
    request, deterministically -- not left to the tool-loop planner's
    discretion, which otherwise sometimes decides the whole-image
    description already covers it and never calls describe_marked_region at
    all (observed in practice: it fired for a first marked-region question in
    a conversation, then silently skipped it for two later questions against
    newly marked regions, because the planner treated the earlier answer/the
    automatic whole-image description as already sufficient).

    Recorded into tool_results (like vlm_initial_description) so the
    continuation planner sees it as already-gathered evidence and doesn't
    need to -- and shouldn't -- call describe_marked_region again itself.
    """
    region_bbox = state.get("region_bbox")
    input_file = state.get("input_file")
    if not region_bbox or not input_file:
        return {
            "execution_trace": [
                trace_entry("describe_region_auto", "no marked region")
            ]
        }

    args = trusted_args_for_tool(TOOL_DESCRIBE_REGION, state)
    result = execute_tool(TOOL_DESCRIBE_REGION, args)
    if result.get("status") != "success":
        logger.info("[REGION DESCRIBE FAILED] %s", result.get("error"))
        return {
            "execution_trace": [trace_entry("describe_region_auto", "failed")]
        }

    logger.info("[REGION DESCRIBE] chars=%d", len(result.get("text") or ""))
    return {
        "tool_hops": (state.get("tool_hops") or 0) + 1,
        "tool_results": [{
            "tool": TOOL_DESCRIBE_REGION,
            "result": result,
        }],
        "execution_trace": [trace_entry("describe_region_auto", "generated")],
    }


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
        logger.info("[ORCHESTRATOR DECISION] status=clarify reason=%r", reason)
        return {
            "status": "clarify",
            "final_answer": reason or "Could you clarify what you'd like me to do?",
            "execution_trace": [
                trace_entry("respond", "clarify")
            ],
        }

    # A bare "chat" action only means "this needs no tool at all" when
    # nothing has been gathered yet. If tool_results (or the VLM's initial
    # description) is already populated -- e.g. the mock keyword planner
    # returning "chat" on a continuation hop because no keyword matched --
    # that's "stop gathering, answer from what's collected", not "no tool
    # was ever needed"; fall through to the tool_results synthesis below
    # instead of overwriting real findings with the canned reply.
    if action == "chat" and not (state.get("tool_results") or state.get("initial_description")):
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
        if state.get("initial_description"):
            logger.info("[ORCHESTRATOR DECISION] status=success (initial description only)")
            return {
                "status": "success",
                "final_answer": state["initial_description"],
                "execution_trace": [
                    trace_entry("respond", "success (initial description only)")
                ],
            }
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

    prefix = ""
    if len(results) > 1:
        prefix = f"Completed {len(results)} tool calls. "

    synthesized = synthesize_final_answer(state, results)
    final_answer = synthesized or (prefix + format_tool_success(tool_name, latest))
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
