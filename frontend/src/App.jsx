import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import AnalyzeView from './components/AnalyzeView';
import ResultsView from './components/ResultsView';
import ExecutionTraceView from './components/ExecutionTraceView';
import ModelsView from './components/ModelsView';
import AboutView from './components/AboutView';
import AuditReportModal from './components/AuditReportModal';
import { checkHealth, runSatelliteQuery } from './api/satqueryApi';
import { collectRasterAssets } from './api/rasters';
import { handleQueryResponse } from './api/handleQueryResponse';
import {
  applyIntent,
  createDefaultForm,
  formToQueryFields,
  inferIntentFromQuery,
  isAmbiguousVegetationQuery,
  missingMustFields,
  mustFieldMessage,
  widenDates
} from './state/intents';

function scrollToFields(fieldIds) {
  const first = fieldIds.find((id) => document.getElementById(`field-${id}`) || document.getElementById(id));
  const el = first
    ? (document.getElementById(`field-${first}`) || document.getElementById(first))
    : null;
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

export default function App() {
  const [currentView, setCurrentView] = useState('analyze');
  const [form, setForm] = useState(() => createDefaultForm());
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [handled, setHandled] = useState(null);
  const [highlightedFields, setHighlightedFields] = useState([]);
  const [clarifyReason, setClarifyReason] = useState('');
  const [formError, setFormError] = useState(null);
  const [ambiguousOpen, setAmbiguousOpen] = useState(false);
  const [forceChat, setForceChat] = useState(false);
  const [telemetry, setTelemetry] = useState({ totalTime: '—' });
  const [healthStatus, setHealthStatus] = useState(null);
  const [healthLatency, setHealthLatency] = useState(null);
  const [isReportOpen, setIsReportOpen] = useState(false);

  useEffect(() => {
    let isMounted = true;
    async function updateHealth() {
      const res = await checkHealth();
      if (isMounted) {
        setHealthStatus(res.ok);
        if (res.latency) setHealthLatency(res.latency);
      }
    }
    updateHealth();
    const interval = setInterval(updateHealth, 10000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  const applyHandled = (next, { stayOnAnalyze = false } = {}) => {
    setHandled(next);
    setForm((prev) => ({ ...prev, _lastTrace: next.executionTrace || [] }));
    if (next.kind === 'clarify') {
      setClarifyReason(next.copy?.message || next.plan?.reason || next.finalAnswer);
      setHighlightedFields(next.missingFields || []);
      setFormError(null);
      setCurrentView('analyze');
      setTimeout(() => scrollToFields(next.missingFields || ['bbox']), 50);
      return;
    }
    setClarifyReason('');
    setHighlightedFields([]);
    setFormError(null);
    if (next.kind === 'error' && stayOnAnalyze) {
      setFormError(next);
      setCurrentView('analyze');
      return;
    }
    if (next.kind === 'error' && (next.httpStatus === 400) && (next.missingFields || []).length) {
      setHighlightedFields(next.missingFields);
      setFormError(next);
      setCurrentView('analyze');
      setTimeout(() => scrollToFields(next.missingFields), 50);
      return;
    }
    setCurrentView('results');
  };

  const handleSelectIntent = (intentId) => {
    setAmbiguousOpen(false);
    setForceChat(false);
    setClarifyReason('');
    setHighlightedFields([]);
    setFormError(null);
    setForm((prev) => applyIntent(prev, intentId, { rewriteQuery: true }));
    setCurrentView('analyze');
  };

  const executeQuery = async (nextForm) => {
    const payloadForm = nextForm || form;
    if (!payloadForm.query.trim() || isRunning) return;

    setIsRunning(true);
    setFormError(null);
    const startTime = performance.now();

    try {
      const apiResult = await runSatelliteQuery(formToQueryFields(payloadForm));
      const elapsed = ((performance.now() - startTime) / 1000).toFixed(2);
      setTelemetry({ totalTime: `${elapsed}s` });

      const next = handleQueryResponse(apiResult);

      if (next.kind === 'error' && next.httpStatus === 500) {
        console.error('SatQuery 500', next.errors, next.body);
      }

      applyHandled(next);
    } finally {
      setIsRunning(false);
    }
  };

  const handleRunAnalysis = async () => {
    if (!form.query.trim() || isRunning) return;

    let working = { ...form };
    const inferred = inferIntentFromQuery(working.query);
    if (inferred && working.intent !== inferred) {
      working = applyIntent(working, inferred, { rewriteQuery: false });
      setForm(working);
    }

    if (!forceChat && isAmbiguousVegetationQuery(working.query)) {
      setAmbiguousOpen(true);
      setCurrentView('analyze');
      return;
    }

    if (working.intent) {
      const missing = missingMustFields(working);
      if (missing.length) {
        const message = mustFieldMessage(working);
        setClarifyReason(message);
        setHighlightedFields(missing);
        setFormError(null);
        setCurrentView('analyze');
        setTimeout(() => scrollToFields(missing), 50);
        return;
      }
    }

    await executeQuery(working);
  };

  const handleErrorAction = async (actionId) => {
    if (actionId === 'retry') {
      await executeQuery(form);
      return;
    }
    if (actionId === 'widen_dates') {
      const next = widenDates(form, 30);
      setForm(next);
      setCurrentView('analyze');
      setFormError(null);
      return;
    }
    if (String(actionId).startsWith('orbit:')) {
      const orbit_direction = String(actionId).split(':')[1];
      const next = { ...form, orbit_direction, intent: form.intent || 'sar' };
      setForm(next);
      await executeQuery(next);
    }
  };

  const handlePickVegetation = (choice) => {
    setAmbiguousOpen(false);
    setForceChat(false);
    setForm((prev) => applyIntent({ ...prev, query: choice.query }, choice.id, { rewriteQuery: true }));
  };

  return (
    <div className="satquery-app">
      <Navbar
        currentView={currentView}
        onSelectView={setCurrentView}
        healthStatus={healthStatus}
        healthLatency={healthLatency}
      />

      <main className="main-content">
        {currentView === 'analyze' && (
          <AnalyzeView
            form={form}
            onChangeForm={setForm}
            onSelectIntent={handleSelectIntent}
            onRunAnalysis={handleRunAnalysis}
            isRunning={isRunning}
            rasters={collectRasterAssets(handled?.toolResults)}
            clarify={clarifyReason}
            highlightedFields={highlightedFields}
            showAdvanced={showAdvanced}
            onToggleAdvanced={() => setShowAdvanced((v) => !v)}
            ambiguousOpen={ambiguousOpen}
            onPickVegetation={handlePickVegetation}
            onDismissAmbiguous={() => {
              setAmbiguousOpen(false);
              setForceChat(true);
              executeQuery({ ...form });
            }}
            errorOnForm={formError}
            onErrorAction={handleErrorAction}
          />
        )}

        {currentView === 'results' && (
          <ResultsView
            handled={handled}
            queryText={form.query}
            onNewAnalysis={() => setCurrentView('analyze')}
            onViewTrace={() => setCurrentView('trace')}
            onOpenReport={() => setIsReportOpen(true)}
            onSelectIntent={handleSelectIntent}
            onErrorAction={handleErrorAction}
            isRunning={isRunning}
          />
        )}

        {currentView === 'trace' && (
          <ExecutionTraceView
            handled={handled}
            telemetry={telemetry}
            onOpenReport={() => setIsReportOpen(true)}
          />
        )}

        {currentView === 'models' && <ModelsView />}

        {currentView === 'about' && <AboutView />}
      </main>

      <AuditReportModal
        isOpen={isReportOpen}
        onClose={() => setIsReportOpen(false)}
        queryText={form.query}
        handled={handled}
        form={form}
      />
    </div>
  );
}
