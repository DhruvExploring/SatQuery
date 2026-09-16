from backend.orchestrator.router import route_after_load_kb, route_after_validate
from backend.orchestrator.tool_loop_graph import route_after_llm


def test_route_after_validate_continues_without_errors():
    assert route_after_validate({"errors": []}) == "continue"


def test_route_after_validate_errors_short_circuits():
    assert route_after_validate({"errors": ["query must not be empty."]}) == "error"


def test_route_after_load_kb_describes_when_kb_present():
    assert route_after_load_kb({"knowledge_base": {"bands": ["B04"]}}) == "describe"


def test_route_after_load_kb_skips_without_kb():
    assert route_after_load_kb({"knowledge_base": None}) == "skip"


def test_route_after_llm_goes_to_tool_on_call_tool():
    next_node = route_after_llm(
        {"plan": {"action": "call_tool", "tool": "fetch_optical_imagery", "args": {}, "reason": "test"}}
    )
    assert next_node == "tool"


def test_route_after_llm_ends_on_clarify():
    next_node = route_after_llm(
        {"plan": {"action": "clarify", "tool": None, "args": {}, "reason": "no bbox"}}
    )
    assert next_node == "end"
