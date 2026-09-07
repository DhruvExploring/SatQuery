"""Invoke the LangGraph orchestrator from the command line (no HTTP).

Run from the SatQuery root:
    python -m backend.demo
"""

from __future__ import annotations

import json

from backend.orchestrator.graph import invoke_satquery
from backend.orchestrator.state import empty_state


def run_demo() -> None:
    state = empty_state(
        query="Fetch Sentinel-2 imagery for Delhi.",
        bbox=[77.10, 28.50, 77.30, 28.70],
        start_date="2025-01-01",
        end_date="2025-01-31",
    )
    result = invoke_satquery(state)
    print(json.dumps(
        {
            "status": result.get("status"),
            "plan": result.get("plan"),
            "tool_results": result.get("tool_results"),
            "final_answer": result.get("final_answer"),
        },
        indent=2,
    ))


if __name__ == "__main__":
    run_demo()
