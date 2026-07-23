#!/usr/bin/env bash
# One-shot setup: install the CLI + build the web UI.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Installing the Python CLI (issue) ..."
if command -v uv >/dev/null 2>&1; then
  uv pip install -e .
else
  python3 -m pip install -e .
fi

echo "==> Building the web frontend ..."
if command -v npm >/dev/null 2>&1; then
  (cd frontend && npm install && npm run build)
  echo "==> Web UI built. Run 'issue serve' and open http://127.0.0.1:8000"
else
  echo "!! npm not found — skipping frontend build."
  echo "   The CLI works without it; install Node and run 'cd frontend && npm run build' for the web UI."
fi

echo "==> Done. Try:  issue add \"My first issue\" && issue list"
