from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "t", "yes", "y")


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

    # LLM selection
    use_openai: bool = False
    use_claude: bool = False

    # LLM models
    openai_model: str = "gpt-5.6"
    claude_model: str = "claude-sonnet-4-6"

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

    # When using the real planner, exactly one LLM must be enabled.
    if not use_mock_planner and use_openai == use_claude:
        raise ValueError(
            "Exactly one LLM must be enabled. "
            "Set SATQUERY_USE_OPENAI=true OR "
            "SATQUERY_USE_CLAUDE=true, but not both."
        )

    return Settings(
        use_mock_planner=use_mock_planner,

        use_mock_tools=_as_bool(
            os.getenv("SATQUERY_MOCK_TOOLS"), True
        ),

        use_openai=use_openai,
        use_claude=use_claude,

        openai_model=os.getenv(
            "SATQUERY_OPENAI_MODEL",
            "gpt-5.6",
        ),

        claude_model=os.getenv(
            "SATQUERY_CLAUDE_MODEL",
            "claude-sonnet-4-6",
        ),

        openai_api_key=os.getenv(
            "OPENAI_API_KEY"
        ) or None,

        claude_api_key=os.getenv(
            "ANTHROPIC_API_KEY"
        ) or None,

        memory_backend=os.getenv(
            "SATQUERY_MEMORY_BACKEND",
            "none",
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