import React from 'react';
import { collectRasterAssets, rasterDownloadUrl, rasterPreviewUrl } from '../api/rasters';

export default function ChatMessage({ message }) {
  if (message.role === 'user') {
    return (
      <div className="chat-row chat-row-user">
        <div className="chat-bubble chat-bubble-user">
          <p>{message.text}</p>
          {message.attachmentNote && <div className="chat-attachment-note">{message.attachmentNote}</div>}
        </div>
      </div>
    );
  }

  const rasters = collectRasterAssets(message.toolResults);

  return (
    <div className="chat-row chat-row-assistant">
      <div className={`chat-bubble chat-bubble-assistant chat-status-${message.status || 'error'}`}>
        <p>{message.text}</p>

        {rasters.length > 0 && (
          <div className="raster-gallery">
            {rasters.map((r) => (
              <a
                key={r.path}
                className="raster-thumb"
                href={rasterDownloadUrl(r.path)}
                target="_blank"
                rel="noreferrer"
                title={`${r.label} — click to download`}
              >
                <img src={rasterPreviewUrl(r.path, 512)} alt={r.label} />
                <span>{r.label}</span>
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
