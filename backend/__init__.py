"""SatQuery AI backend — LangGraph orchestration over remote-sensing tools."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _ensure_venv_site_packages() -> None:
    """Windows-only: keep .venv packages importable after uvicorn --reload respawn.

    `uvicorn --reload` on Windows often starts the worker with the base
    CPython executable instead of `.venv\\Scripts\\python.exe`, so packages
    installed only in the venv (e.g. rasterio) raise ModuleNotFoundError.

    Linux/CI/Docker never touch sys.path here. Delete this helper once the
    documented launch is `.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload`.
    """
    if sys.platform != "win32":
        return

    candidates: list[Path] = []
    virtual_env = os.environ.get("VIRTUAL_ENV")
    if virtual_env:
        candidates.append(Path(virtual_env))
    candidates.append(Path(__file__).resolve().parent.parent / ".venv")

    seen: set[Path] = set()
    for root in candidates:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_dir():
            continue
        seen.add(resolved)
        try:
            if Path(sys.prefix).resolve() == resolved:
                return
        except OSError:
            pass
        site_packages = resolved / "Lib" / "site-packages"
        if not site_packages.is_dir():
            continue
        site_str = str(site_packages)
        if site_str not in sys.path:
            sys.path.insert(0, site_str)
            logger.warning(
                "SATQUERY_VENV_SYSPATH injected %s (interpreter=%s). "
                "Prefer launching with .venv\\Scripts\\python.exe -m uvicorn.",
                site_str,
                sys.executable,
            )
        return


_ensure_venv_site_packages()
