"""Tool 10 (spatial_geocoding_poi) must never parse the user's raw natural-
language query itself -- that's the LLM planner's job (see
backend/orchestrator/llm.py::_PLAN_SCHEMA's place_name/landmark_names fields
and registry.py::trusted_args_for_tool). This file protects three things:

1. forward_geocode() trusts its `query` argument as an already-clean name --
   no regex cleaning, and (the bug that motivated this) no crash when both
   providers return zero results.
2. resolve_scene_identity() resolves exactly the `landmark_names` it's given,
   never re-deriving them from `query` itself.
3. _is_valid_landmark_candidate() filters purely on the geocoder's own
   structured result metadata (class/type/importance), never on keyword-
   matching the query text.
"""
from __future__ import annotations

from Tool_10_spatial_geocoding_poi.spatial_geocoding_poi import (
    _is_valid_landmark_candidate,
    forward_geocode,
    resolve_scene_identity,
)

DELHI = [77.10, 28.50, 77.30, 28.70]


def test_forward_geocode_treats_query_as_already_clean(monkeypatch):
    """No _clean_entity_string-style rewriting -- whatever string is passed
    is sent to the geocoder verbatim (aside from whitespace trimming)."""
    import Tool_10_spatial_geocoding_poi.spatial_geocoding_poi as tool10

    captured = {}

    class _FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return []

    def _fake_get(url, params=None, **kwargs):
        captured["q"] = params.get("q")
        return _FakeResponse()

    monkeypatch.setattr(tool10.os, "getenv", lambda *a, **k: "")  # no LocationIQ key -> Nominatim only
    monkeypatch.setattr(tool10.requests, "get", _fake_get)
    monkeypatch.setattr(tool10, "_rate_limit_nominatim", lambda: None)

    forward_geocode(query="  Yamuna River  ")
    assert captured["q"] == "Yamuna River"


def test_forward_geocode_fails_cleanly_instead_of_crashing_on_zero_results(monkeypatch):
    """The bug this file exists to prevent: forward_geocode used to crash
    with NameError (_trim_query_for_fallback was called but never defined)
    whenever both providers returned zero matches."""
    import Tool_10_spatial_geocoding_poi.spatial_geocoding_poi as tool10

    class _FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return []

    monkeypatch.setattr(tool10.os, "getenv", lambda *a, **k: "")
    monkeypatch.setattr(tool10.requests, "get", lambda *a, **k: _FakeResponse())
    monkeypatch.setattr(tool10, "_rate_limit_nominatim", lambda: None)

    result = forward_geocode(query="a name that resolves to nothing")
    assert result["status"] == "error"
    assert "No geocoding matches found" in result["message"]


def test_resolve_scene_identity_resolves_exactly_the_given_landmark_names(monkeypatch):
    """A confusing/irrelevant `query` must never influence which landmark(s)
    get geocoded -- only landmark_names does."""
    import Tool_10_spatial_geocoding_poi.spatial_geocoding_poi as tool10

    monkeypatch.setattr(
        tool10, "reverse_geocode",
        lambda lat, lon, zoom=None: {"status": "success", "address": {}, "display_name": ""},
    )

    calls: list[str] = []

    def _fake_forward_geocode(name, bbox=None, viewbox_clamping=True):
        calls.append(name)
        return {"status": "success", "candidates": [], "best_match": None}

    monkeypatch.setattr(tool10, "forward_geocode", _fake_forward_geocode)

    resolve_scene_identity(
        bbox=DELHI,
        query="this sentence mentions Qutub Minar and Lotus Temple but should be ignored",
        landmark_names=["Red Fort"],
    )
    # Two-tier strategy: global unbounded search, then (since the stub never
    # returns a canonical match) a local bounded retry -- both for the same
    # name, never anything derived from `query`.
    assert calls == ["Red Fort", "Red Fort"]
    assert set(calls) == {"Red Fort"}


def test_resolve_scene_identity_with_no_landmark_names_resolves_none(monkeypatch):
    import Tool_10_spatial_geocoding_poi.spatial_geocoding_poi as tool10

    monkeypatch.setattr(
        tool10, "reverse_geocode",
        lambda lat, lon, zoom=None: {"status": "success", "address": {}, "display_name": ""},
    )
    calls: list[str] = []
    monkeypatch.setattr(
        tool10, "forward_geocode",
        lambda name, bbox=None, viewbox_clamping=True: calls.append(name) or {"status": "error"},
    )

    result = resolve_scene_identity(bbox=DELHI, query="what region is this scene")
    assert calls == []
    assert result["landmarks"] == []


def test_is_valid_landmark_candidate_filters_on_structured_metadata_only():
    """No query_entity/keyword-matching parameter any more -- purely
    class/type/importance from the geocoder's own result."""
    low_importance_shop = {"class": "shop", "type": "convenience", "importance": 0.1}
    assert _is_valid_landmark_candidate(low_importance_shop) is False

    high_importance_amenity = {"class": "amenity", "type": "hotel", "importance": 0.6}
    assert _is_valid_landmark_candidate(high_importance_amenity) is True

    heritage_type = {"class": "amenity", "type": "fort", "importance": 0.05}
    assert _is_valid_landmark_candidate(heritage_type) is True

    non_noise_class = {"class": "historic", "type": "monument", "importance": 0.02}
    assert _is_valid_landmark_candidate(non_noise_class) is True
