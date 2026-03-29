# UNICC AI Safety Council

Multi-expert AI safety evaluation for **UN / humanitarian** deployment contexts. Three virtual experts run in parallel, exchange **six directional critiques**, and a **rules-based arbitration layer** produces a structured **`CouncilReport`** (JSON) with a clear recommendation: **APPROVE**, **REVIEW**, or **REJECT**.

**Production stack:** `real_frontend/` (React) + `frontend_api/` (FastAPI, default **:8100**).  
**Static UI demo (no backend):** `mock_frontend/`.  
**Documentation:** [docs/system-overview.en.md](docs/system-overview.en.md) and [docs/README.md](docs/README.md).

On GitHub, the canonical readme is this file (English). For Chinese narrative in-repo, see [docs/system-overview.zh-CN.md](docs/system-overview.zh-CN.md). Optionally keep a personal `README.zh-CN.md` in the repo root; it is listed in `.gitignore` so it stays local and is not pushed.

---

## Features

| Layer | Role |
|--------|------|
| **Expert 1** | Security and adversarial testing: document analysis (Mode A) or full PROBE to BOUNDARY to ATTACK (Mode B) with an adapter. |
| **Expert 2** | Governance and compliance: EU AI Act, GDPR, NIST, UNESCO, etc., via agentic RAG over ChromaDB. |
| **Expert 3** | UN mission fit: UN Charter, humanitarian principles, UNESCO ethics, via agentic RAG. |
| **Council** | Six critiques plus non-LLM arbitration (conservative aggregation, consensus). |

**Model backends:** Anthropic **Claude** (dev/demo) or **vLLM + Llama 3 70B** (`council/slm_*.py`).

---

## Quick start: web UI and full council

```bash
# Terminal 1 - API
cd /path/to/Capstone
pip install -r frontend_api/requirements.txt
export ANTHROPIC_API_KEY=...
uvicorn frontend_api.main:app --reload --port 8100

# Terminal 2 - UI
cd real_frontend && npm install && npm run dev
```

Open the URL Vite prints (usually `http://localhost:5173`). Use **New Evaluation** to call `POST /evaluate/council`. **Final Report** can export Markdown.

**OpenAPI:** `http://localhost:8100/docs`

---

## Quick start: Expert 1 only

```bash
pip install -r api/requirements.txt
uvicorn api.main:app --reload --port 8000
```

`POST /evaluate/expert1-attack` — see `http://localhost:8000/docs`.

---

## Quick start: Python (no HTTP)

```python
from council.council_orchestrator import evaluate_agent

report = evaluate_agent(
    agent_id="demo-001",
    system_description="...",
    system_name="Demo",
    backend="claude",
)
print(report.incident_id)
```

---

## Repository layout (top level)

```text
Capstone/
├── council/           # Orchestrator, critiques, reports, storage, SLM helpers
├── Expert1/
├── Expert 2/          # + chroma_db_expert2/
├── Expert 3/          # + expert3_rag/
├── frontend_api/      # FastAPI: council, history, markdown
├── api/               # FastAPI: Expert 1 only (:8000)
├── real_frontend/
├── mock_frontend/
├── docs/
├── benchmark_*.py
├── benchmark_data/
└── UNICC-Project-2/
```

---

## Persistence

| Artifact | Path |
|----------|------|
| Full JSON | `council/reports/{incident_id}.json` |
| SQLite | `council/council.db` |
| JSONL index | `council/knowledge_index.jsonl` |

---

## `frontend_api` endpoints (:8100)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health |
| POST | `/evaluate/council` | Full pipeline + persist |
| POST | `/evaluate/expert1-attack` | Expert 1 only |
| GET | `/evaluations` | History |
| GET | `/evaluations/{incident_id}` | Report JSON |
| GET | `/evaluations/{incident_id}/markdown` | Markdown |

More: [frontend_api/README.md](frontend_api/README.md).

---

## Input (minimal)

- `agent_id`, `system_name`, `system_description` (long text; PDF/JSON/MD parsing in `real_frontend`).

Optional fields: purpose, deployment context, data access, risk indicators, backend, vLLM settings (see OpenAPI).

---

## Security

Use environment variables for keys (e.g. `ANTHROPIC_API_KEY`). Do not commit `.env`. `.gitignore` excludes secrets and `node_modules/`.

---

## Current limits

- No automatic **GitHub repo to system description** pipeline.  
- No **PDF** export in the UI (JSON + Markdown).  
- Vector search over `knowledge_index.jsonl` is future work.

---

## License

See [UNICC-Project-2/LICENSE](UNICC-Project-2/LICENSE) (MIT) unless another license applies in a subtree.
