# api/endpoint.py
# ============================================================
# SatQuery AI — FastAPI Inference Endpoint
# ============================================================
# Sprint 4 — Serves EarthMind as a REST API
#
# Responsibilities:
#   - Accept image(s) + query from orchestrator
#   - Route to correct EarthMind inference method
#   - Return structured JSON response
#   - Provide health check and model status endpoints
#
# This endpoint is what Nishika/Shrishti's LangGraph
# orchestrator calls when routing a query to EarthMind.
#
# Usage:
#   uvicorn api.endpoint:app --host 0.0.0.0 --port 8001
#
# Endpoints:
#   GET  /api/v1/health          — Health check
#   GET  /api/v1/status          — Model status + VRAM
#   POST /api/v1/inference       — Main inference endpoint
#   POST /api/v1/inference/vqa   — VQA only
#   POST /api/v1/inference/caption — Captioning only
#   POST /api/v1/inference/ground  — Grounding only
#   POST /api/v1/inference/change  — Change VQA only
# ============================================================

import io
import logging
import time
from enum import Enum
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from PIL import Image
from pydantic import BaseModel, Field

from config import API_CONFIG, MODEL_CONFIG
from models.earthmind_runner import runner

logger = logging.getLogger(__name__)


# ── App Setup ─────────────────────────────────────────────────
app = FastAPI(
    title="SatQuery AI — EarthMind Inference API",
    description=(
        "REST API for EarthMind-4B satellite image analysis. "
        "Supports VQA, captioning, grounding, and change detection."
    ),
    version=API_CONFIG["version"],
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow orchestrator (running on same machine) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Task Enum ─────────────────────────────────────────────────
class TaskType(str, Enum):
    """
    Supported inference task types.
    Orchestrator sends this to route to correct method.
    """
    VQA        = "vqa"
    CAPTIONING = "captioning"
    GROUNDING  = "grounding"
    CHANGE_VQA = "change_vqa"
    SAR_OPTICAL = "sar_optical"
    AUTO        = "auto"          # Orchestrator decides


# ── Response Schema ───────────────────────────────────────────
class InferenceResponse(BaseModel):
    """
    Standardized response returned to orchestrator.
    All fields are always present — None if not applicable.
    """
    task:            str            = Field(..., description="Task that was executed")
    answer:          str            = Field(..., description="Model text response")
    confidence:      float          = Field(..., description="Confidence score [0,1]")
    model:           str            = Field(..., description="Model name used")
    elapsed_sec:     float          = Field(..., description="Inference time in seconds")
    image_count:     int            = Field(..., description="Number of images processed")
    error:           Optional[str]  = Field(None, description="Error message if failed")


class HealthResponse(BaseModel):
    status:  str
    model:   str
    loaded:  bool
    version: str


class StatusResponse(BaseModel):
    model:      str
    loaded:     bool
    device:     str
    vram_gb:    float
    quantized:  bool
    version:    str


# ── Startup / Shutdown ────────────────────────────────────────
@app.on_event("startup")
async def startup_event() -> None:
    """
    Loads EarthMind when the API server starts.
    Model stays in VRAM for all subsequent requests.
    """
    logger.info("API startup — loading EarthMind...")
    try:
        runner.load()
        logger.info("✅ EarthMind ready for inference.")
    except Exception as e:
        logger.error(f"Failed to load EarthMind on startup: {e}")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """
    Unloads EarthMind cleanly when server shuts down.
    """
    logger.info("API shutdown — unloading EarthMind...")
    runner.unload()


# ── Helpers ───────────────────────────────────────────────────
async def _read_image(upload: UploadFile) -> Image.Image:
    """
    Reads an uploaded file and converts to PIL RGB Image.

    Supports:
        - JPEG / PNG  (benchmark datasets)
        - GeoTIFF / TIFF (real satellite imagery)

    Args:
        upload : FastAPI UploadFile object.

    Returns:
        PIL.Image in RGB mode.

    Raises:
        HTTPException 400 : If file cannot be read as image.
    """
    try:
        contents = await upload.read()
        filename = upload.filename or ""

        # GeoTIFF support
        if filename.lower().endswith((".tif", ".tiff")):
            try:
                import rasterio
                import numpy as np
                from io import BytesIO

                with rasterio.MemoryFile(contents) as memfile:
                    with memfile.open() as src:
                        if src.count >= 3:
                            r = src.read(1)
                            g = src.read(2)
                            b = src.read(3)
                        else:
                            band = src.read(1)
                            r = g = b = band

                        def normalize(arr):
                            arr = arr.astype(float)
                            mn, mx = arr.min(), arr.max()
                            if mx > mn:
                                arr = (arr - mn) / (mx - mn) * 255
                            return arr.astype("uint8")

                        rgb = np.stack(
                            [normalize(r), normalize(g), normalize(b)],
                            axis=-1,
                        )
                        return Image.fromarray(rgb, mode="RGB")

            except ImportError:
                logger.warning(
                    "rasterio not available — "
                    "falling back to PIL for TIFF."
                )

        # Standard image formats
        image = Image.open(io.BytesIO(contents)).convert("RGB")
        return image

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot read image '{upload.filename}': {e}",
        )


