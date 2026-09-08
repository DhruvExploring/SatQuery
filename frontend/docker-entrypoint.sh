#!/bin/sh
# Runs automatically at container start (nginx's official image executes every
# executable script in /docker-entrypoint.d/ before starting nginx). Writes the
# API endpoint into a small runtime-loaded file so it can change per deployment
# without rebuilding the image — Vite env vars are baked in at build time and
# can't do this on their own.
set -eu

cat <<EOF > /usr/share/nginx/html/env-config.js
window.__SATQUERY_CONFIG__ = {
  API_BASE_URL: "${API_BASE_URL:-}"
};
EOF
