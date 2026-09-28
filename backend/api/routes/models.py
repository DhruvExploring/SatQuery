"""Read-only status endpoint the frontend uses to render the Models view truthfully.

No fake data, no live model ping — just reflects the current .env configuration.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.config.settings import settings

router = APIRouter()


@router.get("/api/v1/models", tags=["meta"])
def get_models_status() -> dict:
    return {
        "orchestrator": {
            "provider": settings.orchestrator_provider,
            "model": (
                settings.orchestrator_model
                if settings.orchestrator_provider != "mock"
                else None
            ),
            "synthesizes_answer": (
                settings.orchestrator_provider != "mock"
                and settings.orchestrator_synthesize_answer
            ),
        },
        "vision_tool": {
            "enabled": settings.vision_tool_enabled,
            "provider": settings.vision_tool_provider if settings.vision_tool_enabled else None,
            "model": settings.vision_tool_model if settings.vision_tool_enabled else None,
        },
        "supported_models": [
            {
                "id": "claude-sonnet-5",
                "name": "Claude Sonnet 5",
                "tier": "sonnet",
                "description": "Default flagship model. State-of-the-art multimodal vision and spatial tool orchestration.",
            },
            {
                "id": "claude-haiku-4-5",
                "name": "Claude 4.5 Haiku",
                "tier": "haiku",
                "description": "Ultra-fast, cost-effective model for high-throughput queries.",
            },
            {
                "id": "claude-opus-5-5",
                "name": "Claude Opus 5.5",
                "tier": "opus",
                "description": "Deepest analytical reasoning for complex multi-temporal and multi-sensor missions.",
            },
        ],
    }
