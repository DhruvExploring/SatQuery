# syntax=docker/dockerfile:1
#
# Build context is this folder (local_model_server/), unlike backend/Dockerfile:
#   docker build -f local_model_server/Dockerfile local_model_server/
#
# CPU-only unless the host has the NVIDIA Container Toolkit installed and the
# container is run with GPU access (see the `local-vlm` service in the root
# docker-compose.yml). On Docker Desktop for Mac this is always CPU-only — use
# the native run path in README.md for real speed during development.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${LOCAL_VLM_PORT:-8080}"]
