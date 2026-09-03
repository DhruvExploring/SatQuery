---
name: fetch-sar
description: Download Sentinel-1 SAR (Synthetic Aperture Radar) imagery for a bounding box and date range.
---

# fetch-sar

Use this skill when the user requests SAR imagery, radar data, Sentinel-1 imagery,
or backscatter data for a specific location.

SAR imagery is useful when optical imagery is blocked by clouds or when the user
explicitly needs radar-based observation (e.g. flood mapping, ship detection,
subsidence monitoring).

## Required inputs

- `bbox`: Bounding box as [min_lon, min_lat, max_lon, max_lat]. Ask for this if missing.
- `start_date`: Start of date range in YYYY-MM-DD format.
- `end_date`: End of date range in YYYY-MM-DD format.

## Optional inputs

- `width`: Output image width in pixels (default 512)
- `height`: Output image height in pixels (default 512)

## When to use

- User says: "SAR", "radar", "Sentinel-1", "backscatter", "cloud-free radar imagery"
- User mentions flood mapping, ship detection, or subsidence — SAR is preferred for these

## When NOT to use

- User asks for optical or Sentinel-2 data → use fetch-satellite-imagery instead
- User asks a general question without a location → respond with chat action

## Current status

This tool is registered and routed correctly. The implementation (Sentinel-1 API integration)
is pending — it will be added in a future notebook. Until then, calling this tool returns
a "not implemented" error, which is handled gracefully by the orchestrator.

## Tool name for executor

When deciding to use this skill, set `tool` = `fetch_sar` in the Plan.
