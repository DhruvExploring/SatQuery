"""Vision provider contract: every backend (OpenAI, local model server) implements this."""

from __future__ import annotations

from typing import Protocol


class VisionProvider(Protocol):
    def interpret(self, image_path: str, query: str) -> dict:
        """Return {"text": str, "model": str, "provider": str, "bbox": list[float] | None}.
        bbox, when present, is [x_min, y_min, x_max, y_max] as fractions 0-1
        of the image's width/height (top-left origin) -- a rough visual
        estimate the model gives only when the query asked it to locate,
        mark, or highlight a specific region; providers that can't produce
        this (e.g. the local model server) should simply omit/null it, never
        fabricate one. Raises on failure -- callers
        (backend/tools/executor.py) are responsible for wrapping errors."""
        ...

    def compare(self, image_paths: list[str], query: str) -> dict:
        """Qualitative two-image comparison (compare_images_visually):
        return {"text": str, "model": str, "provider": str}. image_paths has
        exactly 2 entries, labeled Image A / Image B in that order to the
        model -- they need not be aligned, the same sensor, or even the same
        location; unlike analyze_temporal_change this never requires a grid
        match. Providers that can't do this at all may simply not implement
        it -- callers check with hasattr() rather than assuming every
        provider supports it."""
        ...
