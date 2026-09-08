/**
 * Raster file concerns: uploading a GeoTIFF, and building preview/download
 * URLs for a file path returned by either the upload endpoint or
 * POST /api/v1/query's tool_results.
 */

import { API_BASE } from './satqueryApi';

export function rasterPreviewUrl(filePath, size = 1024) {
  if (!filePath) return '';
  const params = new URLSearchParams({ path: filePath, size: String(size) });
  return `${API_BASE}/api/v1/raster-preview?${params.toString()}`;
}

export function rasterDownloadUrl(filePath) {
  if (!filePath) return '';
  const params = new URLSearchParams({ path: filePath });
  return `${API_BASE}/api/v1/raster-file?${params.toString()}`;
}

/**
 * POST /api/v1/upload-raster with a .tif/.tiff File from a browser file
 * picker. Returns { ok: true, path } or { ok: false, error }.
 */
export async function uploadRasterFile(file) {
  const form = new FormData();
  form.append('file', file);

  let res;
  try {
    res = await fetch(`${API_BASE}/api/v1/upload-raster`, { method: 'POST', body: form });
  } catch (err) {
    return { ok: false, error: err.message || 'Network error' };
  }

  let body = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }

  if (!res.ok) {
    return { ok: false, error: body?.detail || `Upload failed (HTTP ${res.status})` };
  }
  return { ok: true, path: body?.path };
}

/**
 * Find GeoTIFF/raster paths inside a tool_results array, for showing output
 * previews. Requires an actual path separator so bare-filename fields (e.g.
 * inspect_geotiff_metadata's "file_name") don't get treated as a usable path
 * — only "file_path"-shaped values do.
 */
function isRasterPath(key, value) {
  if (typeof value !== 'string' || !value.trim()) return false;
  if (!/\.(tif|tiff|png|jpg|jpeg|webp)$/i.test(value)) return false;
  if (!/[/\\]/.test(value)) return false;
  return /path|file/i.test(key);
}

function walkPaths(obj, acc, tool) {
  if (!obj || typeof obj !== 'object') return;
  for (const [key, value] of Object.entries(obj)) {
    if (isRasterPath(key, value)) {
      if (!acc.some((item) => item.path === value)) {
        acc.push({ path: value, tool: tool || '', label: key.replace(/_/g, ' ') });
      }
    } else if (value && typeof value === 'object' && !Array.isArray(value)) {
      walkPaths(value, acc, tool);
    }
  }
}

export function collectRasterAssets(toolResults = []) {
  const acc = [];
  for (const entry of toolResults || []) {
    const tool = entry?.tool || '';
    if (String(tool).includes('weather')) continue;
    walkPaths(entry?.result || entry, acc, tool);
  }
  return acc;
}
