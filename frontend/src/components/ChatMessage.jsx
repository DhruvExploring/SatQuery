import React, { useState } from 'react';
import { collectRasterAssets, rasterDownloadUrl, rasterPreviewUrl } from '../api/rasters';
import { toolLabel } from '../lib/toolLabels';

const KNOWN_SECTIONS = [
  { key: 'observation', title: 'Observation', accent: 'sky' },
  { key: 'evidence', title: 'Evidence', accent: 'indigo' },
  { key: 'analysis', title: 'Analysis', accent: 'orange' },
  { key: 'confidence', title: 'Confidence', accent: 'emerald' },
  { key: 'summary', title: 'Summary', accent: 'slate' },
  { key: 'findings', title: 'Findings', accent: 'indigo' },
  { key: 'recommendation', title: 'Recommendation', accent: 'amber' }
];

function renderInlineMarkdown(text) {
  if (!text) return '';

  // Process bold: **text**
  const parts = [];
  const boldRegex = /\*\*(.*?)\*\*/g;
  let lastIndex = 0;
  let match;

  while ((match = boldRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    parts.push(<strong key={match.index}>{match[1]}</strong>);
    lastIndex = boldRegex.lastIndex;
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  // Next, map backticks to <code>
  return parts.map((part, pIdx) => {
    if (typeof part !== 'string') return part;
    if (!part.includes('`')) return part;

    const subParts = [];
    const codeRegex = /`([^`]+)`/g;
    let sLast = 0;
    let cMatch;
    while ((cMatch = codeRegex.exec(part)) !== null) {
      if (cMatch.index > sLast) {
        subParts.push(part.slice(sLast, cMatch.index));
      }
      subParts.push(<code key={`${pIdx}-${cMatch.index}`}>{cMatch[1]}</code>);
      sLast = codeRegex.lastIndex;
    }
    if (sLast < part.length) {
      subParts.push(part.slice(sLast));
    }
    return <React.Fragment key={pIdx}>{subParts}</React.Fragment>;
  });
}

function parseStructuredText(rawText) {
  if (!rawText) return [];

  // Match pattern like: (Observation|Evidence|Analysis|Confidence): or **Observation**:
  const sectionHeaderRegex = /(?:^|\n)(?:#{1,4}\s*|\*{0,2})(Observation|Evidence|Analysis|Confidence|Summary|Findings|Recommendation)(?:\*{0,2})[:\-—]\s*/i;

  if (!sectionHeaderRegex.test(rawText)) {
    // Return single standard block
    return [{ type: 'standard', title: null, content: rawText }];
  }

  const lines = rawText.split('\n');
  const sections = [];
  let currentSec = { type: 'standard', title: null, lines: [] };

  for (const line of lines) {
    const trimmed = line.trim();
    const match = trimmed.match(/^(?:#{1,4}\s*|\*{0,2})(Observation|Evidence|Analysis|Confidence|Summary|Findings|Recommendation)(?:\*{0,2})[:\-—]\s*(.*)$/i);

    if (match) {
      if (currentSec.lines.length > 0) {
        sections.push({
          type: currentSec.type,
          title: currentSec.title,
          content: currentSec.lines.join('\n').trim()
        });
      }

      const secName = match[1];
      const remainder = match[2];
      const known = KNOWN_SECTIONS.find((s) => s.key === secName.toLowerCase()) || {
        key: secName.toLowerCase(),
        title: secName,
        accent: 'slate'
      };

      currentSec = {
        type: known.key,
        title: known.title,
        accent: known.accent,
        lines: remainder ? [remainder] : []
      };
    } else {
      currentSec.lines.push(line);
    }
  }

  if (currentSec.lines.length > 0) {
    sections.push({
      type: currentSec.type,
      title: currentSec.title,
      accent: currentSec.accent,
      content: currentSec.lines.join('\n').trim()
    });
  }

  return sections.filter((s) => s.content || s.title);
}

function StructuredSection({ section }) {
  const paragraphs = section.content.split(/\n\s*\n/).filter(Boolean);

  return (
    <div className={`chat-section-block section-${section.accent || 'slate'}`}>
      {section.title && (
        <div className="section-head">
          <span className="section-title">{section.title}</span>
        </div>
      )}
      <div className="section-body">
        {paragraphs.map((p, pIdx) => {
          // Check for bullet list
          if (p.includes('\n- ') || p.startsWith('- ') || p.includes('\n* ') || p.startsWith('* ')) {
            const listItems = p.split(/\n[-*]\s+/).filter(Boolean);
            return (
              <ul key={pIdx} className="section-list">
                {listItems.map((item, i) => (
                  <li key={i}>{renderInlineMarkdown(item.trim())}</li>
                ))}
              </ul>
            );
          }
          return <p key={pIdx}>{renderInlineMarkdown(p)}</p>;
        })}
      </div>
    </div>
  );
}

export default function ChatMessage({ message, onOpenRaster }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    if (!message.text) return;
    navigator.clipboard?.writeText(message.text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (message.role === 'user') {
    // Strip any filenames or file tags that may have been concatenated
    const cleanText = (message.text || '')
      .replace(/\s*\|\s*(T[12]|File):.*$/i, '')
      .replace(/\n*Active:\s*.*$/i, '')
      .trim();

    return (
      <div className="chat-msg-row chat-user-row">
        <div className="chat-bubble user-bubble">
          <p className="user-query-text">{cleanText || message.text}</p>
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

  const sections = parseStructuredText(message.text);

  return (
    <div className="chat-msg-row chat-assistant-row">
      <div className={`chat-bubble assistant-bubble ${statusClass}`}>
        {/* Assistant Header */}
        <div className="assistant-bubble-head">
          <div className="assistant-meta-left">
            <span className="sat-agent-dot" />
            <span className="assistant-name">SatQuery Intelligence</span>
            <span className={`assistant-status-tag ${statusClass}`}>
              {message.status === 'success' || message.status === 'ok' ? 'Resolved' : message.status === 'clarify' ? 'Clarification' : 'Notice'}
            </span>
          </div>

          <button
            type="button"
            className="btn-copy-bubble"
            onClick={handleCopy}
            title="Copy response to clipboard"
          >
            {copied ? (
              <>
                <span className="copy-check">✓</span>
                <span>Copied</span>
              </>
            ) : (
              <>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
                <span>Copy</span>
              </>
            )}
          </button>
        </div>

        {/* Structured Body: Observation, Evidence, Analysis, Confidence */}
        <div className="assistant-bubble-body">
          {sections.map((sec, idx) => (
            <StructuredSection key={idx} section={sec} />
          ))}
        </div>

        {/* Executed Tools Strip */}
        {message.toolResults && message.toolResults.length > 0 && (
          <div className="executed-tools-strip">
            <span className="tools-strip-label">Tools Deployed:</span>
            <div className="tools-badges-wrap">
              {message.toolResults.map((t, i) => (
                <span key={i} className="tool-micro-pill" title={t.tool}>
                  <span className="tool-pill-dot" />
                  {toolLabel(t.tool)}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Generated Raster Previews Gallery */}
        {rasters.length > 0 && (
          <div className="generated-rasters-tray">
            <span className="tray-label">Generated Raster Products:</span>
            <div className="rasters-grid">
              {rasters.map((r) => (
                <div
                  key={r.path}
                  className="raster-preview-card"
                  onClick={() => onOpenRaster && onOpenRaster(r)}
                  title="Click to inspect in high resolution modal"
                >
                  <div className="preview-img-container">
                    <img src={rasterPreviewUrl(r.path, 512)} alt={r.label} />
                    <span className="preview-zoom-badge">Inspect</span>
                  </div>
                  <div className="preview-meta-row">
                    <span className="preview-label" title={r.label}>{r.label}</span>
                    <a
                      href={rasterDownloadUrl(r.path)}
                      target="_blank"
                      rel="noreferrer"
                      className="btn-download-raster"
                      onClick={(e) => e.stopPropagation()}
                      download
                    >
                      GeoTIFF
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
