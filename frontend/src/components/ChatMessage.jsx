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

  const rawWebResults = (message.toolResults || [])
    .filter((t) => t.tool === 'fetch_web_intelligence' && t.result?.status === 'success')
    .map((t) => t.result);

  // Deduplicate web intelligence results by query or top URL signature
  const seenWebKeys = new Set();
  const webResults = [];
  for (const web of rawWebResults) {
    const key = (web.query || (web.results && web.results[0]?.url) || JSON.stringify(web)).trim().toLowerCase();
    if (!seenWebKeys.has(key)) {
      seenWebKeys.add(key);
      webResults.push(web);
    }
  }

  return (
    <div className="chat-row chat-row-assistant">
      <div className={`chat-bubble chat-bubble-assistant chat-status-${message.status || 'error'}`}>
        <p>{message.text}</p>

        {webResults.map((web, idx) => {
          const provider = (web.provider || 'web').toLowerCase();
          const isTavily = provider === 'tavily';
          const isFallback = !!web.fallback_triggered;

          return (
            <div key={idx} className="web-intelligence-card">
              <div className="web-provider-header">
                <span className={`web-provider-badge ${isTavily ? 'badge-tavily' : 'badge-ddg'}`}>
                  <span className="badge-dot" />
                  {isTavily ? 'Tavily Search' : isFallback ? 'DuckDuckGo (Fail-safe)' : 'DuckDuckGo Search'}
                </span>
                {web.results_count > 0 && (
                  <span className="web-results-count">{web.results_count} verified sources</span>
                )}
              </div>

              {web.results && web.results.length > 0 && (
                <div className="web-sources-list">
                  {web.results.slice(0, 4).map((source, sIdx) => (
                    <a
                      key={sIdx}
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                      className="web-source-pill"
                      title={source.content || source.title}
                    >
                      <span className="web-source-icon">🔗</span>
                      <span className="web-source-title">{source.title || source.url}</span>
                    </a>
                  ))}
                </div>
              )}
            </div>
          );
        })}

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
