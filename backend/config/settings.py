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

# Sanitize PROJ environment so rasterio/GDAL/pyproj uses its own bundled PROJ database
# rather than an incompatible system version (e.g. from PostgreSQL/PostGIS).
try:
    import rasterio
    _rproj = Path(rasterio.__file__).parent / "proj_data"
    if (_rproj / "proj.db").is_file():
        os.environ["PROJ_LIB"] = str(_rproj)
        os.environ["PROJ_DATA"] = str(_rproj)
except Exception:
    pass


def _clean_str(value: str | None) -> str | None:
    if value is None:
        return None
    val = value.strip().strip("'\"").strip()
    return val if val else None


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    cleaned = value.strip().strip("'\"").strip().lower()
    return cleaned in {"1", "true", "t", "yes", "y", "on"}


def _as_origin_list(value: str | None) -> list[str]:
    cleaned = _clean_str(value)
    if cleaned is None:
        return ["*"]
    return [origin.strip().strip("'\"") for origin in cleaned.split(",") if origin.strip()]


SUPPORTED_CLAUDE_MODELS: tuple[str, ...] = (
    "claude-sonnet-5",
    "claude-haiku-4-5",
    "claude-opus-5-5",
)

CLAUDE_MODEL_ALIASES: dict[str, str] = {
    # Claude Sonnet 5
    "claude-sonnet-5": "claude-sonnet-5",
    "claude-5-sonnet": "claude-sonnet-5",
    "claude-sonnet-5.0": "claude-sonnet-5",
    "sonnet-5": "claude-sonnet-5",
    "claude-sonnet": "claude-sonnet-5",
    # Claude 4.5 Haiku
    "claude-haiku-4-5": "claude-haiku-4-5",
    "claude-haiku-4-5-20251001": "claude-haiku-4-5",
    "claude-4-5-haiku": "claude-haiku-4-5",
    "claude-haiku-4.5": "claude-haiku-4-5",
    "haiku-4-5": "claude-haiku-4-5",
    "haiku-4.5": "claude-haiku-4-5",
    # Claude Opus 5.5
    "claude-opus-5-5": "claude-opus-5-5",
    "claude-opus-5.5": "claude-opus-5-5",
    "claude-5-5-opus": "claude-opus-5-5",
    "claude-5.5-opus": "claude-opus-5-5",
    "claude-opus-5": "claude-opus-5-5",
    "opus-5-5": "claude-opus-5-5",
    "opus-5.5": "claude-opus-5-5",
    "opus-5": "claude-opus-5-5",
}


def normalize_claude_model(raw_model: str | None) -> str:
    """Normalize model string to one of the 3 supported Claude models, or raise ValueError."""
    if not raw_model:
        return "claude-sonnet-5"
    token = raw_model.strip().lower()
    if token in CLAUDE_MODEL_ALIASES:
        return CLAUDE_MODEL_ALIASES[token]
    if "haiku" in token and ("4-5" in token or "4.5" in token):
        return "claude-haiku-4-5"
    if "opus" in token and ("5-5" in token or "5.5" in token or "5" in token):
        return "claude-opus-5-5"
    if "sonnet" in token and "5" in token:
        return "claude-sonnet-5"
    if token in SUPPORTED_CLAUDE_MODELS:
        return token
    raise ValueError(
        f"Model {raw_model!r} is not allowed. SatQuery only runs on Claude Sonnet 5 "
        f"('claude-sonnet-5'), 4.5 Haiku ('claude-haiku-4-5'), and Opus 5.5 ('claude-opus-5-5')."
    )


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
    orchestrator_provider: str = "anthropic"  # mock (tests only) | anthropic
    orchestrator_model: str = "claude-sonnet-5"
    orchestrator_api_key: str | None = None
    orchestrator_base_url: str | None = None
    orchestrator_synthesize_answer: bool = True

    # --- Vision tool role ---
    vision_tool_enabled: bool = False
    vision_tool_provider: str = "anthropic"  # anthropic | local
    vision_tool_model: str = "claude-sonnet-5"
    vision_tool_api_key: str | None = None
    vision_tool_base_url: str | None = None
    vision_tool_timeout_s: float = 60.0

    # --- Networking / deployment ---
    cors_allowed_origins: tuple[str, ...] = ("*",)
    backend_port: int = 8000


