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

# Pre-download the sentence-transformers embedding model so all three Expert
# RAG auto-rebuilds use the local cache instead of downloading mid-evaluation.
echo "[start] Warming up sentence-transformers model cache…"
python3 -c "
from sentence_transformers import SentenceTransformer
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
print('[start] Model cache ready.')
" || echo "[start] WARNING: sentence-transformers warmup failed — RAG rebuild will attempt download at runtime."

echo "[start] Starting UNICC Council backend on port 8100..."
cd "$ROOT/frontend_api"
exec uvicorn main:app --host 0.0.0.0 --port 8100
