from backend.orchestrator.llm import _llm_plan, resolve_llm_tool
from backend.orchestrator.registry import reconcile_sar_args
from backend.orchestrator.state import empty_state


def _fake_client(tool: str, reason: str = "ok"):
    class _FakeClient:
        def invoke(self, _messages):
            return {
                "action": "call_tool",
                "tool": tool,
                "args": {},
                "reason": reason,
            }

    return _FakeClient()


def test_resolve_llm_tool_maps_aliases_and_rejects_invented_names():
    assert resolve_llm_tool("fetch_multispectral_imagery") == "fetch_multispectral_imagery"
    assert resolve_llm_tool("fetch_sar") == "fetch_sar_imagery"
    assert resolve_llm_tool("fetch_satellite_imagery") == "fetch_optical_imagery"
    assert resolve_llm_tool("Sentinelimagery") is None
    assert resolve_llm_tool("SentinelHub_Search") is None


def test_llm_plan_falls_back_when_model_invents_sentinelimagery(monkeypatch):
    monkeypatch.setattr(
        "backend.orchestrator.llm._build_llm_client",
        lambda: _fake_client("Sentinelimagery"),
    )
    plan = _llm_plan(
        empty_state(
            query="Fetch Sentinel-2 multispectral imagery for Delhi for vegetation analysis",
            bbox=[77.1, 28.5, 77.3, 28.7],
            start_date="2025-01-01",
            end_date="2025-01-31",
        )
    )
    assert plan["action"] == "call_tool"
    assert plan["tool"] == "fetch_multispectral_imagery"
    assert "keyword fallback" in plan["reason"]


def test_llm_plan_falls_back_when_model_invents_sentinelhub_search(monkeypatch):
    monkeypatch.setattr(
        "backend.orchestrator.llm._build_llm_client",
        lambda: _fake_client("SentinelHub_Search"),
    )
    plan = _llm_plan(
        empty_state(
            query="Fetch SAR radar Sentinel-1 imagery for Delhi",
            bbox=[77.1, 28.5, 77.3, 28.7],
            start_date="2025-01-01",
            end_date="2025-01-31",
        )
    )
    assert plan["action"] == "call_tool"
    assert plan["tool"] == "fetch_sar_imagery"
    assert "keyword fallback" in plan["reason"]


def test_llm_plan_maps_fetch_sar_alias(monkeypatch):
    monkeypatch.setattr(
        "backend.orchestrator.llm._build_llm_client",
        lambda: _fake_client("fetch_sar", "SAR skill name"),
    )
    plan = _llm_plan(
        empty_state(
            query="Fetch SAR radar Sentinel-1 imagery for Delhi",
            bbox=[77.1, 28.5, 77.3, 28.7],
            start_date="2025-01-01",
            end_date="2025-01-31",
        )
    )
    assert plan["action"] == "call_tool"
    assert plan["tool"] == "fetch_sar_imagery"
    assert plan["reason"] == "SAR skill name"


def test_llm_plan_unknown_tool_without_keywords_becomes_chat(monkeypatch):
    monkeypatch.setattr(
        "backend.orchestrator.llm._build_llm_client",
        lambda: _fake_client("SentinelHub_Search"),
    )
    plan = _llm_plan(empty_state(query="hello, what can you do?"))
    assert plan["action"] == "chat"
    assert plan["tool"] is None


def test_llm_plan_discards_hallucinated_bbox(monkeypatch):
    delhi = [77.10, 28.50, 77.30, 28.70]

    class _FakeClient:
        def invoke(self, _messages):
            return {
                "action": "call_tool",
                "tool": "fetch_optical_imagery",
                "args": {
                    "bbox": [0.0, 0.0, 1.0, 1.0],
                    "start_date": "1999-01-01",
                },
                "reason": "optical",
            }

    monkeypatch.setattr(
        "backend.orchestrator.llm._build_llm_client",
        lambda: _FakeClient(),
    )
    plan = _llm_plan(
        empty_state(
            query="Fetch Sentinel-2 optical imagery for Delhi.",
            bbox=delhi,
            start_date="2025-01-01",
        )
    )
    assert plan["action"] == "call_tool"
    assert plan["args"]["bbox"] == delhi
    assert plan["args"]["start_date"] == "2025-01-01"


