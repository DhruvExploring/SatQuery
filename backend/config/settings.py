"""Runtime flags for the orchestrator.

Tools always run for real. Planner can still be keyword (tests) or LLM (Groq).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(_env_path)


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    default_start_date: str = "2025-01-01"
    default_end_date: str = "2025-01-31"
    default_max_cloud_cover: float = 30.0
    default_width: int = 512
    default_height: int = 512
    default_crs: str = "EPSG:4326"
    use_mock_planner: bool = True

    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str | None = None
    llm_api_key: str | None = None


def load_settings() -> Settings:
    return Settings(
        use_mock_planner=_as_bool(os.getenv("SATQUERY_MOCK_PLANNER"), True),
        llm_provider=os.getenv("SATQUERY_LLM_PROVIDER", "openai"),
        llm_model=os.getenv("SATQUERY_LLM_MODEL", "gpt-4o-mini"),
        llm_base_url=os.getenv("SATQUERY_LLM_BASE_URL") or None,
        llm_api_key=os.getenv("SATQUERY_LLM_API_KEY") or None,
    )


settings = load_settings()
