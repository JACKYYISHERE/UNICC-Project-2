# UNICC AI Safety Council

Multi-expert AI safety evaluation for **UN / humanitarian** deployment contexts. Three virtual experts run in parallel, exchange **six directional critiques**, and a **rules-based arbitration layer** produces a structured **`CouncilReport`** (JSON) with a clear recommendation: **APPROVE**, **REVIEW**, or **REJECT**.

**Production stack:** `real_frontend/` (React + Vite) + `frontend_api/` (FastAPI, default **:8100**).  
**Static UI (no backend):** `mock_frontend/`.  
**Long-form docs:** [docs/system-overview.en.md](docs/system-overview.en.md) · Chinese: [docs/system-overview.zh-CN.md](docs/system-overview.zh-CN.md).

Root `README.zh-CN.md` is optional and **gitignored** for a personal local copy; GitHub shows this English file only.

---

## What runs in one evaluation

1. Build an **`AgentSubmission`** from `agent_id`, `system_name`, `system_description`, and optional metadata (`purpose`, `deployment_context`, `data_access`, `risk_indicators`, etc.).
2. **`CouncilOrchestrator`** runs **Expert 1 / 2 / 3** concurrently (each returns a block under `expert_reports`).
3. Six **directed critiques** are generated (e.g. governance on security); results live under `critiques`.
4. **Arbitration** (pure Python rules, no extra LLM call) sets `council_decision` (final recommendation, consensus, oversight flags) and a human-readable `council_note`.
5. **`persist_report()`** writes the full JSON file, upserts **SQLite**, and appends a row to the **JSONL** knowledge index.

Reference JSON shape: `council/test_output_refugeeassist.json` (example full run).

---

## Expert roles (detail)

| Expert | Code entry (typical) | Output keys in `expert_reports` |
|--------|----------------------|-----------------------------------|
| **Security** | `Expert1/expert1_module.py`, `expert1_router.py` | `security` — scores, `risk_tier`, `recommendation`, `key_findings`, optional `council_handoff` |
| **Governance** | `Expert 2/expert2_agent.py` + `Expert 2/chroma_db_expert2/` | `governance` — compliance dimensions, `key_gaps`, citations, `recommendation` |
| **UN mission fit** | `Expert 3/expert3_agent.py` + `Expert 3/expert3_rag/` | `un_mission_fit` — dimension scores, violations, `recommendation` |

Expert 1 **Mode A** (doc analysis): retrieves relevant MITRE ATLAS techniques via RAG, derives dimension scores **deterministically** from a pre-computed lookup table (`Expert1/atlas_dimension_scores.json` — tactic × maturity × attack-layer mapping), then calls LLM only to write rationale. Scores are fully traceable to specific ATLAS technique IDs.  **Mode B**: live **PROBE → BOUNDARY → ATTACK** adversarial testing when an adapter targets a real system (`Expert1/adapters/`).

---

## Core data shapes (integrators)

**Request body (HTTP / internal)** — minimal fields:

- `agent_id` (string, stable id)
- `system_name` (display)
- `system_description` (long text; main evaluation input)

**`CouncilReport` (response)** — fields you will render or store:

- `incident_id` — generated id for storage (e.g. `inc_YYYYMMDD_agent_suffix`)
- `agent_id`, `session_id`, `timestamp`
- `expert_reports` — dict with `security`, `governance`, `un_mission_fit`
- `critiques` — six directed critique objects
- `council_decision` — `final_recommendation`, `consensus_level`, rationale, flags
- `council_note` — short narrative summary

Dataclass definitions: `council/council_report.py`, submission: `council/agent_submission.py`.

---

## Persistence (what gets written)

| Layer | Location | Purpose |
|--------|-----------|---------|
| Full report | `council/reports/{incident_id}.json` | Lossless archive |
| SQLite | `council/council.db`, table `evaluations` | List/detail APIs, dashboard history |
| Index | `council/knowledge_index.jsonl` | Per-run `summary_core` + `raw` dict for future embeddings / similarity |

Writer: `council/storage.py` (`persist_report`).

---

## HTTP APIs

### `frontend_api` (recommended, port **8100**)

| Method | Path | Notes |
|--------|------|--------|
| GET | `/health` | Liveness |
| POST | `/evaluate/council` | Full pipeline + persist |
| POST | `/evaluate/expert1-attack` | Expert 1 only (same suite) |
| GET | `/evaluations` | `limit`, `offset` query params |
| GET | `/evaluations/{incident_id}` | Full `CouncilReport` JSON |
| GET | `/evaluations/{incident_id}/markdown` | Server-generated Markdown |
| GET | `/knowledge/index` | Recent JSONL records |
| GET | `/knowledge/search` | Text search over summaries / ids |

Implementation: `frontend_api/main.py`. Runbook: [frontend_api/README.md](frontend_api/README.md). **CORS** is open for local UI dev.

### `api` (Expert 1 only, port **8000**)

- `POST /evaluate/expert1-attack` with `mode` **A** or **B**, `backend` `claude` or `mock`, etc.
- Entry: `api/main.py`. Dependencies: `api/requirements.txt`.

