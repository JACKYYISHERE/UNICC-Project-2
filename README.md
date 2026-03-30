# UNICC AI Safety Council

> **Multi-expert AI safety evaluation framework for UN and humanitarian deployment contexts.**  
> Submit any AI system description → receive a structured APPROVE / REVIEW / REJECT verdict backed by traceable evidence from MITRE ATLAS, EU AI Act, GDPR, NIST AI RMF, and UN mission alignment principles.

---

## The Problem

Deploying AI systems in humanitarian and UN contexts carries unique risks: biased decisions affecting vulnerable populations, regulatory exposure across multiple jurisdictions (EU AI Act, GDPR, UN Human Rights guidance), adversarial threats specific to high-stakes operational environments, and no standardised pre-deployment vetting process.

Existing AI safety tools either focus on a single dimension (security *or* compliance *or* ethics) or produce generic outputs with no traceable evidence. There is no purpose-built council that can simultaneously assess all three perspectives and arbitrate between them.

---

## What This System Does

The UNICC AI Safety Council runs **three specialised expert agents in parallel**, each grounded in its own knowledge base, then generates **six directed cross-critiques** between them. A **pure Python rules-based arbitration layer** (no additional LLM call) synthesises a final `CouncilReport` with:

- A clear three-way verdict: **APPROVE · REVIEW · REJECT**
- Per-expert dimension scores with traceable citations
- Structured audit findings (Risk → Evidence → Impact → Score Rationale)
- Consensus level and mandatory human-oversight flags

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Submission Layer                          │
│  GitHub URL / PDF / Markdown / JSON  →  system_description      │
│                  POST /analyze/repo  →  /evaluate/council        │
└───────────────────────────┬─────────────────────────────────────┘
                            │  AgentSubmission
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CouncilOrchestrator                           │
│        (council/council_orchestrator.py)  — Round 1             │
│                                                                  │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │   Expert 1       │  │   Expert 2        │  │   Expert 3    │  │
│  │   Security &     │  │   Governance &    │  │   UN Mission  │  │
│  │   Adversarial    │  │   Regulatory      │  │   Fit &       │  │
│  │   Robustness     │  │   Compliance      │  │   Human Rights│  │
│  │                  │  │                   │  │               │  │
│  │ MITRE ATLAS RAG  │  │  ChromaDB RAG     │  │  Custom RAG   │  │
│  │ atlas_dimension  │  │  EU AI Act        │  │  UN mandate   │  │
│  │ _scores.json     │  │  GDPR, NIST,      │  │  UNGP, UNESCO │  │
│  │ (deterministic)  │  │  OWASP, UNESCO    │  │               │  │
│  └────────┬─────────┘  └────────┬──────────┘  └───────┬───────┘  │
│           │                     │                      │          │
│           └─────────────────────┴──────────────────────┘          │
│                                 │  expert_reports                  │
│                            Round 2: 6 directed cross-critiques     │
│        (gov→sec, sec→gov, mission→sec, sec→mission,               │
│         mission→gov, gov→mission)                                  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│              Rules-Based Arbitration  (no LLM)                   │
│   final_recommendation · consensus_level · oversight_flags       │
│                       council_note                               │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Persistence Layer                           │
│  council/reports/{incident_id}.json  (full archive)             │
│  council/council.db  (SQLite — dashboard / API)                 │
│  council/knowledge_index.jsonl  (per-run summary + embeddings)  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Features

### Expert 1 — Security & Adversarial Robustness

- **RAG-grounded, deterministic scoring**: retrieves relevant MITRE ATLAS techniques from ChromaDB, maps them to 7 dimensions via a pre-computed lookup table (`Expert1/atlas_dimension_scores.json` — tactic × maturity × attack-layer). Scores are fully traceable to ATLAS technique IDs; the LLM is invoked **only** to write rationale.
- **Structured audit findings** per finding:
  - **Risk** — specific threat to this system
  - **Evidence** — ATLAS ID + named architectural weakness
  - **Impact** — what an attacker could achieve concretely
  - **Score Rationale** — why this dimension received this score
