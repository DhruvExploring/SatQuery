import React from 'react';
import AoiPanel from './AoiPanel';
import QueryForm from './QueryForm';
import LiveTrace from './LiveTrace';
import { INTENTS, VEGETATION_CHOICES } from '../state/intents';

export default function AnalyzeView({
  form,
  onChangeForm,
  onSelectIntent,
  onRunAnalysis,
  isRunning,
  rasters = [],
  clarify,
  highlightedFields,
  showAdvanced,
  onToggleAdvanced,
  ambiguousOpen,
  onPickVegetation,
  onDismissAmbiguous,
  errorOnForm,
  onErrorAction
}) {
  const handleKeyDown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      onRunAnalysis();
    }
  };

  return (
    <div className="view-page active" id="view-analyze">
      <div className="page-header">
        <div className="page-title-group">
          <div className="page-icon-badge">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="2" y1="12" x2="22" y2="12"></line>
              <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
            </svg>
          </div>
          <div>
            <h1 className="page-title">Satellite <span>Earth Analysis</span></h1>
            <p className="page-subtitle">One endpoint — POST /api/v1/query — with a progressive form per intent</p>
          </div>
        </div>
      </div>

      <div className="dashboard-grid-analyze">
        <AoiPanel
          form={form}
          onChange={onChangeForm}
          highlightedFields={highlightedFields}
          rasters={rasters}
          isRunning={isRunning}
        />

        <div className="card query-panel">
          <div className="tab-nav">
            <button type="button" className="tab-btn active">
              Query Console
            </button>
          </div>

          <div className="tab-content-container">
            <div className="prompt-box-card">
              <div className="prompt-header">
                <span>NATURAL LANGUAGE QUERY</span>
              </div>
              <textarea
                id="query-input"
                className="prompt-textarea"
                rows="3"
                placeholder="Ask SatQuery… e.g. Fetch Sentinel-2 optical imagery, Compute NDVI, Assess flood inundation impact"
                value={form.query}
                onChange={(e) => onChangeForm({ ...form, query: e.target.value })}
                onKeyDown={handleKeyDown}
              />
              <div className="prompt-footer">
                <span className="char-counter">{form.query.length} characters</span>
                <button
                  type="button"
                  className="btn-send"
                  onClick={onRunAnalysis}
                  title="Run Analysis"
                  disabled={isRunning || !form.query.trim()}
                >
                  {isRunning ? '⏳' : '➤'}
                </button>
              </div>
            </div>

            <div className="example-queries-section">
              <div className="section-label"><span>INTENT CHIPS</span></div>
              <div className="example-chips-wrap">
                {INTENTS.map((chip) => (
                  <button
                    key={chip.id}
                    type="button"
                    className={`example-chip ${form.intent === chip.id ? 'active' : ''}`}
                    onClick={() => onSelectIntent(chip.id)}
                  >
                    {chip.label}
                  </button>
                ))}
              </div>
            </div>

            {ambiguousOpen && (
              <div className="clarify-banner" id="ambiguous-vegetation">
                <strong>Did you mean something more specific?</strong>
                <p>
                  “Vegetation” alone is a chat/capability reply on the backend — it will not compute indices.
                  Choose a target and we will rewrite the query before calling POST /api/v1/query.
                </p>
                <div className="example-chips-wrap" style={{ marginTop: '0.6rem' }}>
                  {VEGETATION_CHOICES.map((choice) => (
                    <button
                      key={choice.id}
                      type="button"
                      className="example-chip"
                      onClick={() => onPickVegetation(choice)}
                    >
                      {choice.label}
                    </button>
                  ))}
                  <button type="button" className="example-chip" onClick={onDismissAmbiguous}>
                    Send as chat
                  </button>
                </div>
              </div>
            )}

            {clarify && (
              <div className="clarify-banner" id="clarify-banner">
                <strong>A few more inputs are needed</strong>
                <p>{clarify}</p>
                <span className="form-hint">This is a form completion prompt, not a failed request. Your query text is kept.</span>
              </div>
            )}

            {errorOnForm && (
              <div className={`error-banner http-${errorOnForm.httpStatus || 400}`}>
                <strong>{errorOnForm.copy?.title}</strong>
                <p>{errorOnForm.copy?.message}</p>
                {errorOnForm.copy?.actions?.length > 0 && (
                  <div className="example-chips-wrap" style={{ marginTop: '0.5rem' }}>
                    {errorOnForm.copy.actions.map((action) => (
                      <button
                        key={action.id}
                        type="button"
                        className="example-chip"
                        onClick={() => onErrorAction(action.id)}
                      >
                        {action.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            <QueryForm
              form={form}
              onChange={onChangeForm}
              highlightedFields={highlightedFields}
              showAdvanced={showAdvanced}
              onToggleAdvanced={onToggleAdvanced}
            />

            <button
              type="button"
              className="btn-primary-action"
              id="btn-run-analysis"
              onClick={onRunAnalysis}
              disabled={isRunning || !form.query.trim()}
            >
              {isRunning ? 'Running LangGraph pipeline…' : 'Run Analysis ➔'}
            </button>

            {(isRunning || (form._lastTrace && form._lastTrace.length > 0)) && (
              <div className="form-section">
                <div className="section-label"><span>EXECUTION TRACE</span></div>
                <LiveTrace isRunning={isRunning} executionTrace={form._lastTrace || []} />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
