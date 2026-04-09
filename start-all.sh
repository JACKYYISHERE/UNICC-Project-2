#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# UNICC AI Safety Council — unified launcher
# Starts backend (port 8100) + frontend dev server (port 5173) in one command.
#
# Usage:
#   bash start-all.sh
#
# Prerequisites (first run only):
#   pip install -r requirements.txt
#   cd real_frontend && npm install && cd ..
#
# Environment:
#   export ANTHROPIC_API_KEY=sk-ant-...   (required for Claude backend)
#   export MOCK_MODE=1                    (optional — skips LLM calls)
# ─────────────────────────────────────────────────────────────────────────────
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── Dependency check ──────────────────────────────────────────────────────────
if ! command -v uvicorn &>/dev/null; then
  echo "[start-all] ERROR: uvicorn not found. Run: pip install -r requirements.txt"
  exit 1
fi
if [ ! -d "$ROOT/real_frontend/node_modules" ]; then
  echo "[start-all] node_modules missing — running npm install..."
  cd "$ROOT/real_frontend" && npm install --silent
  cd "$ROOT"
fi

# ── API Key check ─────────────────────────────────────────────────────────────
if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ "${MOCK_MODE:-0}" != "1" ]; then
  echo "[start-all] ERROR: ANTHROPIC_API_KEY is not set."
  echo "  Run:  export ANTHROPIC_API_KEY=sk-ant-..."
  echo "  Or:   MOCK_MODE=1 bash start-all.sh   (skips LLM calls)"
  exit 1
fi

# ── Ports ─────────────────────────────────────────────────────────────────────
BACKEND_PORT=8100
FRONTEND_PORT=5173

# ── Cleanup on exit ──────────────────────────────────────────────────────────
cleanup() {
  echo ""
  echo "[start-all] Shutting down..."
  kill "$BACKEND_PID" 2>/dev/null || true
  kill "$FRONTEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" 2>/dev/null || true
  wait "$FRONTEND_PID" 2>/dev/null || true
  echo "[start-all] Done."
}
trap cleanup INT TERM EXIT

# ── Start backend ─────────────────────────────────────────────────────────────
echo "[start-all] Starting backend  → http://localhost:$BACKEND_PORT"
cd "$ROOT/frontend_api"
uvicorn main:app --host 0.0.0.0 --port "$BACKEND_PORT" &
BACKEND_PID=$!
cd "$ROOT"

# ── Wait for backend ready ────────────────────────────────────────────────────
printf "[start-all] Waiting for backend"
for i in $(seq 1 20); do
  sleep 1
  if curl -sf "http://localhost:$BACKEND_PORT/health" &>/dev/null; then
    echo " ✓"
    break
  fi
  printf "."
  if [ "$i" -eq 20 ]; then
    echo ""
    echo "[start-all] ERROR: backend did not start within 20 s"
    exit 1
  fi
done

# ── Start frontend ────────────────────────────────────────────────────────────
echo "[start-all] Starting frontend → http://localhost:$FRONTEND_PORT"
cd "$ROOT/real_frontend"
npm run dev -- --port "$FRONTEND_PORT" &
FRONTEND_PID=$!
cd "$ROOT"

echo ""
echo "  ✓ UNICC AI Safety Council is running"
echo ""
printf "    %-12s http://localhost:%s\n"      "Backend"  "$BACKEND_PORT"
printf "    %-12s http://localhost:%s\n"      "Frontend" "$FRONTEND_PORT"
printf "    %-12s http://localhost:%s/docs\n" "API docs" "$BACKEND_PORT"
echo ""
echo "  Press Ctrl+C to stop both servers."
echo ""

# ── Keep alive ───────────────────────────────────────────────────────────────
wait "$BACKEND_PID" "$FRONTEND_PID"
