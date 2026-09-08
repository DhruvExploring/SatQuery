/**
 * Raster preview/download URLs for GeoTIFF paths returned by POST /api/v1/query.
 */

const API_BASE = (typeof window !== 'undefined' && window.location.port && window.location.port !== '8000')
  ? 'http://localhost:8000'
  : '';

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

function isRasterPath(key, value) {
  if (typeof value !== 'string' || !value.trim()) return false;
  if (!/\.(tif|tiff|png|jpg|jpeg|webp)$/i.test(value)) return false;
  return /path|file/i.test(key) || /\.(tif|tiff)$/i.test(value);
}

function walkPaths(obj, acc, tool) {
  if (!obj || typeof obj !== 'object') return;
  for (const [key, value] of Object.entries(obj)) {
    if (isRasterPath(key, value)) {
      const path = value;
      if (!acc.some((item) => item.path === path)) {
        acc.push({
          key,
          path,
          tool: tool || '',
          label: key.replace(/_/g, ' '),
          name: String(path).split(/[/\\]/).pop()
        });
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
    const data = entry?.result?.data;
    if (data && typeof data === 'object') walkPaths(data, acc, tool);
  }
  return acc;
}

export function hasImageryTool(toolResults = []) {
  return collectRasterAssets(toolResults).length > 0;
}
