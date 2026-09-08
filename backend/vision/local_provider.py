"""Vision tool backend: the local_model_server sidecar (InternVL-1B or EarthMind-4B,
whichever it was started with — see local_model_server/README.md). The backend does
not need to know which model is loaded; it only talks to one small HTTP contract.
"""

from __future__ import annotations

import base64
from pathlib import Path

import requests

from backend.config.settings import settings


class LocalVisionProvider:
    def interpret(self, image_path: str, query: str) -> dict:
        if not settings.vision_tool_base_url:
            raise ValueError(
                "SATQUERY_VISION_TOOL_PROVIDER=local but SATQUERY_VISION_TOOL_BASE_URL is not set."
            )

        encoded = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
        response = requests.post(
            f"{settings.vision_tool_base_url.rstrip('/')}/infer",
            json={"image_base64": encoded, "query": query},
            timeout=settings.vision_tool_timeout_s,
        )
        response.raise_for_status()
        payload = response.json()
        return {
            "text": payload.get("text", ""),
            "model": payload.get("model", settings.vision_tool_model),
            "provider": "local",
        }
