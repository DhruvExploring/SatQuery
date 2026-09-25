import React from 'react';
import { collectRasterAssets, rasterDownloadUrl, rasterPreviewUrl } from '../api/rasters';
import { toolLabel } from '../lib/toolLabels';

export default function ChatMessage({ message, onOpenRaster }) {
  if (message.role === 'user') {
    return (
      <div className="chat-row chat-row-user">
        <div className="chat-bubble chat-bubble-user">
          <div className="bubble-header-user">
            <span className="user-avatar">👤</span>
            <span className="bubble-author">You</span>
          </div>
          <p className="chat-text">{message.text}</p>
          {message.attachmentNote && (
            <div className="chat-attachment-note">
              <span className="attach-icon">📎</span>
              <span>{message.attachmentNote}</span>
            </div>
          )}
        </div>
      </div>
    );
  }

  const rasters = collectRasterAssets(message.toolResults);
  const statusClass = message.status === 'success' || message.status === 'ok'
    ? 'status-success'
    : message.status === 'clarify'
      ? 'status-clarify'
      : 'status-error';

  return (
    <div className="chat-row chat-row-assistant">
      <div className={`chat-bubble chat-bubble-assistant ${statusClass}`}>
        <div className="bubble-header-assistant">
          <div className="assistant-identity">
            <span className="assistant-avatar">🛰️</span>
            <span className="bubble-author">SatQuery Intelligence Agent</span>
          </div>
          <span className={`status-badge-inline ${statusClass}`}>
            {message.status === 'success' || message.status === 'ok' ? 'Resolved' : message.status === 'clarify' ? 'Clarification' : 'Notice'}
          </span>
        </div>

        <div className="chat-answer-body">
          <p className="chat-text">{message.text}</p>
        </div>

        {/* Display executed tool results badges */}
        {message.toolResults && message.toolResults.length > 0 && (
          <div className="tools-executed-strip">
            <span className="strip-title">Tools Deployed:</span>
            <div className="tools-pill-group">
              {message.toolResults.map((t, i) => (
                <span key={i} className="tool-executed-pill" title={t.tool}>
                  <span className="tool-dot" />
                  {toolLabel(t.tool)}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Generated Raster Previews Gallery */}
        {rasters.length > 0 && (
          <div className="raster-gallery-section">
            <span className="gallery-title">Generated Satellite Rasters & Products:</span>
            <div className="raster-gallery">
              {rasters.map((r) => (
                <div
                  key={r.path}
                  className="raster-thumb-card"
                  onClick={() => onOpenRaster && onOpenRaster(r)}
                >
                  <div className="thumb-img-wrap">
                    <img src={rasterPreviewUrl(r.path, 512)} alt={r.label} />
                    <span className="thumb-zoom-tag">Click to Inspect</span>
                  </div>
                  <div className="thumb-meta">
                    <span className="thumb-label">{r.label}</span>
                    <a
                      href={rasterDownloadUrl(r.path)}
                      target="_blank"
                      rel="noreferrer"
                      className="thumb-download-link"
                      onClick={(e) => e.stopPropagation()}
                      download
                    >
                      GeoTIFF ⤓
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
