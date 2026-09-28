"""Vision tool backend: Anthropic Claude vision model."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from backend.config.settings import normalize_claude_model, settings
from backend.vision.openai_provider import (
    _MIME_BY_SUFFIX,
    _SYSTEM_PROMPT,
    _COMPARE_SYSTEM_PROMPT,
    _RESPONSE_SCHEMA,
    _clean_bbox,
    _clean_polygon,
)


class AnthropicVisionProvider:
    def interpret(self, image_path: str, query: str) -> dict:
        api_key = settings.vision_tool_api_key or settings.orchestrator_api_key
        if not api_key:
            raise ValueError(
                "SATQUERY_VISION_TOOL_PROVIDER=anthropic but no API key is set "
                "(SATQUERY_VISION_TOOL_API_KEY, SATQUERY_ORCHESTRATOR_API_KEY, or ANTHROPIC_API_KEY)."
            )

        from langchain_anthropic import ChatAnthropic
        from langchain_core.messages import HumanMessage, SystemMessage

        path = Path(image_path)
        mime = _MIME_BY_SUFFIX.get(path.suffix.lower(), "image/png")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")

        model_name = normalize_claude_model(settings.vision_tool_model or "claude-sonnet-5")
        client_kwargs: dict[str, Any] = {
            "model": model_name,
            "api_key": api_key,
            "max_tokens": 1500,
        }
        base_url = settings.vision_tool_base_url or settings.orchestrator_base_url
        if base_url:
            client_kwargs["base_url"] = base_url

        client = ChatAnthropic(**client_kwargs).with_structured_output(_RESPONSE_SCHEMA)

        message = HumanMessage(
            content=[
                {"type": "text", "text": query},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
            ]
        )
        result: dict = client.invoke([SystemMessage(content=_SYSTEM_PROMPT), message])
        return {
            "text": (result.get("text") if isinstance(result, dict) else "") or "",
            "bbox": _clean_bbox(result.get("bbox") if isinstance(result, dict) else None),
            "polygon": _clean_polygon(result.get("polygon") if isinstance(result, dict) else None),
            "model": model_name,
            "provider": "anthropic",
        }

    def compare(self, image_paths: list[str], query: str) -> dict:
        api_key = settings.vision_tool_api_key or settings.orchestrator_api_key
        if not api_key:
            raise ValueError(
                "SATQUERY_VISION_TOOL_PROVIDER=anthropic but no API key is set "
                "(SATQUERY_VISION_TOOL_API_KEY, SATQUERY_ORCHESTRATOR_API_KEY, or ANTHROPIC_API_KEY)."
            )
        if len(image_paths) != 2:
            raise ValueError("compare() requires exactly two image paths.")

        from langchain_anthropic import ChatAnthropic
        from langchain_core.messages import HumanMessage, SystemMessage

        content: list[dict] = [{"type": "text", "text": query}]
        for label, image_path in zip(("Image A:", "Image B:"), image_paths):
            path = Path(image_path)
            mime = _MIME_BY_SUFFIX.get(path.suffix.lower(), "image/png")
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            content.append({"type": "text", "text": label})
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}})

        model_name = normalize_claude_model(settings.vision_tool_model or "claude-sonnet-5")
        client_kwargs: dict[str, Any] = {
            "model": model_name,
            "api_key": api_key,
            "max_tokens": 1500,
        }
        base_url = settings.vision_tool_base_url or settings.orchestrator_base_url
        if base_url:
            client_kwargs["base_url"] = base_url

        client = ChatAnthropic(**client_kwargs)

        message = HumanMessage(content=content)
        response = client.invoke([SystemMessage(content=_COMPARE_SYSTEM_PROMPT), message])
        content_text = response.content
        if isinstance(content_text, list):
            content_text = "".join(
                block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")
                for block in content_text
                if (isinstance(block, dict) and block.get("type") == "text")
                or getattr(block, "type", "") == "text"
            )
        return {
            "text": str(content_text),
            "model": model_name,
            "provider": "anthropic",
        }
