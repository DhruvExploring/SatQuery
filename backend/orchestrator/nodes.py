"""Graph nodes. Each function: State in → partial State out.

Do not put Sentinel Hub URLs or FastAPI status codes here.
"""

from __future__ import annotations

from typing import Any

from backend.orchestrator.llm import make_plan
from backend.orchestrator.state import SatQueryState
from backend.tools.executor import execute_tool


def validate_input(state: SatQueryState) -> dict[str, Any]:
    """Reject obviously bad inputs before planning. Does not call tools."""

    errors: list[str] = []
    query = (state.get("query") or "").strip()
    if not query:
        errors.append("query must not be empty.")

    bbox = state.get("bbox")
    if bbox is not None:
        if not isinstance(bbox, list) or len(bbox) != 4:
            errors.append("bbox must be [min_lon, min_lat, max_lon, max_lat].")
        else:
            min_lon, min_lat, max_lon, max_lat = bbox
            try:
                min_lon, min_lat, max_lon, max_lat = (
                    float(min_lon),
                    float(min_lat),
                    float(max_lon),
                    float(max_lat),
                )
            except (TypeError, ValueError):
                errors.append("bbox values must be numbers.")
            else:
                if not -180 <= min_lon <= 180 or not -180 <= max_lon <= 180:
                    errors.append("bbox longitude must be between -180 and 180.")
                if not -90 <= min_lat <= 90 or not -90 <= max_lat <= 90:
                    errors.append("bbox latitude must be between -90 and 90.")
                if min_lon >= max_lon:
                    errors.append("bbox min_lon must be smaller than max_lon.")
                if min_lat >= max_lat:
                    errors.append("bbox min_lat must be smaller than max_lat.")

    return {"errors": errors}


def plan(state: SatQueryState) -> dict[str, Any]:
    """Fill state['plan']. Mock now; real LLM later via the same function."""

    return {"plan": make_plan(state)}


def execute(state: SatQueryState) -> dict[str, Any]:
    """Run the planned tool and APPEND one ToolResult."""

    planned = state.get("plan")
    if not planned or planned.get("action") != "call_tool" or not planned.get("tool"):
        return {
            "errors": ["execute node ran without a call_tool plan."],
        }

    tool_name = planned["tool"]
    result = execute_tool(tool_name, planned.get("args") or {})
    return {
        "tool_results": [{"tool": tool_name, "result": result}],
    }


def respond(state: SatQueryState) -> dict[str, Any]:
    """Turn State into a user-facing answer. Does not invent file paths."""

    errors = state.get("errors") or []
    if errors:
        return {
            "status": "error",
            "final_answer": "Request could not be processed: " + " ".join(errors),
        }

    planned = state.get("plan") or {
        "action": "chat",
        "tool": None,
        "args": {},
        "reason": "",
    }
    action = planned.get("action")

    if action == "clarify":
        return {
            "status": "clarify",
            "final_answer": (
                "I can fetch Sentinel-2 imagery, but I need a bounding box "
                "as [min_lon, min_lat, max_lon, max_lat]. For Delhi you can "
                "use [77.10, 28.50, 77.30, 28.70]."
            ),
        }

    if action == "chat":
        return {
            "status": "ok",
            "final_answer": (
                "I am SatQuery's controller. I do not answer satellite "
                "questions from memory. Ask me to fetch imagery (and later "
                "to run specialist tools) and I will call those tools."
            ),
        }

    results = state.get("tool_results") or []
    if not results:
        return {
            "status": "error",
            "final_answer": "No tool output was collected.",
        }

    latest = results[-1]["result"]
    tool_name = results[-1]["tool"]

    if latest.get("status") != "success":
        error = latest.get("error") or {}
        message = error.get("message") or "Tool execution failed."
        return {
            "status": "error",
            "final_answer": f"{tool_name} failed: {message}",
        }

    # Build a generic success message from whichever fields the tool returned.
    data = latest.get("data") or {}
    source = latest.get("source") or {}
    quality = latest.get("quality") or {}

    parts: list[str] = []

    collection = source.get("collection") or tool_name
    scene_id = source.get("scene_id")
    if scene_id:
        parts.append(f"Fetched {collection} scene {scene_id}.")
    else:
        parts.append(f"{tool_name} completed successfully.")

    cloud = quality.get("cloud_cover")
    if cloud is not None:
        parts.append(f"Cloud cover {cloud}%.")

    path = data.get("file_path")
    fmt = data.get("format", "file")
    if path:
        parts.append(f"{fmt} saved at {path}.")

    return {
        "status": "success",
        "final_answer": " ".join(parts),
    }
