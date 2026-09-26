#!/usr/bin/env node
/**
 * SatQuery AI Auto-Refresh Dev Watcher
 *
 * - Watches frontend/src and frontend/index.html for any code changes.
 * - Rebuilds the frontend bundle using Vite in ~500ms.
 * - Synchronizes the built dist to the running Docker frontend container (satquery-main-frontend-1).
 * - Broadcasts a Server-Sent Events (SSE) 'reload' signal to all open browser tabs on port 35729.
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const { exec } = require('child_process');

const PORT = parseInt(process.env.AUTOREFRESH_PORT || '35729', 10);
const ROOT_DIR = path.resolve(__dirname, '..');
const FRONTEND_DIR = path.join(ROOT_DIR, 'frontend');
const SRC_DIR = path.join(FRONTEND_DIR, 'src');
const INDEX_HTML = path.join(FRONTEND_DIR, 'index.html');

const clients = new Set();
let isBuilding = false;
let pendingBuild = false;
let debounceTimer = null;

// 1. Lightweight SSE Server
const server = http.createServer((req, res) => {
  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', '*');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  const parsedUrl = new URL(req.url, `http://${req.headers.host || 'localhost'}`);

  if (parsedUrl.pathname === '/live-reload' || parsedUrl.pathname === '/__live_reload__') {
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      'Connection': 'keep-alive'
    });
    res.write(': connected\n\n');
    clients.add(res);
    console.log(`[AutoRefresh] Browser tab connected (${clients.size} active client${clients.size === 1 ? '' : 's'})`);

    req.on('close', () => {
      clients.delete(res);
      console.log(`[AutoRefresh] Browser tab disconnected (${clients.size} active client${clients.size === 1 ? '' : 's'})`);
    });
    return;
  }

  if (parsedUrl.pathname === '/trigger') {
    triggerRebuildAndReload('manual-trigger');
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'triggered', clients: clients.size }));
    return;
  }

  if (parsedUrl.pathname === '/health' || parsedUrl.pathname === '/ping') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', clients: clients.size }));
    return;
  }

  res.writeHead(404);
  res.end('Not Found');
});

// Periodic heartbeat to prevent idle connection closure
setInterval(() => {
  for (const client of clients) {
    try {
      client.write(': ping\n\n');
    } catch {
      clients.delete(client);
    }
  }
}, 15000);

// 2. Build & Reload Pipeline
function notifyReload() {
  if (clients.size === 0) {
    console.log('[AutoRefresh] Rebuilt dist (no browser tabs currently connected).');
    return;
  }
  console.log(`[AutoRefresh] Notifying ${clients.size} browser tab(s) to reload...`);
  for (const client of clients) {
    try {
      client.write('data: reload\n\n');
    } catch {
      clients.delete(client);
    }
  }
}

function triggerRebuildAndReload(changedFile) {
  if (isBuilding) {
    pendingBuild = true;
    return;
  }

  isBuilding = true;
  const start = Date.now();
  console.log(`\n[AutoRefresh] Change detected in ${changedFile || 'code'} — rebuilding frontend...`);

  exec('npm run build', { cwd: FRONTEND_DIR }, (err, stdout, stderr) => {
    isBuilding = false;
    if (err) {
      console.error('[AutoRefresh] Build failed:\n', stderr || err.message);
      if (pendingBuild) {
        pendingBuild = false;
        triggerRebuildAndReload('pending-retry');
      }
      return;
    }

    const duration = ((Date.now() - start) / 1000).toFixed(2);
    console.log(`[AutoRefresh] Build succeeded in ${duration}s.`);

    // Synchronize to running Docker frontend container if present
    exec('docker cp dist/. satquery-main-frontend-1:/usr/share/nginx/html/', { cwd: FRONTEND_DIR }, (cpErr) => {
      if (!cpErr) {
        console.log('[AutoRefresh] Synchronized dist to Docker container satquery-main-frontend-1.');
      }
      notifyReload();

      if (pendingBuild) {
        pendingBuild = false;
        setTimeout(() => triggerRebuildAndReload('queued-change'), 100);
      }
    });
  });
}

// 3. File Watcher
function onFileChange(eventType, filename) {
  if (!filename) return;
  // Ignore temporary files, git, node_modules, dist, etc.
  if (
    filename.includes('node_modules') ||
    filename.includes('.git') ||
    filename.includes('dist') ||
    filename.startsWith('.') ||
    filename.endsWith('~')
  ) {
    return;
  }

  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    triggerRebuildAndReload(filename);
  }, 200);
}

try {
  fs.watch(SRC_DIR, { recursive: true }, (event, filename) => {
    onFileChange(event, `src/${filename}`);
  });
  fs.watch(INDEX_HTML, (event) => {
    onFileChange(event, 'index.html');
  });
  console.log(`[AutoRefresh] Watching for code changes in:
  - ${SRC_DIR} (recursive)
  - ${INDEX_HTML}`);
} catch (err) {
  console.error('[AutoRefresh] Could not start fs.watch:', err.message);
}

server.listen(PORT, '0.0.0.0', () => {
  console.log(`[AutoRefresh] Dev live-reload server running at http://localhost:${PORT}/live-reload`);
  console.log('[AutoRefresh] Any frontend code edit will automatically rebuild and refresh your browser.');
});
