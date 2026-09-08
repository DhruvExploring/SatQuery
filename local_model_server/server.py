"""Local VLM inference server.

Serves exactly one model, chosen at startup by LOCAL_VLM_MODEL_ID — restart with
a different value to switch models (e.g. internvl-1b <-> earthmind-4b). The
SatQuery backend (backend/vision/local_provider.py) only talks to this over
HTTP; it never loads model weights itself, so it doesn't need to know which
model is currently loaded here.

Run (from inside local_model_server/):
    uvicorn server:app --host 0.0.0.0 --port ${LOCAL_VLM_PORT:-8080}
"""

from __future__ import annotations

import base64
import io
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# LOCAL_VLM_MODEL_ID -> default Hugging Face repo id. Override any entry (or add a
# new model id entirely) with LOCAL_VLM_HF_REPO, without touching this code.
_MODEL_REPOS = {
    "internvl-1b": "OpenGVLab/InternVL3_5-1B",
    "earthmind-4b": "sy1998/EarthMind-4B",
}

_state: dict = {"adapter": None, "model_id": None}


def _load_model() -> None:
    from model_adapters import (
        EarthMindAdapter,
        InternVLAdapter,
        resolve_device_and_dtype,
    )

    model_id = os.getenv("LOCAL_VLM_MODEL_ID", "internvl-1b").strip().lower()
    repo_id = os.getenv("LOCAL_VLM_HF_REPO") or _MODEL_REPOS.get(model_id)
    if not repo_id:
        raise RuntimeError(
            f"Unknown LOCAL_VLM_MODEL_ID={model_id!r}. Set LOCAL_VLM_HF_REPO explicitly, "
            f"or use one of: {sorted(_MODEL_REPOS)}."
        )

    device, dtype = resolve_device_and_dtype(os.getenv("LOCAL_VLM_DEVICE", "auto"))
    logger.info("Loading %s (%s) on %s ...", model_id, repo_id, device)

    adapter_cls = EarthMindAdapter if model_id == "earthmind-4b" else InternVLAdapter
    _state["adapter"] = adapter_cls(repo_id, device, dtype)
    _state["model_id"] = model_id
    logger.info("Model %s ready.", model_id)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    _load_model()
    yield


app = FastAPI(title="SatQuery local VLM server", lifespan=lifespan)


class InferRequest(BaseModel):
    image_base64: str
    query: str


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok" if _state["adapter"] is not None else "loading",
        "model": _state["model_id"],
    }


@app.post("/infer")
def infer(request: InferRequest) -> dict:
    adapter = _state["adapter"]
    if adapter is None:
        raise HTTPException(status_code=503, detail="Model is still loading.")
    try:
        image_bytes = base64.b64decode(request.image_base64)
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        text = adapter.generate(image, request.query)
        return {"text": text, "model": _state["model_id"]}
    except Exception as exc:
        logger.exception("Inference failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
