#!/usr/bin/env bash
# Start the UNICC Council backend
# Setup:  pip install -r requirements.txt
# Run:    bash start.sh
#
# LLM backend is auto-selected at request time (no restart needed):
#   - vLLM   if running at http://localhost:8000  (set by caller, e.g. dgx_setup.sh)
#   - Claude if ANTHROPIC_API_KEY is set
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "[start] Starting UNICC Council backend on port 8100..."
cd "$ROOT/frontend_api"
exec uvicorn main:app --host 0.0.0.0 --port 8100
