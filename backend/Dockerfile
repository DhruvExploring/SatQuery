# syntax=docker/dockerfile:1
#
# Build from the repository root (build context = repo root), since this image
# needs backend/ plus the top-level Tool_1..8_*/ packages, satquery_workflows.py
# and skills/ — not just the backend/ folder:
#   docker build -f backend/Dockerfile .
# docker-compose.yml at the repo root does this for you.

FROM python:3.12-slim

# rasterio's PyPI wheels vendor GDAL/PROJ/GEOS/etc. themselves (rasterio.libs/),
# so no system libgdal package is required — but they still dynamically link a
# few base-OS libraries (e.g. libexpat) that python:3.12-slim strips out to
# stay small. PROJ_NETWORK=OFF avoids a multi-minute hang on the first CRS
# operation in a container with no route to the PROJ CDN grid registry
# (offline/restricted-egress deployments).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PROJ_NETWORK=OFF

RUN apt-get update && apt-get install -y --no-install-recommends \
      libexpat1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY Tool_1_fetch_optical_imagery/ Tool_1_fetch_optical_imagery/
COPY Tool_2_fetch_multispectral_imagery/ Tool_2_fetch_multispectral_imagery/
COPY Tool_3_fetch_sar_imagery/ Tool_3_fetch_sar_imagery/
COPY Tool_4_fetch_weather_environment/ Tool_4_fetch_weather_environment/
COPY Tool_5_compute_vegetation_indices/ Tool_5_compute_vegetation_indices/
COPY Tool_6_inspect_geotiff_metadata/ Tool_6_inspect_geotiff_metadata/
COPY Tool_7_analyze_temporal_change/ Tool_7_analyze_temporal_change/
COPY Tool_8_analyze_spatial_landcover_terrain/ Tool_8_analyze_spatial_landcover_terrain/
COPY Tool_9_fetch_web_intelligence/ Tool_9_fetch_web_intelligence/
COPY satquery_workflows.py .
COPY skills/ skills/

EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${SATQUERY_BACKEND_PORT:-8000}"]
