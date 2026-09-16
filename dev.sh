#!/usr/bin/env bash
# Run the SatQuery backend (FastAPI/uvicorn) and frontend (Vite) together.
#
# Usage: ./dev.sh
# Logs stream live in this terminal (prefixed [backend]/[frontend]) and are
# also written to logs/backend.log and logs/frontend.log for later review.
# Ctrl+C stops both servers.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

mkdir -p logs
: > logs/backend.log
: > logs/frontend.log

if [ ! -d .venv ]; then
  echo "No .venv found — creating one and installing backend dependencies..."
  python3 -m venv .venv
  ./.venv/bin/pip install -r requirements.txt
fi

if [ ! -d frontend/node_modules ]; then
  echo "frontend/node_modules missing — running npm install..."
  (cd frontend && npm install)
fi

if [ ! -f .env ]; then
  echo "No .env found — copying .env.example. Fill in real credentials before using live tools." >&2
  cp .env.example .env
fi

PIDS=()

cleanup() {
  echo ""
  echo "Stopping backend/frontend..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

./.venv/bin/python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000 \
  >> logs/backend.log 2>&1 &
PIDS+=($!)

(cd frontend && npm run dev) >> logs/frontend.log 2>&1 &
PIDS+=($!)

echo "Backend:  http://127.0.0.1:8000  (docs at /docs, log: logs/backend.log)"
echo "Frontend: http://localhost:3000  (log: logs/frontend.log)"
echo "Press Ctrl+C to stop both. Tailing logs below..."
echo ""

tail -n +1 -f logs/backend.log logs/frontend.log &
PIDS+=($!)

wait "${PIDS[0]}" "${PIDS[1]}"
