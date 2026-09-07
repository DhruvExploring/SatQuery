from backend.orchestrator.router import route_after_plan


def test_route_call_tool_goes_to_execute():
    next_node = route_after_plan(
        {
            "query": "fetch",
            "plan": {
                "action": "call_tool",
                "tool": "fetch_optical_imagery",
                "args": {},
                "reason": "test",
            },
            "tool_results": [],
            "errors": [],
        }
    )
    assert next_node == "execute"


def test_route_clarify_goes_to_respond():
    next_node = route_after_plan(
        {
            "query": "fetch",
            "plan": {
                "action": "clarify",
                "tool": None,
                "args": {},
                "reason": "no bbox",
            },
            "tool_results": [],
            "errors": [],
        }
    )
    assert next_node == "respond"