def _auto_detect_task(
    question:    str,
    has_image2:  bool,
) -> TaskType:
    """
    Automatically detects task type from question and inputs.
    Used when task=auto is sent by orchestrator.

    Args:
        question   : User's natural language query.
        has_image2 : True if a second image was uploaded.

    Returns:
        Detected TaskType.
    """
    q = question.lower()

    if has_image2:
        if any(w in q for w in ["change", "differ", "before",
                                  "after", "compare", "between"]):
            return TaskType.CHANGE_VQA
        return TaskType.SAR_OPTICAL

    if any(w in q for w in ["describe", "caption", "what is",
                              "scene", "overall", "summarize"]):
        return TaskType.CAPTIONING

    if any(w in q for w in ["locate", "highlight", "where is",
                              "find", "ground", "show", "bbox",
                              "bounding"]):
        return TaskType.GROUNDING

    return TaskType.VQA


# ── Health Check ──────────────────────────────────────────────
@app.get(
    "/api/v1/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Health check",
)
async def health_check() -> HealthResponse:
    """
    Returns API health status.
    Orchestrator calls this before sending inference requests.
    """
    return HealthResponse(
        status="ok" if runner.is_loaded else "model_not_loaded",
        model=MODEL_CONFIG["name"],
        loaded=runner.is_loaded,
        version=API_CONFIG["version"],
    )


# ── Model Status ──────────────────────────────────────────────
@app.get(
    "/api/v1/status",
    response_model=StatusResponse,
    tags=["System"],
    summary="Model status and VRAM usage",
)
async def model_status() -> StatusResponse:
    """
    Returns detailed model status including VRAM usage.
    Useful for debugging memory issues on RTX 4060.
    """
    status = runner.status()
    return StatusResponse(
        model=status["model"],
        loaded=status["loaded"],
        device=status["device"],
        vram_gb=status["vram_gb"],
        quantized=status["4bit_quant"],
        version=API_CONFIG["version"],
    )


