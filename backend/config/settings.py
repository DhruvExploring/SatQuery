"""Runtime configuration for SatQuery.

Provider selection is controlled by SATQUERY_USE_OPENAI / SATQUERY_USE_CLAUDE.
Exactly one real provider must be enabled when SATQUERY_MOCK_PLANNER=false.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load the project-root .env when this module is imported.
_env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(_env_path)


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    default_start_date: str = "2025-01-01"
    default_end_date: str = "2025-01-31"
    default_max_cloud_cover: float = 30.0
    default_width: int = 512
    default_height: int = 512
    default_crs: str = "EPSG:4326"

    use_mock_planner: bool = True
    use_mock_tools: bool = True

    tool_output_dir: str = "sih_satellite_data"

    memory_backend: str = "none"
    memory_db_url: str | None = None
    memory_embed_model: str = "openai:text-embedding-3-small"

    # LLM provider toggle — preserve Shrishti's existing architecture.
    use_openai: bool = False
    use_claude: bool = False

    # LLM models
    openai_model: str = "gpt-5.6"
    claude_model: str = "claude-sonnet-4-6"
    openai_base_url: str | None = None

    # API keys
    openai_api_key: str | None = None
    claude_api_key: str | None = None


def load_settings() -> Settings:
    use_mock_planner = _as_bool(
        os.getenv("SATQUERY_MOCK_PLANNER"), True
    )

    use_openai = _as_bool(
        os.getenv("SATQUERY_USE_OPENAI"), False
    )

    use_claude = _as_bool(
        os.getenv("SATQUERY_USE_CLAUDE"), False
    )

    # Older .env files used SATQUERY_LLM_PROVIDER instead of USE_OPENAI / USE_CLAUDE.
    provider = (os.getenv("SATQUERY_LLM_PROVIDER") or "").strip().lower()
    if not use_openai and not use_claude:
        if provider in {"openai", "groq"}:
            use_openai = True
        elif provider in {"claude", "anthropic"}:
            use_claude = True

    if not use_mock_planner and use_openai == use_claude:
        raise ValueError(
            "Exactly one LLM must be enabled. "
            "Set SATQUERY_USE_OPENAI=true OR "
            "SATQUERY_USE_CLAUDE=true, but not both. "
            "Or set SATQUERY_MOCK_PLANNER=true for the keyword planner."
        )

    return Settings(
        use_mock_planner=use_mock_planner,
        use_mock_tools=_as_bool(
            os.getenv("SATQUERY_MOCK_TOOLS"), True
        ),
        use_openai=use_openai,
        use_claude=use_claude,
        openai_model=os.getenv("SATQUERY_OPENAI_MODEL")
        or os.getenv("SATQUERY_LLM_MODEL")
        or "gpt-5.6",
        claude_model=os.getenv(
            "SATQUERY_CLAUDE_MODEL", "claude-sonnet-4-6"
        ),
        openai_base_url=os.getenv("SATQUERY_LLM_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or None,
        openai_api_key=(
            os.getenv("OPENAI_API_KEY")
            or os.getenv("SATQUERY_LLM_API_KEY")
            or None
        ),
        claude_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        memory_backend=os.getenv(
            "SATQUERY_MEMORY_BACKEND", "none"
        ),
        memory_db_url=os.getenv(
            "SATQUERY_MEMORY_DB_URL"
        ) or None,
        memory_embed_model=os.getenv(
            "SATQUERY_MEMORY_EMBED_MODEL",
            "openai:text-embedding-3-small",
        ),
    )


settings = load_settings()
