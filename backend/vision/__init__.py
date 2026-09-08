"""Vision tool: interprets a rendered image on request, swappable between an API
vision model and a local model server (InternVL-1B or EarthMind-4B).
"""

from backend.vision.factory import get_vision_provider

__all__ = ["get_vision_provider"]