- **Mode B** (optional): live PROBE → BOUNDARY → ATTACK adversarial test suite against a running target system via pluggable adapters.

### Expert 2 — Governance & Regulatory Compliance

- Agentic multi-round RAG over a regulatory corpus (EU AI Act, GDPR, NIST AI RMF, OWASP LLM Top 10, UNESCO, UN Human Rights).
- Rates 9 compliance dimensions: PASS / FAIL / UNCLEAR — never guesses; UNCLEAR ≠ PASS.
- Findings use audit-standard language: *"No evidence of X has been identified"* (not absolute assertions).
- EU AI Act high-risk articles (Art. 9/13/17/31) carry automatic *"(if classified as high-risk)"* qualifiers to prevent over-claiming.
- Every gap ends with **Impact:** explaining the deployment consequence.
- NIST findings → *alignment gap*; OWASP findings → *exposure / vulnerability*.

### Expert 3 — UN Mission Fit & Human Rights

- RAG over UN mandate documents, UNGP principles, and mission-specific guidance.
- Scores technical risk, ethical risk, legal risk, and societal risk.
- Flags humanitarian-context violations (conflict zones, refugee data, vulnerable populations).

### Cross-Expert Critique Round

Six directed critiques surface blind spots across expert domains. Each critique includes: `agrees`, `divergence_type`, `key_point`, `stance`, and `evidence_references`.

### Rules-Based Arbitration

Pure Python — no additional LLM call. Produces:

| Field | Values |
|-------|--------|
| `final_recommendation` | APPROVE · REVIEW · REJECT |
| `consensus_level` | FULL · PARTIAL · SPLIT |
| `human_oversight_required` | bool |
| `compliance_blocks_deployment` | bool |

---

## Pain Points Solved

| Problem | How we address it |
|---------|-------------------|
| Single-dimension tools miss cross-cutting risks | Three independent experts covering security, law, and ethics simultaneously |
| "Black box" AI safety scores — no evidence trail | Every score traced to ATLAS technique ID, regulation article, or UN principle |
| LLM hallucination in compliance findings | Expert 2 retrieves article text before making any claim; never cites what it didn't retrieve |
| Generic findings not specific to the system under review | Expert 1 binds each finding to a concrete architectural weakness in the submitted description |
| Inconsistent pre-deployment standards across teams | Standardised `CouncilReport` schema with incident IDs, SQLite history, and JSONL index |
| No structured inter-expert disagreement process | Six directed critiques + arbitration consensus score model |

---

## Quick Start

### Requirements

- Python 3.10+
- Node.js 18+
- One of: `ANTHROPIC_API_KEY` (Claude) **or** a running vLLM server

### Run

```bash
# 1. Clone and install
git clone https://github.com/JACKYYISHERE/UNICC-Project-2.git
cd UNICC-Project-2
pip install -r requirements.txt

# 2. Set API key (skip if using vLLM)
export ANTHROPIC_API_KEY=sk-ant-...

# 3. Start backend
bash start.sh          # → http://localhost:8100

# 4. Start frontend (separate terminal)
cd real_frontend && npm install && npm run dev   # → http://localhost:5173
```

### Evaluate a GitHub repo from the command line

```bash
python3 run_batch_eval.py --backend claude
```

### Python API

```python
from council.council_orchestrator import evaluate_agent

report = evaluate_agent(
    agent_id="demo-001",
    system_name="Demo",
    system_description="<long description of the AI system>",
    backend="claude",   # or "vllm"
)
print(report.council_decision.final_recommendation)  # APPROVE / REVIEW / REJECT
```

---

## HTTP API Reference