def load_settings() -> Settings:
    orchestrator_provider = (
        _clean_str(os.getenv("SATQUERY_ORCHESTRATOR_PROVIDER")) or "anthropic"
    ).lower()
    if orchestrator_provider == "openai":
        raise ValueError(
            "SATQUERY_ORCHESTRATOR_PROVIDER cannot be 'openai'. "
            "SatQuery is restricted to Claude Sonnet 5, 4.5 Haiku, and Opus 5.5 (provider: anthropic)."
        )
    if orchestrator_provider not in {"mock", "anthropic"}:
        raise ValueError(
            "SATQUERY_ORCHESTRATOR_PROVIDER must be 'anthropic' (or 'mock' for tests). "
            f"Got {orchestrator_provider!r}."
        )

    raw_orch_model = _clean_str(os.getenv("SATQUERY_ORCHESTRATOR_MODEL")) or "claude-sonnet-5"
    orchestrator_model = normalize_claude_model(raw_orch_model)

    vision_tool_enabled = _as_bool(os.getenv("SATQUERY_VISION_TOOL_ENABLED"), False)
    vision_tool_provider = (
        _clean_str(os.getenv("SATQUERY_VISION_TOOL_PROVIDER")) or "anthropic"
    ).lower()
    if vision_tool_enabled and vision_tool_provider == "openai":
        raise ValueError(
            "SATQUERY_VISION_TOOL_PROVIDER cannot be 'openai'. "
            "SatQuery is restricted to Claude Sonnet 5, 4.5 Haiku, and Opus 5.5 (provider: anthropic)."
        )
    if vision_tool_enabled and vision_tool_provider not in {"anthropic", "local"}:
        raise ValueError(
            "SATQUERY_VISION_TOOL_PROVIDER must be 'anthropic' or 'local'. "
            f"Got {vision_tool_provider!r}."
        )

    raw_vision_model = _clean_str(os.getenv("SATQUERY_VISION_TOOL_MODEL")) or "claude-sonnet-5"
    if vision_tool_provider == "anthropic":
        vision_tool_model = normalize_claude_model(raw_vision_model)
    else:
        vision_tool_model = raw_vision_model

    orchestrator_api_key = _clean_str(os.getenv("SATQUERY_ORCHESTRATOR_API_KEY"))
    if orchestrator_api_key is None and orchestrator_provider == "anthropic":
        orchestrator_api_key = _clean_str(os.getenv("ANTHROPIC_API_KEY"))

    vision_tool_api_key = _clean_str(os.getenv("SATQUERY_VISION_TOOL_API_KEY"))
    if vision_tool_api_key is None and vision_tool_provider == "anthropic":
        vision_tool_api_key = _clean_str(os.getenv("ANTHROPIC_API_KEY")) or orchestrator_api_key

    return Settings(
        orchestrator_provider=orchestrator_provider,
        orchestrator_model=orchestrator_model,
        orchestrator_api_key=orchestrator_api_key,
        orchestrator_base_url=_clean_str(os.getenv("SATQUERY_ORCHESTRATOR_BASE_URL")),
        orchestrator_synthesize_answer=_as_bool(
            os.getenv("SATQUERY_ORCHESTRATOR_SYNTHESIZE_ANSWER"), True
        ),
        vision_tool_enabled=vision_tool_enabled,
        vision_tool_provider=vision_tool_provider,
        vision_tool_model=vision_tool_model,
        vision_tool_api_key=vision_tool_api_key,
        vision_tool_base_url=_clean_str(os.getenv("SATQUERY_VISION_TOOL_BASE_URL")),
        vision_tool_timeout_s=float(
            _clean_str(os.getenv("SATQUERY_VISION_TOOL_TIMEOUT_S")) or "60"
        ),
        cors_allowed_origins=tuple(
            _as_origin_list(os.getenv("SATQUERY_CORS_ALLOWED_ORIGINS"))
        ),
        backend_port=int(_clean_str(os.getenv("SATQUERY_BACKEND_PORT")) or "8000"),
        tool_output_dir=_clean_str(os.getenv("SATQUERY_TOOL_OUTPUT_DIR")) or "sih_satellite_data",
        memory_backend=_clean_str(os.getenv("SATQUERY_MEMORY_BACKEND")) or "none",
        memory_db_url=_clean_str(os.getenv("SATQUERY_MEMORY_DB_URL")),
        memory_embed_model=(
            _clean_str(os.getenv("SATQUERY_MEMORY_EMBED_MODEL"))
            or "openai:text-embedding-3-small"
        ),
    )


settings = load_settings()
