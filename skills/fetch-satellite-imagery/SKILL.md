---
name: fetch-satellite-imagery
description: Download Sentinel-2 optical or multispectral GeoTIFF imagery for a bounding box and date range.
---

# fetch-satellite-imagery

Use this skill when the user requests satellite imagery, Sentinel-2 imagery, optical imagery,
or a GeoTIFF download for a specific location.

## Required inputs

- `bbox`: Bounding box as [min_lon, min_lat, max_lon, max_lat]. Ask for this if missing.
- `start_date`: Start of date range in YYYY-MM-DD format.
- `end_date`: End of date range in YYYY-MM-DD format.

## Optional inputs

- `modality`: "optical" (default) or "multispectral"
- `bands`: List of band names, required only when modality is "multispectral"
- `max_cloud_cover`: Maximum cloud cover percentage (default 30.0)
- `width`: Output image width in pixels (default 512)
- `height`: Output image height in pixels (default 512)

## When to use

- User says: "fetch imagery", "download satellite image", "get Sentinel-2 data", "show me a GeoTIFF"
- User mentions a geographic location and a date range

## When NOT to use

- User asks for radar or SAR data → use fetch-sar instead
- User asks a general question without a location → respond with chat action

## Output

Returns a GeoTIFF file path, scene ID, acquisition time, cloud cover, and raster metadata.

## Tool name for executor

When deciding to use this skill, set `tool` to exactly one of:
- `fetch_optical_imagery` for RGB / visual Sentinel-2
- `fetch_multispectral_imagery` for analytical / vegetation / band-stack Sentinel-2

Never invent names such as Sentinelimagery or SentinelHub_Search.
