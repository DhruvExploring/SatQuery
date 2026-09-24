import React, { useEffect, useRef, useState } from 'react';
import { rasterPreviewUrl, uploadRasterFile } from '../api/rasters';
import { formatBbox, roiBoxToBbox } from '../lib/geo';
import { inspectGeotiff } from '../lib/inspectGeotiff';

const clamp01 = (v) => Math.min(1, Math.max(0, v));

/**
 * One image upload+preview slot: file picker, server-side upload, a rendered
 * preview with a draggable region-of-interest box, and a quiet background
 * inspect_geotiff_metadata call (for the info chip and for converting the
 * drawn box into real coordinates).
 *
 * `onChange` receives a *patch* (merged onto the latest state by the parent
 * via functional setState) rather than a full replacement object -- an
 * earlier version spread the `slot` prop directly, which is a stale closure
 * across an `await`: a second update after the upload finished would revert
 * whatever the first update (before the upload started) had just cleared.
 * `onReset` fully clears the slot (a patch/merge can't remove keys).
 */
export default function ImageSlot({ label, slot, onChange, onReset, disabled }) {
  const fileInputRef = useRef(null);
  const imgWrapRef = useRef(null);
  const uploadTokenRef = useRef(0);
  const [dragStart, setDragStart] = useState(null);
  const [dragCurrent, setDragCurrent] = useState(null);
  const [imgFailed, setImgFailed] = useState(false);

  useEffect(() => {
    setImgFailed(false);
  }, [slot.uploadedPath]);

  const handleFilePick = async (e) => {
    const picked = e.target.files?.[0] || null;
    e.target.value = '';
    if (!picked) return;
    if (!/\.(tif|tiff)$/i.test(picked.name)) {
      onChange({ error: 'Only .tif/.tiff files are accepted.' });
      return;
    }

    const myToken = ++uploadTokenRef.current;
    onChange({
      uploading: true,
      error: null,
      uploadedPath: null,
      originalFilename: picked.name,
      boundsWgs84: null,
      info: null,
      roi: null,
      modelBbox: null,
      modelPolygon: null,
      knowledgeBase: null
    });

    const uploaded = await uploadRasterFile(picked);
    if (myToken !== uploadTokenRef.current) return; // a newer pick superseded this one

    if (!uploaded.ok) {
      onChange({ uploading: false, error: uploaded.error });
      return;
    }

    onChange({
      uploading: false,
      uploadedPath: uploaded.path,
      originalFilename: picked.name,
      knowledgeBase: uploaded.knowledgeBase
    });
    runInspection(uploaded.path, myToken);
  };

  const runInspection = async (path, myToken) => {
    onChange({ inspecting: true });
    const patch = await inspectGeotiff(path);
    if (myToken !== uploadTokenRef.current) return; // superseded while this was in flight
    onChange({ inspecting: false, ...(patch || {}) });
  };

  const clearSlot = () => {
    uploadTokenRef.current += 1; // discard any in-flight upload/inspection for the old file
    onReset();
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const fracFromEvent = (e) => {
    const rect = imgWrapRef.current.getBoundingClientRect();
    return {
      x: clamp01((e.clientX - rect.left) / rect.width),
      y: clamp01((e.clientY - rect.top) / rect.height)
    };
  };

  const handlePointerDown = (e) => {
    if (!slot.uploadedPath || disabled) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture?.(e.pointerId);
    const point = fracFromEvent(e);
    setDragStart(point);
    setDragCurrent(point);
  };

  const handlePointerMove = (e) => {
    if (!dragStart) return;
    setDragCurrent(fracFromEvent(e));
  };

  const finishDrag = () => {
    if (!dragStart || !dragCurrent) return;
    const x = Math.min(dragStart.x, dragCurrent.x);
    const y = Math.min(dragStart.y, dragCurrent.y);
    const w = Math.abs(dragCurrent.x - dragStart.x);
    const h = Math.abs(dragCurrent.y - dragStart.y);
    setDragStart(null);
    setDragCurrent(null);
    if (w < 0.02 || h < 0.02) return; // treat as an accidental click, not a real box
    onChange({ roi: { x, y, w, h } });
  };

  const liveBox = dragStart && dragCurrent
    ? {
        x: Math.min(dragStart.x, dragCurrent.x),
        y: Math.min(dragStart.y, dragCurrent.y),
        w: Math.abs(dragCurrent.x - dragStart.x),
        h: Math.abs(dragCurrent.y - dragStart.y)
      }
    : slot.roi;

  const roiBbox = slot.roi && slot.boundsWgs84 ? roiBoxToBbox(slot.roi, slot.boundsWgs84) : null;

  return (
    <div className="image-slot">
      <div className="image-slot-head">
        <span className="image-slot-label">{label}</span>
        {slot.uploadedPath && (
          <button type="button" className="btn-link" onClick={clearSlot} disabled={disabled}>
            Remove
          </button>
        )}
      </div>

      {!slot.uploadedPath ? (
        <label className="image-drop">
          <input
            ref={fileInputRef}
            type="file"
            accept=".tif,.tiff"
            onChange={handleFilePick}
            disabled={disabled || slot.uploading}
            hidden
          />
          {slot.uploading ? 'Uploading…' : 'Click to choose a .tif / .tiff file'}
        </label>
      ) : (
        <div className="image-preview-wrap">
          <div
            className="image-preview"
            ref={imgWrapRef}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={finishDrag}
            onPointerLeave={finishDrag}
          >
            {!imgFailed && (
              <img
                src={rasterPreviewUrl(slot.uploadedPath, 640)}
                alt={slot.originalFilename}
                draggable={false}
                onError={() => setImgFailed(true)}
              />
            )}
            {imgFailed && <div className="image-preview-failed">Could not load a preview for this file.</div>}
            {liveBox && (
              <div
                className="roi-box"
                style={{
                  left: `${liveBox.x * 100}%`,
                  top: `${liveBox.y * 100}%`,
                  width: `${liveBox.w * 100}%`,
                  height: `${liveBox.h * 100}%`
                }}
              />
            )}
            {slot.modelPolygon ? (
              <>
                <svg className="model-polygon" viewBox="0 0 100 100" preserveAspectRatio="none">
                  <polygon points={slot.modelPolygon.map(([x, y]) => `${x * 100},${y * 100}`).join(' ')} />
                </svg>
                <div
                  className="model-polygon-anchor"
                  style={{
                    left: `${Math.min(...slot.modelPolygon.map((p) => p[0])) * 100}%`,
                    top: `${Math.min(...slot.modelPolygon.map((p) => p[1])) * 100}%`
                  }}
                >
                  <span className="model-bbox-tag">AI</span>
                </div>
              </>
            ) : (
              slot.modelBbox && (
                <div
                  className="model-bbox"
                  style={{
                    left: `${slot.modelBbox[0] * 100}%`,
                    top: `${slot.modelBbox[1] * 100}%`,
                    width: `${(slot.modelBbox[2] - slot.modelBbox[0]) * 100}%`,
                    height: `${(slot.modelBbox[3] - slot.modelBbox[1]) * 100}%`
                  }}
                >
                  <span className="model-bbox-tag">AI</span>
                </div>
              )
            )}
          </div>
          <div className="image-preview-hint">Drag on the image to mark the region you're asking about.</div>
          {slot.roi && (
            <div className="roi-readout">
              <span>{roiBbox ? `Region: ${formatBbox(roiBbox)}` : 'Region marked'}</span>
              <button type="button" className="btn-link" onClick={() => onChange({ roi: null })} disabled={disabled}>
                Clear region
              </button>
            </div>
          )}
          {(slot.modelPolygon || slot.modelBbox) && (
            <div className="roi-readout">
              <span>
                {slot.modelPolygon
                  ? "AI traced a region's path in its answer (rough estimate, not precise)"
                  : 'AI marked a region in its answer (rough estimate, not precise)'}
              </span>
              <button
                type="button"
                className="btn-link"
                onClick={() => onChange({ modelBbox: null, modelPolygon: null })}
                disabled={disabled}
              >
                Clear
              </button>
            </div>
          )}
        </div>
      )}

      {slot.error && <div className="image-slot-error">{slot.error}</div>}

      {slot.info && (
        <div className="tool-badge tool-badge-success tool-badge-quiet">
          GeoTIFF inspection ✓ · {slot.info.width}×{slot.info.height} · {slot.info.bandCount} band(s) ·{' '}
          {slot.info.crs} · {slot.info.georeferenced ? 'georeferenced' : 'not georeferenced'}
          {slot.info.pixelSizeWgs84Degrees && (
            <>
              {' '}
              · {slot.info.pixelSizeWgs84Degrees.lon_per_pixel.toExponential(3)}°lon/px,{' '}
              {slot.info.pixelSizeWgs84Degrees.lat_per_pixel.toExponential(3)}°lat/px
            </>
          )}
        </div>
      )}
      {slot.inspecting && <div className="tool-badge tool-badge-pending tool-badge-quiet">Inspecting GeoTIFF…</div>}
    </div>
  );
}
