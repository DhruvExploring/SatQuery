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
      `http://${host}:35729/live-reload`,
      '/live-reload'
    ];
    let endpointIdx = 0;
    let eventSource = null;
    let retryTimeout = null;

    function connect() {
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }

      const sseUrl = endpoints[endpointIdx % endpoints.length];

      try {
        eventSource = new EventSource(sseUrl);

        eventSource.onopen = () => {
          console.log('[AutoRefresh] Connected to live-reload stream at', sseUrl);
        };

        eventSource.onmessage = (event) => {
          if (event.data === 'reload') {
            console.log('[AutoRefresh] Code change detected! Auto-refreshing web app...');
            window.location.reload();
          }
        };

        eventSource.onerror = () => {
          if (eventSource) {
            eventSource.close();
            eventSource = null;
          }
          // Rotate endpoint on error and retry in 2.5s
          endpointIdx++;
          clearTimeout(retryTimeout);
          retryTimeout = setTimeout(connect, 2500);
        };
      } catch (err) {
        endpointIdx++;
        clearTimeout(retryTimeout);
        retryTimeout = setTimeout(connect, 2500);
      }
    }

    connect();
  })();
}
