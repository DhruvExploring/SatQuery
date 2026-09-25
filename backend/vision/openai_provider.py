"""Vision tool backend: a hosted OpenAI-compatible vision model."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from backend.config.settings import settings

_MIME_BY_SUFFIX = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

# GPT-4o is a general vision-chat model, not a dedicated grounding model
# (e.g. Grounding DINO) -- asked plainly, it can still give a reasonable
# *rough* bounding box for a region it's already looking at, when the
# question is actually about locating/marking something. This system prompt
# is what makes that box show up only for that kind of question, not every
# answer.
_SYSTEM_PROMPT = (
    "You are an expert satellite/aerial imagery analyst. Answer the user's "
    "question about the attached image directly and factually, in plain "
    "language.\n\n"
    "If -- and only if -- the question asks you to locate, mark, point out, "
    "circle, highlight, or draw attention to a specific region, object, or "
    "feature, also estimate where it is:\n\n"
    "- If the target is compact and roughly blob-shaped (a building, a lake, "
    "a field, a stadium, a parking lot), set \"bbox\" to [x_min, y_min, "
    "x_max, y_max], each a fraction between 0 and 1 of the image's "
    "width/height (0,0 is the top-left corner, 1,1 is the bottom-right "
    "corner). Leave \"polygon\" null.\n"
    "- If the target is instead elongated, curved, or linear (a river, road, "
    "coastline, pipeline, ridge, or boundary line) where a single rectangle "
    "would necessarily include far more area than the feature itself, ALSO "
    "set \"polygon\" to an ordered list of [x, y] points (same 0-1 fraction "
    "convention) tracing the feature's actual path or outline as tightly as "
    "possible -- follow its bends, don't just repeat the bbox's four "
    "corners. Use as many points as the shape actually needs (roughly "
    "6-20), and still also set \"bbox\" to that path's own bounding "
    "rectangle, for callers that only want a plain rectangle.\n\n"
    "Both are a rough visual estimate from looking at the image, not a "
    "precise pixel measurement -- say so in your answer if precision "
    "matters. Never invent a bbox or polygon for something that isn't "
    "actually visible in the image.\n\n"
    "If the question does not ask you to locate or mark anything specific, "
    "set \"bbox\" and \"polygon\" to null."
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
        "polygon": {
            "anyOf": [
                {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                    "minItems": 3,
                },
                {"type": "null"},
            ],
            "description": (
                "Ordered list of [x, y] points (fractions 0-1) tracing an "
                "elongated/curved feature's own path, only when a plain bbox "
                "would include far more area than the feature; otherwise "
                "null."
            ),
        },
    },
    "required": ["text", "bbox", "polygon"],
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


def _clean_polygon(polygon: Any) -> list[list[float]] | None:
    if not isinstance(polygon, list) or len(polygon) < 3:
        return None
    cleaned: list[list[float]] = []
    for point in polygon:
        if not isinstance(point, list) or len(point) != 2:
            return None
        try:
            x, y = float(point[0]), float(point[1])
        except (TypeError, ValueError):
            return None
        if x < 0.0 or x > 1.0 or y < 0.0 or y > 1.0:
            return None
        cleaned.append([x, y])
    return cleaned


# Used for compare() -- two arbitrary images, which analyze_temporal_change's
# pixel-wise diff can't handle unless they're already grid-aligned (same CRS,
# dimensions, transform). This is the qualitative fallback: no alignment
# requirement, works across different sensors or even different places.
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


class OpenAIVisionProvider:
    def interpret(self, image_path: str, query: str) -> dict:
        if not settings.vision_tool_api_key:
            raise ValueError(
                "SATQUERY_VISION_TOOL_PROVIDER=openai but no API key is set "
                "(SATQUERY_VISION_TOOL_API_KEY or OPENAI_API_KEY)."
            )

        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        path = Path(image_path)
        mime = _MIME_BY_SUFFIX.get(path.suffix.lower(), "image/png")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")

        kwargs: dict = {
            "model": settings.vision_tool_model,
            "api_key": settings.vision_tool_api_key,
            "temperature": 0,
            "max_tokens": 1500,
            "timeout": settings.vision_tool_timeout_s,
        }
        if settings.vision_tool_base_url:
            kwargs["base_url"] = settings.vision_tool_base_url
        client = ChatOpenAI(**kwargs).with_structured_output(_RESPONSE_SCHEMA)

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
            "polygon": _clean_polygon(result.get("polygon")),
            "model": settings.vision_tool_model,
            "provider": "openai",
        }

    def compare(self, image_paths: list[str], query: str) -> dict:
        if not settings.vision_tool_api_key:
            raise ValueError(
                "SATQUERY_VISION_TOOL_PROVIDER=openai but no API key is set "
                "(SATQUERY_VISION_TOOL_API_KEY or OPENAI_API_KEY)."
            )
        if len(image_paths) != 2:
            raise ValueError("compare() requires exactly two image paths.")

        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        content: list[dict] = [{"type": "text", "text": query}]
        for label, image_path in zip(("Image A:", "Image B:"), image_paths):
            path = Path(image_path)
            mime = _MIME_BY_SUFFIX.get(path.suffix.lower(), "image/png")
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            content.append({"type": "text", "text": label})
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}})

        kwargs: dict = {
            "model": settings.vision_tool_model,
            "api_key": settings.vision_tool_api_key,
            "temperature": 0,
            "max_tokens": 1500,
            "timeout": settings.vision_tool_timeout_s,
        }
        if settings.vision_tool_base_url:
            kwargs["base_url"] = settings.vision_tool_base_url
        client = ChatOpenAI(**kwargs)

        message = HumanMessage(content=content)
        response = client.invoke([SystemMessage(content=_COMPARE_SYSTEM_PROMPT), message])
        return {
            "text": response.content if isinstance(response.content, str) else str(response.content),
            "model": settings.vision_tool_model,
            "provider": "openai",
        }
