"""Map graph outcome → HTTP status for POST /api/v1/query.

The JSON body still carries the semantic `status` field
(success | ok | clarify | error). This module only chooses the HTTP code.
"""

from __future__ import annotations

from typing import Any

# Graph status → HTTP
#   success / ok  → 200  request handled
#   clarify       → 400  missing required location
#   error (input) → 400  invalid bbox / planner rejected the request
#   error (tool)  → 400  tool validation (bad args)
#                  → 404  catalog/API answered; no scene or weather matched filters
#                  → 502  Sentinel Hub / Open-Meteo / upstream failed
#                  → 500  import / unknown tool / unexpected empty output
#   anything else → 500


def http_status_for_query(result: dict[str, Any]) -> int:
    status = (result.get("status") or "error").lower()

    if status in {"success", "ok"}:
        return 200
    if status == "clarify":
        return 400
    if status == "error":
        return _error_http_status(result)
    return 500


def _error_http_status(result: dict[str, Any]) -> int:
    tool_results = result.get("tool_results") or []
    if tool_results:
        latest = tool_results[-1].get("result") or {}
        if latest.get("status") == "success":
            return 500
        err_type = (latest.get("error") or {}).get("type")
        if err_type == "validation_error":
            return 400
        if err_type in {"no_suitable_scene", "no_data"}:
            return 404
        if err_type in {"import_error", "unknown_tool"}:
            return 500
        return 502

    errors = result.get("errors") or []
    if errors:
        return 400

    planned = result.get("plan") or {}
    if planned.get("action") == "respond_error":
        return 400

    return 500
