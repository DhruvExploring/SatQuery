from backend.orchestrator.router import route_after_advance, route_after_plan


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


def test_route_after_advance_continues_when_agenda_remains():
    next_node = route_after_advance(
        {
            "query": "ndvi",
            "plan": {
                "action": "call_tool",
                "tool": "fetch_multispectral_imagery",
                "args": {},
                "reason": "test",
            },
            "agenda": [
                {"tool": "fetch_multispectral_imagery"},
                {"tool": "compute_vegetation_indices"},
            ],
            "agenda_index": 1,
            "handshake_complete": False,
            "tool_results": [],
            "errors": [],
        }
    )
    assert next_node == "continue"


def test_route_after_advance_responds_when_complete():
    next_node = route_after_advance(
        {
            "query": "ndvi",
            "plan": {
                "action": "call_tool",
                "tool": "compute_vegetation_indices",
                "args": {},
                "reason": "test",
            },
            "agenda": [{"tool": "compute_vegetation_indices"}],
            "agenda_index": 1,
            "handshake_complete": True,
            "tool_results": [],
            "errors": [],
        }
    )
    assert next_node == "respond"
