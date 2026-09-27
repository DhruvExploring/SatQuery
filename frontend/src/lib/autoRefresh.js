/**
 * SatQuery AI Auto-Refresh Client
 * 
 * Listens for live-reload SSE events from scripts/dev-watcher.js (port 35729)
 * and refreshes the browser window automatically as soon as code changes.
 */

if (typeof window !== 'undefined') {
  (function initAutoRefresh() {
    // If standard Vite HMR is running (e.g. npm run dev), let Vite handle hot replacement
    if (import.meta.hot) {
      return;
    }

    const host = window.location.hostname || 'localhost';
    const endpoints = [
      '/live-reload',
      `http://${host}:35729/live-reload`
    ];
    let endpointIdx = 0;
    let eventSource = null;
    let retryTimeout = null;
    let failedAttempts = 0;
    const MAX_FAILED_ATTEMPTS = 3;

    function connect() {
      if (failedAttempts >= MAX_FAILED_ATTEMPTS) {
        // Dev watcher is not running; stop reconnecting to avoid console error spam
        return;
      }

      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }

      const sseUrl = endpoints[endpointIdx % endpoints.length];

      try {
        eventSource = new EventSource(sseUrl);

        eventSource.onopen = () => {
          failedAttempts = 0;
        };

        eventSource.onmessage = (event) => {
          if (event.data === 'reload') {
            window.location.reload();
          }
        };

        eventSource.onerror = () => {
          if (eventSource) {
            eventSource.close();
            eventSource = null;
          }
          failedAttempts++;
          endpointIdx++;
          clearTimeout(retryTimeout);
          if (failedAttempts < MAX_FAILED_ATTEMPTS) {
            retryTimeout = setTimeout(connect, 3000);
          }
        };
      } catch {
        failedAttempts++;
        endpointIdx++;
        clearTimeout(retryTimeout);
        if (failedAttempts < MAX_FAILED_ATTEMPTS) {
          retryTimeout = setTimeout(connect, 3000);
        }
      }
    }

    if (['localhost', '127.0.0.1'].includes(window.location.hostname)) {
      connect();
    }
  })();
}