---

## Production frontend (`real_frontend`)

- **API base URL:** `VITE_API_URL` or default `http://localhost:8100` (`src/api/client.ts`).
- **Submit full council:** `submitCouncilEvaluation` → `POST /evaluate/council` (`src/pages/NewEvaluation.tsx`).
- **Map API JSON to UI:** `src/utils/mapCouncilReport.ts` (`councilReportToDetailedEvaluation`).
- **Upload description:** PDF / JSON / Markdown → text via `src/utils/parseAgentDoc.ts`.
- **Markdown download:** `src/utils/reportToMarkdown.ts`, **Final Report** page.

**`mock_frontend`:** same visual flow; `NewEvaluation` uses a timer and `src/data/mockData.ts` — **no** HTTP.

---

## Python-only invocation

```python
from council.council_orchestrator import evaluate_agent

report = evaluate_agent(
    agent_id="demo-001",
    system_description="Long natural-language description of the AI system under review.",
    system_name="Demo",
    backend="claude",  # or "vllm" with slm config
)
# report.to_json() or fields on report.council_decision
```

Orchestrator: `council/council_orchestrator.py`. Critique generation: `council/critique.py`. SLM bridge: `council/slm_backends.py`, `council/slm_experts.py`.

---

## Environment and backends

### Backend server (`frontend_api` / `council`)

| Variable | Role |
|----------|------|
| `ANTHROPIC_API_KEY` | Claude API key; required when `backend=claude` |
| — | When using `backend=vllm`, pass `vllm_base_url` and `vllm_model` in the request body (or set defaults in `council_orchestrator`) |

### Frontend (`real_frontend`) — copy `real_frontend/.env.example` to `real_frontend/.env.local`

| Variable | Default | Role |
|----------|---------|------|
| `VITE_API_URL` | `http://localhost:8100` | `frontend_api` base URL |
| `VITE_COUNCIL_BACKEND` | `claude` | Pre-select backend in the UI (`claude` or `vllm`) |
| `VITE_VLLM_BASE_URL` | `http://127.0.0.1:8000` | vLLM inference server URL (UI default when vllm selected) |
| `VITE_VLLM_MODEL` | `meta-llama/Meta-Llama-3-70B-Instruct` | Model name passed to vLLM |

Do **not** commit `.env` / `.env.local`. Root `.gitignore` covers `.env*`, `node_modules/`, `__pycache__/`, etc. The `.env.example` files are intentionally tracked.

---

## Run commands (copy-paste)

**Full stack (UI + council API):**

```bash
cd /path/to/Capstone
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r frontend_api/requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn frontend_api.main:app --reload --port 8100
```

```bash
cd real_frontend && npm install && npm run dev
```

**Expert 1 API only:**

```bash
pip install -r api/requirements.txt
uvicorn api.main:app --reload --port 8000
```

**Static demo:**

```bash
cd mock_frontend && npm install && npm run dev
```

---

## Key files by subsystem (not exhaustive)

```
council/
├── agent_submission.py       # AgentSubmission
├── council_orchestrator.py   # evaluate_agent, CouncilOrchestrator
├── council_report.py         # CouncilReport, CouncilDecision, CritiqueResult
├── critique.py               # six directional critiques
├── storage.py                # JSON + SQLite + JSONL
├── slm_backends.py           # vLLM client
└── slm_experts.py            # Expert 2/3 on SLM

frontend_api/
├── main.py                   # all :8100 routes
└── requirements.txt

real_frontend/
├── src/App.tsx
├── src/api/client.ts
├── src/utils/mapCouncilReport.ts
├── src/utils/parseAgentDoc.ts
└── src/pages/*.tsx
```

Large or generated artifacts (e.g. Chroma sqlite under `Expert 2/chroma_db_expert2/`) may be present locally; keep them out of git if you add patterns — current policy is in `.gitignore` at repo root.

---

## Benchmarks and secondary trees

- Root `benchmark_*.py` and `benchmark_data/` support annotation / evaluation workflows (see script docstrings).
- `UNICC-Project-2/` holds an additional copy of council/experts/training assets and subproject docs; align changes with root `council/` when you maintain both.

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| UI cannot load dashboard | `frontend_api` on **8100**, `GET /health`, browser console / CORS |
| `evaluate/council` hangs | Model latency; watch server logs; ensure API key or vLLM is reachable |
| Empty expert sections | Mapper expects keys `security` / `governance` / `un_mission_fit`; compare response to `test_output_refugeeassist.json` |
| Chroma / RAG errors | Expert 2/3 DB paths built under `Expert 2/chroma_db_expert2/`, `Expert 3/expert3_rag/` |

---

## Known limitations

- No automated **“clone GitHub repo → system_description”** pipeline.
- No **PDF** export in the web UI (JSON + Markdown available).
- Vector retrieval over `knowledge_index.jsonl` is not wired into the default UI yet.

---

## License

See [UNICC-Project-2/LICENSE](UNICC-Project-2/LICENSE) (MIT) unless another license applies in a subtree.
