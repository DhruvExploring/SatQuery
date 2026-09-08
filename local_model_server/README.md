# SatQuery local VLM server

Serves the vision tool's **local** backend — one of InternVL-1B or EarthMind-4B,
chosen by `LOCAL_VLM_MODEL_ID`. The main SatQuery backend talks to whatever is
running here over a tiny HTTP contract (`POST /infer`); it never loads model
weights itself, so switching models is a restart of this service, not a change
to the backend.

This is a separate service from `backend/` on purpose — it depends on
`torch`/`transformers`, a completely different (and much heavier) footprint than
the FastAPI/rasterio backend.

## Hardware reality check

| Model | Disk size | Realistic hardware |
| :--- | :--- | :--- |
| `internvl-1b` (`OpenGVLab/InternVL3_5-1B`) | ~2-3 GB | Runs on most laptops, CPU included. This is the "should just work" default. |
| `earthmind-4b` (`sy1998/EarthMind-4B`) | ~15 GB | Needs a real GPU (or a Mac with large unified memory) to be usable. CPU inference will be very slow. |

Both require `transformers` with `trust_remote_code=True` (custom architecture
code shipped in the model repo) — they cannot be served via Ollama or
llama.cpp.

## Run natively (recommended for this Mac)

Docker Desktop on macOS cannot pass through Metal/GPU acceleration to Linux
containers, so a containerized model here runs CPU-only. For real speed during
development, run this service directly in a venv so it can use MPS:

```bash
cd local_model_server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set LOCAL_VLM_DEVICE=mps
uvicorn server:app --host 0.0.0.0 --port 8080
```

First start downloads the model weights into `LOCAL_VLM_HF_CACHE_DIR` — this can
take a while for EarthMind-4B (~15GB).

## Run via Docker (Compose `local-models` profile)

```bash
docker compose --profile local-models up local-vlm
```

CPU-only on Docker Desktop for Mac. On a Linux host with an NVIDIA GPU and the
NVIDIA Container Toolkit installed, this profile gets real GPU acceleration.

## Switching models

Restart with a different `LOCAL_VLM_MODEL_ID` (`internvl-1b` | `earthmind-4b`).
There is no in-process hot-swap — this matches the rest of SatQuery's model
configuration, which is a static per-deployment choice, not an automatic
runtime failover.

## API contract

```
POST /infer
{"image_base64": "<base64 PNG/JPEG>", "query": "What does this image show?"}
-> {"text": "...", "model": "internvl-1b"}

GET /health -> {"status": "ok" | "loading", "model": "internvl-1b"}
```
