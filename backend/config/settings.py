"""Runtime flags for the orchestrator.

Week 1 uses a mock planner and mock tools so the graph can be tested
without a paid LLM or a live Sentinel Hub call. Flip `use_mock_tools`
later when execute() should call the real MCP tool.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the SatQuery project root (one level above backend/)
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
    use_mock_tools: bool = True

    # Tool config
    tool_output_dir: str = "sih_satellite_data"   # relative to the tool module

    # Memory config — only read when use_mock_planner=False
    # "none"    → no memory store (stateless, default)
    # "in_memory" → InMemoryStore (dev — lost on restart)
    # "postgres"  → PostgresStore (production — requires SATQUERY_MEMORY_DB_URL)
    memory_backend: str = "none"
    memory_db_url: str | None = None   # PostgreSQL connection string for production
    memory_embed_model: str = "openai:text-embedding-3-small"  # embedding model for vector search

    # LLM planner config — only read when use_mock_planner=False
    llm_provider: str = "openai"          # "openai" | "ollama" | "anthropic"
    llm_model: str = "gpt-4o-mini"        # any model the provider supports
    llm_base_url: str | None = None       # set for Ollama: "http://localhost:11434"
    llm_api_key: str | None = None        # set for OpenAI / Anthropic


def load_settings() -> Settings:
    return Settings(
        use_mock_planner=_as_bool(os.getenv("SATQUERY_MOCK_PLANNER"), True),
        use_mock_tools=_as_bool(os.getenv("SATQUERY_MOCK_TOOLS"), True),
        llm_provider=os.getenv("SATQUERY_LLM_PROVIDER", "openai"),
        llm_model=os.getenv("SATQUERY_LLM_MODEL", "gpt-4o-mini"),
        llm_base_url=os.getenv("SATQUERY_LLM_BASE_URL") or None,
        llm_api_key=os.getenv("SATQUERY_LLM_API_KEY") or None,
        memory_backend=os.getenv("SATQUERY_MEMORY_BACKEND", "none"),
        memory_db_url=os.getenv("SATQUERY_MEMORY_DB_URL") or None,
        memory_embed_model=os.getenv("SATQUERY_MEMORY_EMBED_MODEL", "openai:text-embedding-3-small"),
    )


settings = load_settings()
