"""Vision tool backend: Google Gemini multimodal vision model."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from backend.config.settings import settings

_MIME_BY_SUFFIX = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

_SYSTEM_PROMPT = (
    "You are an expert satellite/aerial imagery analyst. Answer the user's "
    "question about the attached image directly and factually, in plain "
    "language.\n\n"
    "If -- and only if -- the question asks you to locate, mark, point out, "
    "circle, highlight, or draw attention to a specific region, object, or "
    "feature, also estimate a bounding box for that region: set \"bbox\" to "
    "[x_min, y_min, x_max, y_max], each a fraction between 0 and 1 of the "
    "image's width/height (0,0 is the top-left corner, 1,1 is the "
    "bottom-right corner). This is a rough visual estimate from looking at "
    "the image, not a precise pixel measurement -- say so in your answer if "
    "precision matters. Never invent a bbox for something that isn't "
    "actually visible in the image.\n\n"
    "If the question does not ask you to locate or mark anything specific, "
    "set \"bbox\" to null."
)

_RESPONSE_SCHEMA = {
    "title": "VisionAnalysis",
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": "The natural-language answer to the user's question.",
        },
        "bbox": {
            "anyOf": [
                {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4},
                {"type": "null"},
            ],
            "description": (
                "[x_min, y_min, x_max, y_max] as fractions 0-1 of the image's "
                "width/height, only when the question asked to locate/mark/"
                "highlight something; otherwise null."
            ),
        },
    },
    "required": ["text", "bbox"],
}


def _clean_bbox(bbox: Any) -> list[float] | None:
    if not isinstance(bbox, list) or len(bbox) != 4:
        return None
    try:
        values = [float(v) for v in bbox]
    except (TypeError, ValueError):
        return None
    if any(v < 0.0 or v > 1.0 for v in values):
        return None
    return values


_COMPARE_SYSTEM_PROMPT = (
    "You are an expert satellite/aerial imagery analyst. You are given two "
    "images, labeled Image A and Image B in that order. They may be the "
    "same location at different times, different sensors of the same "
    "location, or entirely different places -- do not assume they show the "
    "same location unless the visual evidence actually supports it.\n\n"
    "Compare them and answer the user's question factually: describe what "
    "is visually similar and different between them (e.g. land cover, "
    "built-up area, vegetation, water extent, visible damage or change). "
    "If they clearly show different geographic areas entirely, say so "
    "plainly instead of forcing a before/after comparison that doesn't "
    "make sense."
)


class GeminiVisionProvider:
    def interpret(self, image_path: str, query: str) -> dict:
        if not settings.vision_tool_api_key:
            raise ValueError(
                "SATQUERY_VISION_TOOL_PROVIDER=gemini but no API key is set "
                "(SATQUERY_VISION_TOOL_API_KEY, GEMINI_API_KEY, or GOOGLE_API_KEY)."
            )

        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.output_parsers import JsonOutputParser

        path = Path(image_path)
        mime = _MIME_BY_SUFFIX.get(path.suffix.lower(), "image/png")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")

        client = ChatGoogleGenerativeAI(
            model=settings.vision_tool_model,
            google_api_key=settings.vision_tool_api_key,
            timeout=settings.vision_tool_timeout_s,
        ) | JsonOutputParser()

        message = HumanMessage(
            content=[
                {"type": "text", "text": query},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
            ]
        )
        result: dict = client.invoke([SystemMessage(content=_SYSTEM_PROMPT), message])
        return {
            "text": result.get("text") or "",
            "bbox": _clean_bbox(result.get("bbox")),
            "model": settings.vision_tool_model,
            "provider": "gemini",
        }

    def compare(self, image_paths: list[str], query: str) -> dict:
        if not settings.vision_tool_api_key:
            raise ValueError(
                "SATQUERY_VISION_TOOL_PROVIDER=gemini but no API key is set "
                "(SATQUERY_VISION_TOOL_API_KEY, GEMINI_API_KEY, or GOOGLE_API_KEY)."
            )
        if len(image_paths) != 2:
            raise ValueError("compare() requires exactly two image paths.")

        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_google_genai import ChatGoogleGenerativeAI

        content: list[dict] = [{"type": "text", "text": query}]
        for label, image_path in zip(("Image A:", "Image B:"), image_paths):
            path = Path(image_path)
            mime = _MIME_BY_SUFFIX.get(path.suffix.lower(), "image/png")
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            content.append({"type": "text", "text": label})
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}})

        client = ChatGoogleGenerativeAI(
            model=settings.vision_tool_model,
            google_api_key=settings.vision_tool_api_key,
            timeout=settings.vision_tool_timeout_s,
        )

        message = HumanMessage(content=content)
        response = client.invoke([SystemMessage(content=_COMPARE_SYSTEM_PROMPT), message])
        return {
            "text": response.content if isinstance(response.content, str) else str(response.content),
            "model": settings.vision_tool_model,
            "provider": "gemini",
        }