Base URL: `http://localhost:8100`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| POST | `/analyze/repo` | Extract system description from a GitHub URL |
| POST | `/evaluate/council` | Full three-expert evaluation + persist |
| GET | `/evaluations` | List past evaluations (`limit`, `offset`) |
| GET | `/evaluations/{incident_id}` | Full `CouncilReport` JSON |
| GET | `/evaluations/{incident_id}/markdown` | Report as Markdown download |
| GET | `/audit/recent` | Live pipeline events (used by frontend log panel) |
| GET | `/knowledge/stats` | RAG knowledge base document counts |

---

## CouncilReport Shape

```jsonc
{
  "incident_id": "inc_20260330_system-name_a1b2c3",
  "agent_id": "system-name",
  "timestamp": "2026-03-30T...",
  "expert_reports": {
    "security":      { "dimension_scores": {...}, "key_findings": [...], "recommendation": "REVIEW" },
    "governance":    { "compliance_findings": {...}, "key_gaps": [...], "recommendation": "REJECT" },
    "un_mission_fit":{ "dimension_scores": {...}, "key_findings": [...], "recommendation": "REVIEW" }
  },
  "critiques": { "gov_on_sec": {...}, "sec_on_gov": {...}, ... },  // 6 entries
  "council_decision": {
    "final_recommendation": "REVIEW",
    "consensus_level": "PARTIAL",
    "human_oversight_required": true,
    "compliance_blocks_deployment": false
  },
  "council_note": "..."
}
```

---

## Repository Structure

```
Capstone/
├── council/                     # Core orchestration
│   ├── council_orchestrator.py  # evaluate_agent(), CouncilOrchestrator
│   ├── council_report.py        # CouncilReport dataclasses
│   ├── critique.py              # 6-critique generation
│   ├── storage.py               # JSON + SQLite + JSONL persistence
│   └── reports/                 # Per-run JSON archives
│
├── Expert1/                     # Security expert
│   ├── expert1_router.py        # Mode A (RAG) + Mode B (attack)
│   ├── atlas_dimension_scores.json  # Pre-computed ATLAS → dimension scores
│   └── rag/                     # ChromaDB for ATLAS techniques
│
├── Expert 2/                    # Governance expert
│   ├── expert2_agent.py         # Agentic RAG compliance assessor
│   └── chroma_db_expert2/       # Regulatory corpus (EU AI Act, GDPR, …)
│
├── Expert 3/                    # UN Mission Fit expert
│   ├── expert3_agent.py
│   └── expert3_rag/             # UN mandate / UNGP corpus
│
├── frontend_api/                # FastAPI backend (:8100)
│   └── main.py
│
├── real_frontend/               # React + Vite UI (:5173)
│   └── src/
│       ├── pages/               # Dashboard, NewEvaluation, ExpertAnalysis, …
│       ├── api/client.ts
│       └── utils/mapCouncilReport.ts
│
├── run_batch_eval.py            # CLI: evaluate multiple GitHub repos
├── dgx_setup.sh                 # GPU server deployment helper
├── start.sh                     # Simple backend entry point
└── docs/
    ├── system-overview.en.md
    └── system-overview.zh-CN.md
```

---

## Environment Variables

### Backend

| Variable | Required | Notes |
|----------|----------|-------|
| `ANTHROPIC_API_KEY` | If using Claude | Falls back automatically if vLLM unreachable |

### Frontend (`real_frontend/.env.local`)

| Variable | Default | Notes |
|----------|---------|-------|
| `VITE_API_URL` | `http://localhost:8100` | Backend base URL |
| `VITE_COUNCIL_BACKEND` | `claude` | `claude` or `vllm` |
| `VITE_VLLM_BASE_URL` | `http://127.0.0.1:8000` | vLLM server when backend=vllm |
| `VITE_VLLM_MODEL` | `meta-llama/Meta-Llama-3-70B-Instruct` | Model name |

Copy `real_frontend/.env.example` → `real_frontend/.env.local` to get started.

---

## Docs

- [System Overview (English)](docs/system-overview.en.md)
- [系统概览（中文）](docs/system-overview.zh-CN.md)

---

## License

MIT — see [UNICC-Project-2/LICENSE](UNICC-Project-2/LICENSE).
