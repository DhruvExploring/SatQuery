"""Picks the configured vision-tool backend. Mode is a static deployment choice —
no automatic runtime failover between local and API (see backend/config/settings.py)."""

from __future__ import annotations

import functools

from backend.config.settings import settings
from backend.vision.base import VisionProvider


@functools.lru_cache(maxsize=1)
def get_vision_provider() -> VisionProvider:
    if settings.vision_tool_provider == "openai":
        from backend.vision.openai_provider import OpenAIVisionProvider

        return OpenAIVisionProvider()

    if settings.vision_tool_provider == "gemini":
        from backend.vision.gemini_provider import GeminiVisionProvider

        return GeminiVisionProvider()

    if settings.vision_tool_provider == "local":
        from backend.vision.local_provider import LocalVisionProvider

        return LocalVisionProvider()

    raise ValueError(f"Unknown SATQUERY_VISION_TOOL_PROVIDER: {settings.vision_tool_provider!r}")