def test_llm_plan_clarifies_when_model_calls_tool_without_location(monkeypatch):
    class _FakeClient:
        def invoke(self, _messages):
            return {
                "action": "call_tool",
                "tool": "fetch_optical_imagery",
                "args": {},
                "reason": "Looks like an optical fetch.",
            }

    monkeypatch.setattr(
        "backend.orchestrator.llm._build_llm_client",
        lambda: _FakeClient(),
    )
    plan = _llm_plan(empty_state(query="Fetch Sentinel-2 optical imagery for Delhi."))
    assert plan["action"] == "clarify"
    assert plan["tool"] is None


def test_llm_sar_plan_does_not_keep_hallucinated_ascending(monkeypatch):
    class _FakeClient:
        def invoke(self, _messages):
            return {
                "action": "call_tool",
                "tool": "fetch_sar_imagery",
                "args": {
                    "bbox": [72.8, 18.9, 73.0, 19.1],
                    "orbit_direction": "ASCENDING",
                    "polarization": ["VV"],
                },
                "reason": "SAR request.",
            }

    monkeypatch.setattr(
        "backend.orchestrator.llm._build_llm_client",
        lambda: _FakeClient(),
    )
    plan = _llm_plan(
        empty_state(
            query="Get SAR radar imagery for Mumbai",
            bbox=[72.8, 18.9, 73.0, 19.1],
        )
    )
    assert plan["action"] == "call_tool"
    assert plan["args"]["orbit_direction"] == "BOTH"
    assert plan["args"]["polarization"] == ["VV", "VH"]


def test_reconcile_sar_args_honors_explicit_ascending_in_query():
    args = reconcile_sar_args(
        {"orbit_direction": "BOTH"},
        empty_state(query="Fetch ascending Sentinel-1 SAR for Mumbai"),
    )
    assert args["orbit_direction"] == "ASCENDING"


def test_reconcile_sar_args_http_orbit_wins_over_query_and_llm():
    args = reconcile_sar_args(
        {"orbit_direction": "BOTH", "polarization": ["VV", "VH"]},
        empty_state(
            query="Fetch descending Sentinel-1 SAR for Mumbai",
            orbit_direction="ASCENDING",
        ),
    )
    assert args["orbit_direction"] == "ASCENDING"


def test_reconcile_sar_args_query_descending_when_no_http_field():
    args = reconcile_sar_args(
        {"orbit_direction": "BOTH"},
        empty_state(query="Fetch descending Sentinel-1 SAR for Mumbai"),
    )
    assert args["orbit_direction"] == "DESCENDING"


def test_reconcile_sar_args_defaults_to_both_over_llm_guess():
    args = reconcile_sar_args(
        {"orbit_direction": "ASCENDING"},
        empty_state(query="Get SAR radar imagery for Mumbai"),
    )
    assert args["orbit_direction"] == "BOTH"


def test_reconcile_sar_args_http_polarization_wins_over_llm():
    args = reconcile_sar_args(
        {"orbit_direction": "BOTH", "polarization": ["VV", "VH"]},
        empty_state(
            query="Get SAR radar imagery for Mumbai",
            polarization=["VV"],
        ),
    )
    assert args["polarization"] == ["VV"]


def test_reconcile_sar_args_keeps_llm_polarization_without_http_field():
    args = reconcile_sar_args(
        {"orbit_direction": "BOTH", "polarization": ["VV", "VH"]},
        empty_state(query="Get SAR radar imagery for Mumbai"),
    )
    assert args["polarization"] == ["VV", "VH"]
