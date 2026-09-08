---
name: derive-aoi-from-uploaded-file
description: Ground a fetch request in an uploaded GeoTIFF's own bounds instead of asking the user for a bbox that already exists in the file.
---

# derive-aoi-from-uploaded-file

Core principle: never ask the user for information the request already
contains in another form. If a fetch tool (`fetch_optical_imagery`,
`fetch_multispectral_imagery`, `fetch_sar_imagery`) is missing only its
`bbox`, and the request already includes a GeoTIFF (`input_file`), that file's
own georeferenced extent already answers "where" — inspect it and use it
instead of clarifying.

## When this applies

- User uploads or references a `.tif`/`.tiff` file **and** asks for a
  different sensor/product than the one they uploaded (e.g. uploads an
  optical scene, asks "get me the SAR image for this area").
- No `bbox` (and no `latitude`/`longitude`) was supplied any other way.

## When NOT to use

- No file is present at all — there is genuinely nothing to derive a location
  from. Only then should the orchestrator clarify and ask for a bbox or
  latitude/longitude.
- The uploaded file has no usable CRS (rare) — the derivation step fails
  cleanly with an error rather than fetching an incorrect area.

## Mechanism (already implemented, not a manual step)

This is handled automatically by `backend/orchestrator/handshake.py`:
`inspect_geotiff_metadata` runs first, its `spatial.bounds_wgs84` becomes the
`bbox` for the next step, and the originally requested fetch tool runs with
that derived AOI — a 2-step agenda, not a clarify. Do not re-ask the user for
bbox when this condition is met; the backend already resolves it.

## Grounding requirement

Every answer must be built only from real tool output collected during this
request (or a prior request in the same handshake) — never state a fact
about imagery, coordinates, or file contents that wasn't actually returned by
a tool call. If a needed input genuinely cannot be derived from anything
already available (no file, no bbox, no lat/lon, no prior tool output), the
correct response is `clarify` naming exactly what's missing — not a guess.