# ── Main Inference Endpoint ───────────────────────────────────
@app.post(
    "/api/v1/inference",
    response_model=InferenceResponse,
    tags=["Inference"],
    summary="Main inference — auto task detection",
)
async def inference(
    question: str       = Form(..., description="Natural language query"),
    task:     TaskType  = Form(TaskType.AUTO, description="Task type"),
    image1:   UploadFile = File(..., description="Primary satellite image"),
    image2:   Optional[UploadFile] = File(
        None,
        description="Second image for paired analysis (SAR or temporal)",
    ),
) -> InferenceResponse:
    """
    Main inference endpoint called by the LangGraph orchestrator.

    Accepts:
        - Single image  → VQA, captioning, or grounding
        - Image pair    → Change VQA or SAR+Optical fusion

    Auto-detects task type if task=auto is sent.

    Returns structured JSON with answer, confidence,
    elapsed time, and task type executed.
    """
    if not runner.is_loaded:
        raise HTTPException(
            status_code=503,
            detail="EarthMind is not loaded. Restart the server.",
        )

    start_time = time.time()

    # Read images
    pil_image1 = await _read_image(image1)
    pil_image2 = None

    if image2 and image2.filename:
        pil_image2 = await _read_image(image2)

    # Auto-detect task
    resolved_task = (
        _auto_detect_task(question, pil_image2 is not None)
        if task == TaskType.AUTO
        else task
    )

    logger.info(
        f"Inference request — "
        f"Task: {resolved_task} | "
        f"Images: {1 + (pil_image2 is not None)} | "
        f"Question: {question[:80]}"
    )

    # Run inference
    try:
        if resolved_task == TaskType.VQA:
            answer, confidence = runner.infer_vqa(
                image=pil_image1,
                question=question,
            )

        elif resolved_task == TaskType.CAPTIONING:
            answer, confidence = runner.infer_captioning(
                image=pil_image1,
            )

        elif resolved_task == TaskType.GROUNDING:
            answer, confidence = runner.infer_grounding(
                image=pil_image1,
                region_description=question,
            )

        elif resolved_task == TaskType.CHANGE_VQA:
            if pil_image2 is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Change VQA requires two images. "
                        "Upload image2 (the 'after' image)."
                    ),
                )
            answer, confidence = runner.infer_change_vqa(
                image_before=pil_image1,
                image_after=pil_image2,
                question=question,
            )

        elif resolved_task == TaskType.SAR_OPTICAL:
            if pil_image2 is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "SAR+Optical analysis requires two images. "
                        "Upload image2 (the SAR image)."
                    ),
                )
            answer, confidence = runner.infer_sar_optical(
                optical_image=pil_image1,
                sar_image=pil_image2,
                question=question,
            )

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown task type: {resolved_task}",
            )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Inference failed: {e}", exc_info=True)
        return InferenceResponse(
            task=resolved_task,
            answer="",
            confidence=0.0,
            model=MODEL_CONFIG["name"],
            elapsed_sec=round(time.time() - start_time, 3),
            image_count=1 + (pil_image2 is not None),
            error=str(e),
        )

    elapsed = round(time.time() - start_time, 3)

    logger.info(
        f"✅ Inference complete — "
        f"Task: {resolved_task} | "
        f"Confidence: {confidence:.3f} | "
        f"Time: {elapsed}s"
    )

    return InferenceResponse(
        task=str(resolved_task),
        answer=answer,
        confidence=confidence,
        model=MODEL_CONFIG["name"],
        elapsed_sec=elapsed,
        image_count=1 + (pil_image2 is not None),
        error=None,
    )


# ── Task-Specific Convenience Endpoints ──────────────────────
@app.post(
    "/api/v1/inference/vqa",
    response_model=InferenceResponse,
    tags=["Inference"],
    summary="VQA — single image question answering",
)
async def vqa_endpoint(
    question: str        = Form(...),
    image1:   UploadFile = File(...),
) -> InferenceResponse:
    """Single image VQA — convenience wrapper."""
    return await inference(
        question=question,
        task=TaskType.VQA,
        image1=image1,
        image2=None,
    )


@app.post(
    "/api/v1/inference/caption",
    response_model=InferenceResponse,
    tags=["Inference"],
    summary="Captioning — describe satellite image",
)
async def caption_endpoint(
    image1: UploadFile = File(...),
) -> InferenceResponse:
    """Satellite image captioning — convenience wrapper."""
    return await inference(
        question="Describe this satellite image.",
        task=TaskType.CAPTIONING,
        image1=image1,
        image2=None,
    )


@app.post(
    "/api/v1/inference/ground",
    response_model=InferenceResponse,
    tags=["Inference"],
    summary="Grounding — locate a region by text description",
)
async def ground_endpoint(
    region_description: str        = Form(...),
    image1:             UploadFile = File(...),
) -> InferenceResponse:
    """Text-guided region grounding — convenience wrapper."""
    return await inference(
        question=region_description,
        task=TaskType.GROUNDING,
        image1=image1,
        image2=None,
    )


@app.post(
    "/api/v1/inference/change",
    response_model=InferenceResponse,
    tags=["Inference"],
    summary="Change VQA — bi-temporal change analysis",
)
async def change_endpoint(
    question:     str        = Form(...),
    image_before: UploadFile = File(...),
    image_after:  UploadFile = File(...),
) -> InferenceResponse:
    """Bi-temporal change VQA — convenience wrapper."""
    return await inference(
        question=question,
        task=TaskType.CHANGE_VQA,
        image1=image_before,
        image2=image_after,
    )


# ── Run Directly ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.endpoint:app",
        host=API_CONFIG["host"],
        port=API_CONFIG["port"],
        reload=False,
        log_level="info",
    )