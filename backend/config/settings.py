"""Runtime configuration for SatQuery.

Two independent, swappable model roles:

- Orchestrator (SATQUERY_ORCHESTRATOR_*): picks which tool to call next and,
  when enabled, writes the final narrative answer. mock | openai | anthropic.
- Vision tool (SATQUERY_VISION_TOOL_*): interprets a rendered image on request,
  called like any other tool. openai (hosted vision API) | local (talks to
  local_model_server, which may be serving InternVL-1B or EarthMind-4B).

Neither role auto-fails-over between local and API at runtime — the mode is a
static deployment choice. See .env.example for the full var list.
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


def _as_origin_list(value: str | None) -> list[str]:
    if value is None or not value.strip():
        return ["*"]
    return [origin.strip() for origin in value.split(",") if origin.strip()]


@dataclass(frozen=True)
class Settings:
    default_start_date: str = "2025-01-01"
    default_end_date: str = "2025-01-31"
    default_max_cloud_cover: float = 30.0
    default_width: int = 512
    default_height: int = 512
    default_crs: str = "EPSG:4326"

    tool_output_dir: str = "sih_satellite_data"

    memory_backend: str = "none"
    memory_db_url: str | None = None
    memory_embed_model: str = "openai:text-embedding-3-small"

    # --- Orchestrator role ---
    orchestrator_provider: str = "mock"  # mock | openai | anthropic
    orchestrator_model: str = "gpt-5.2"
    orchestrator_api_key: str | None = None
    orchestrator_base_url: str | None = None
    orchestrator_synthesize_answer: bool = True

    # --- Vision tool role ---
    vision_tool_enabled: bool = False
    vision_tool_provider: str = "openai"  # openai | local
    vision_tool_model: str = "gpt-4o-mini"
    vision_tool_api_key: str | None = None
    vision_tool_base_url: str | None = None
    vision_tool_timeout_s: float = 60.0

    # --- Networking / deployment ---
    cors_allowed_origins: tuple[str, ...] = ("*",)
    backend_port: int = 8000


def load_settings() -> Settings:
    orchestrator_provider = (
        os.getenv("SATQUERY_ORCHESTRATOR_PROVIDER") or "mock"
    ).strip().lower()
    if orchestrator_provider not in {"mock", "openai", "anthropic"}:
        raise ValueError(
            "SATQUERY_ORCHESTRATOR_PROVIDER must be one of: mock, openai, anthropic. "
            f"Got {orchestrator_provider!r}."
        )

    vision_tool_enabled = _as_bool(os.getenv("SATQUERY_VISION_TOOL_ENABLED"), False)
    vision_tool_provider = (
        os.getenv("SATQUERY_VISION_TOOL_PROVIDER") or "openai"
    ).strip().lower()
    if vision_tool_enabled and vision_tool_provider not in {"openai", "local"}:
        raise ValueError(
            "SATQUERY_VISION_TOOL_PROVIDER must be one of: openai, local. "
            f"Got {vision_tool_provider!r}."
        )

    orchestrator_api_key = os.getenv("SATQUERY_ORCHESTRATOR_API_KEY") or None
    if orchestrator_api_key is None:
        if orchestrator_provider == "openai":
            orchestrator_api_key = os.getenv("OPENAI_API_KEY") or None
        elif orchestrator_provider == "anthropic":
            orchestrator_api_key = os.getenv("ANTHROPIC_API_KEY") or None

    vision_tool_api_key = os.getenv("SATQUERY_VISION_TOOL_API_KEY") or None
    if vision_tool_api_key is None and vision_tool_provider == "openai":
        vision_tool_api_key = os.getenv("OPENAI_API_KEY") or None

    return Settings(
        orchestrator_provider=orchestrator_provider,
        orchestrator_model=os.getenv("SATQUERY_ORCHESTRATOR_MODEL", "gpt-5.2"),
        orchestrator_api_key=orchestrator_api_key,
        orchestrator_base_url=os.getenv("SATQUERY_ORCHESTRATOR_BASE_URL") or None,
        orchestrator_synthesize_answer=_as_bool(
            os.getenv("SATQUERY_ORCHESTRATOR_SYNTHESIZE_ANSWER"), True
        ),
        vision_tool_enabled=vision_tool_enabled,
        vision_tool_provider=vision_tool_provider,
        vision_tool_model=os.getenv("SATQUERY_VISION_TOOL_MODEL", "gpt-4o-mini"),
        vision_tool_api_key=vision_tool_api_key,
        vision_tool_base_url=os.getenv("SATQUERY_VISION_TOOL_BASE_URL") or None,
        vision_tool_timeout_s=float(
            os.getenv("SATQUERY_VISION_TOOL_TIMEOUT_S", "60")
        ),
        cors_allowed_origins=tuple(
            _as_origin_list(os.getenv("SATQUERY_CORS_ALLOWED_ORIGINS"))
        ),
        backend_port=int(os.getenv("SATQUERY_BACKEND_PORT", "8000")),
        tool_output_dir=os.getenv("SATQUERY_TOOL_OUTPUT_DIR", "sih_satellite_data"),
        memory_backend=os.getenv("SATQUERY_MEMORY_BACKEND", "none"),
        memory_db_url=os.getenv("SATQUERY_MEMORY_DB_URL") or None,
        memory_embed_model=os.getenv(
            "SATQUERY_MEMORY_EMBED_MODEL",
            "openai:text-embedding-3-small",
        ),
    )


settings = load_settings()
