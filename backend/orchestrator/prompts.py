"""Loader for the orchestrator's editable prompt text.

Prompt wording lives in plain markdown files under backend/orchestrator/prompts/
instead of inline Python strings, so it can be edited without touching
planner/synthesis code. Placeholders use {{UPPER_SNAKE}} tokens and are
substituted with plain string replacement (not str.format), so the prompt
text itself can contain literal braces (e.g. "Set args to {}.") without
needing to escape them.
"""
from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str, **placeholders: str) -> str:
    text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()
    for key, value in placeholders.items():
        text = text.replace("{{" + key + "}}", value)
    return text
