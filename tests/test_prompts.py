"""The planner's system prompt is one editable file (prompts/planner_system.md)
used whether or not SkillKit is active, with the continuation note plugged in
only on a continuation hop. Also locks in that trace_entry() logs every step
(backend/orchestrator/README.md's "Every graph step" guarantee)."""
from __future__ import annotations

import logging

from backend.orchestrator.llm import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_WITH_CONTINUATION,
    _CONTINUATION_NOTE,
)
from backend.orchestrator.prompts import load_prompt
from backend.orchestrator.state import trace_entry


def test_system_prompt_has_no_leftover_placeholders():
    assert "{{" not in SYSTEM_PROMPT
    assert "{{" not in SYSTEM_PROMPT_WITH_CONTINUATION


def test_system_prompt_mentions_skillkit_usage_and_all_tools():
    assert "Skill/SkillRead" in SYSTEM_PROMPT
    assert "describe_marked_region" in SYSTEM_PROMPT
    assert "fetch_web_intelligence" in SYSTEM_PROMPT


def test_continuation_note_only_present_in_the_continuation_variant():
    assert "already gathered" not in SYSTEM_PROMPT
    assert "already gathered" in SYSTEM_PROMPT_WITH_CONTINUATION
    # Everything else is identical -- only the continuation note is inserted.
    assert SYSTEM_PROMPT_WITH_CONTINUATION.replace(_CONTINUATION_NOTE, "", 1) == SYSTEM_PROMPT


def test_planner_and_synthesis_prompts_prioritize_geocoded_place_name():
    # A vision model can hallucinate a specific place name from visual
    # similarity even while correctly describing scene content -- both
    # prompts must tell the model to trust a verified place_name field
    # (reverse geocoding) over that guess. See the "Vasant Vihar" vs.
    # "India Gate" mismatch this was written to catch: describe_marked_region
    # correctly reverse-geocoded a region's center, but the synthesized
    # answer repeated the vision model's own wrong guess instead.
    assert "place_name" in SYSTEM_PROMPT
    assert "authoritative" in SYSTEM_PROMPT

    synthesis_prompt = load_prompt("synthesis_system")
    assert "place_name" in synthesis_prompt
    assert "authoritative" in synthesis_prompt


def test_trace_entry_logs_every_step_to_console(caplog):
    with caplog.at_level(logging.INFO, logger="satquery.graph"):
        entry = trace_entry("some_node", "some summary")
    assert entry == {
        "node": "some_node",
        "timestamp": entry["timestamp"],
        "summary": "some summary",
    }
    assert any(
        "[STEP] some_node: some summary" in record.message
        for record in caplog.records
    )
