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

# Force UTF-8 output encoding so build scripts with Unicode chars work on
# Windows (default GBK) and other non-UTF-8 locales.
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

# ── Step 1: Pre-download embedding model ─────────────────────────────────────
echo "[start] Warming up sentence-transformers model cache…"
python3 -c "
from sentence_transformers import SentenceTransformer
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
print('[start] Model cache ready.')
" || echo "[start] WARNING: sentence-transformers warmup failed — will retry at runtime."

# ── Step 2: Pre-build all three Expert RAG indexes ───────────────────────────
echo "[start] Checking / building Expert RAG indexes…"
python3 - "$ROOT" << 'PYEOF'
import sys, importlib.util
from pathlib import Path

root = Path(sys.argv[1])

configs = [
    {
        "label":  "Expert 1 (ATLAS)",
        "db":     root / "Expert1" / "rag" / "chroma_db_expert1",
        "collection": "expert1_attack_techniques",
        "script": root / "Expert1" / "rag" / "build_rag_expert1.py",
        "mod_name": "build_rag_expert1",
    },
    {
        "label":  "Expert 2 (Regulatory)",
        "db":     root / "Expert 2" / "chroma_db_expert2",
        "collection": "expert2_legal_compliance",
        "script": root / "Expert 2" / "build_rag_expert2.py",
        "mod_name": "build_rag_expert2",
    },
    {
        "label":  "Expert 3 (UN Principles)",
        "db":     root / "Expert 3" / "expert3_rag" / "chroma_db",
        "collection": "expert3_un_context",
        "script": root / "Expert 3" / "expert3_rag" / "build_rag.py",
        "mod_name": "build_rag_expert3",
    },
]

for cfg in configs:
    label, db, col_name, script, mod_name = (
        cfg["label"], cfg["db"], cfg["collection"], cfg["script"], cfg["mod_name"]
    )

    # Check if rebuild needed
    needs_build = False
    if not db.exists() or not (db / "chroma.sqlite3").exists():
        needs_build = True
    else:
        try:
            import chromadb
            c = chromadb.PersistentClient(path=str(db))
            names = [col.name for col in c.list_collections()]
            if col_name not in names:
                needs_build = True
        except Exception:
            needs_build = True

    if not needs_build:
        print(f"[start]   {label}: index OK — skipping rebuild")
        continue

    print(f"[start]   {label}: building RAG index (first-time setup, ~1-2 min)…")
    try:
        spec = importlib.util.spec_from_file_location(mod_name, str(script))
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.build()
        print(f"[start]   {label}: done ✓")
    except Exception as e:
        print(f"[start]   {label}: WARNING — build failed: {e}")
        print(f"[start]   You can rebuild manually: python3 {script}")
PYEOF

echo "[start] Starting UNICC Council backend on port 8100..."
# Load API keys from Expert1/.env if present
[ -f "$ROOT/Expert1/.env" ] && source "$ROOT/Expert1/.env"
cd "$ROOT/frontend_api"
exec uvicorn main:app --host 0.0.0.0 --port 8100
