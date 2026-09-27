import React from 'react';
import { rasterPreviewUrl } from '../api/rasters';

/**
 * Image History Toggle for SatQuery Vision frontend.
 *
 * Displays:
 * 1. Compact toggle: [ Original Image ] [ Generated Image ]
 * 2. Selectable tabs/thumbnails progression strip: Original → SAR → Optical → NDVI → etc.
 * 3. Badge label indicator: ORIGINAL, GENERATED · SAR, GENERATED · NDVI, etc.
 */
export default function ImageHistoryToggle({
  imageHistory = [],
  activeImageId = null,
  onSelectImage,
  onRemoveImage,
  disabled = false
}) {
  if (!imageHistory || imageHistory.length === 0) {
    return null;
  }

  const originalItem = imageHistory.find((item) => item.type === 'original');
  const generatedItems = imageHistory.filter((item) => item.type === 'generated');
  const activeItem = imageHistory.find((item) => item.id === activeImageId) || imageHistory[0];

  const isOriginalActive = activeItem?.type === 'original';
  const isGeneratedActive = activeItem?.type === 'generated';

  const handleSelectOriginal = () => {
    if (disabled || !originalItem) return;
    onSelectImage?.(originalItem.id);
  };

  const handleSelectGeneratedGroup = () => {
    if (disabled || generatedItems.length === 0) return;
    if (isGeneratedActive) return;
    // Switch to the latest generated item
    const target = generatedItems[generatedItems.length - 1];
    onSelectImage?.(target.id);
  };

  const getToolBadgeCode = (item) => {
    if (item.type === 'original') return 'ORIG';
    const cat = (item.category || item.shortLabel || '').toUpperCase();
    if (cat.includes('SAR')) return 'SAR';
    if (cat.includes('NDVI') || cat.includes('VEGETATION')) return 'NDVI';
    if (cat.includes('OPTICAL')) return 'OPT';
    if (cat.includes('MULTISPECTRAL')) return 'MS';
    if (cat.includes('CHANGE') || cat.includes('DIFF') || cat.includes('MASK')) return 'DIFF';
    if (cat.includes('WILDFIRE')) return 'FIRE';
    if (cat.includes('FLOOD')) return 'FLD';
    return (item.shortLabel || 'RAST').slice(0, 4).toUpperCase();
  };

  return (
    <div className="sat-history-toggle-container">
      {/* Top Segment: Compact [ Original Image ] [ Generated Image ] Toggle */}
      <div className="sat-history-top-bar">
        <div className="sat-history-group-toggle">
          {originalItem ? (
            <button
              type="button"
              className={`history-toggle-btn ${isOriginalActive ? 'active' : ''}`}
              onClick={handleSelectOriginal}
              disabled={disabled}
              title={`View Original Image: ${originalItem.filename || 'Uploaded TIFF'}`}
            >
              <span className="btn-text">Original Image</span>
              <span className="history-count-badge">1</span>
            </button>
          ) : (
            <button
              type="button"
              className="history-toggle-btn disabled-empty"
              disabled
              title="No original upload in session"
            >
              <span className="btn-text">Original Image</span>
            </button>
          )}

          {generatedItems.length > 0 ? (
            <button
              type="button"
              className={`history-toggle-btn ${isGeneratedActive ? 'active' : ''}`}
              onClick={handleSelectGeneratedGroup}
              disabled={disabled}
              title={`View Generated Imagery (${generatedItems.length} available)`}
            >
              <span className="btn-text">
                {generatedItems.length === 1 ? 'Generated Image' : 'Generated Products'}
              </span>
              <span className="history-count-badge">{generatedItems.length}</span>
            </button>
          ) : (
            <button
              type="button"
              className="history-toggle-btn disabled-empty"
              disabled
              title="No generated imagery yet. Run an analysis or index calculation to generate."
            >
              <span className="btn-text">Generated Image</span>
            </button>
          )}
        </div>

        {/* Current Active Image Badge Label */}
        {activeItem && (
          <div className="sat-active-badge-wrap">
            <span
              className={`active-badge ${
                activeItem.type === 'original'
                  ? 'badge-original'
                  : `badge-generated badge-${(activeItem.category || 'raster').toLowerCase().replace(/\s+/g, '-')}`
              }`}
            >
              <span className="badge-dot" />
              {activeItem.badgeLabel || (activeItem.type === 'original' ? 'ORIGINAL' : 'GENERATED')}
            </span>
          </div>
        )}
      </div>

      {/* Selectable Tabs / Thumbnails Progression Strip: Original → SAR → Optical → NDVI */}
      {imageHistory.length > 1 && (
        <div className="sat-history-strip" role="tablist" aria-label="Satellite Image History">
          {imageHistory.map((item, index) => {
            const isSelected = item.id === activeImageId;
            const isLast = index === imageHistory.length - 1;

            return (
              <React.Fragment key={item.id}>
                <div
                  className={`sat-history-card-tab ${isSelected ? 'selected' : ''}`}
                  onClick={() => !disabled && onSelectImage?.(item.id)}
                  role="tab"
                  aria-selected={isSelected}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onSelectImage?.(item.id);
                    }
                  }}
                  title={`${item.badgeLabel || item.shortLabel} — ${item.filename || item.filePath}`}
                >
                  {/* Thumbnail / Icon preview */}
                  <div className="history-thumb-box">
                    {item.filePath ? (
                      <img
                        src={rasterPreviewUrl(item.filePath, 96)}
                        alt={item.shortLabel}
                        className="history-thumb-img"
                        onError={(e) => {
                          e.target.style.display = 'none';
                        }}
                      />
                    ) : null}
                    <span className="history-thumb-icon">{getToolBadgeCode(item)}</span>
                  </div>

                  {/* Text details */}
                  <div className="history-card-info">
                    <span className="history-card-label">{item.shortLabel || item.category}</span>
                    <span className="history-card-sub" title={item.filename}>
                      {item.filename || 'GeoTIFF'}
                    </span>
                  </div>

                  {/* Remove Button for individual image */}
                  <button
                    type="button"
                    className="history-card-close"
                    onClick={(e) => {
                      e.stopPropagation();
                      onRemoveImage?.(item.id, e);
                    }}
                    title={`Remove ${item.shortLabel} from session`}
                    aria-label={`Remove ${item.shortLabel}`}
                  >
                    ×
                  </button>
                </div>

                {!isLast && <span className="history-arrow-divider">→</span>}
              </React.Fragment>
            );
          })}
        </div>
      )}
    </div>
  );
}
