from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from council.audit import (
    list_events as audit_list_events,
    list_spans as audit_list_spans,
    log_event as audit_log_event,
)

COUNCIL_DIR = BASE_DIR / "council"
DB_PATH = COUNCIL_DIR / "council.db"
REPORTS_DIR = COUNCIL_DIR / "reports"
INDEX_PATH = COUNCIL_DIR / "knowledge_index.jsonl"
EXPERT1_DIR = BASE_DIR / "Expert1"


def _ensure_serializable(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return _ensure_serializable(asdict(obj))
    if isinstance(obj, dict):
        return {k: _ensure_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_ensure_serializable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    return str(obj)


def _load_report_json(incident_id: str) -> dict:
    p = REPORTS_DIR / f"{incident_id}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Report not found: {incident_id}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read report JSON: {e}")


def _report_to_markdown(r: dict) -> str:
    cd = r.get("council_decision") or {}
    lines: list[str] = []
    lines.append("# UNICC AI Safety Council Report")
    lines.append("")
    lines.append("## Metadata")
    lines.append("")
    lines.append(f"- **Incident ID:** {r.get('incident_id', '')}")
    lines.append(f"- **Agent ID:** {r.get('agent_id', '')}")
    lines.append(f"- **Session ID:** {r.get('session_id', '')}")
    lines.append(f"- **Timestamp:** {r.get('timestamp', '')}")
    lines.append("")
    lines.append("## Final Decision")
    lines.append("")
    lines.append(f"- **Recommendation:** {cd.get('final_recommendation', '')}")
    lines.append(f"- **Consensus:** {cd.get('consensus_level', '')}")
    lines.append(f"- **Human Oversight Required:** {cd.get('human_oversight_required', '')}")
    lines.append(f"- **Compliance Blocks Deployment:** {cd.get('compliance_blocks_deployment', '')}")
    lines.append("")
    lines.append("### Rationale")
    lines.append("")
    lines.append(str(cd.get("rationale", "")).strip())
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Expert Reports")
    lines.append("")
    for key, val in (r.get("expert_reports") or {}).items():
        lines.append(f"### {key}")
        lines.append("")
        lines.append(f"- recommendation: {val.get('recommendation', '')}")
        key_findings = val.get("key_findings") or []
        if key_findings:
            lines.append("- key_findings:")
            for f in key_findings[:10]:
                lines.append(f"  - {f}")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Directional Critiques")
    lines.append("")
    for ckey, cval in (r.get("critiques") or {}).items():
        lines.append(f"### {ckey}")
        lines.append("")
        lines.append(f"- from_expert: {cval.get('from_expert', '')}")
        lines.append(f"- on_expert: {cval.get('on_expert', '')}")
        lines.append(f"- agrees: {cval.get('agrees', '')}")
        lines.append(f"- key_point: {cval.get('key_point', '')}")
        lines.append(f"- stance: {cval.get('stance', '')}")
        ev = cval.get("evidence_references") or []
        if ev:
            lines.append("- evidence_references:")
            for e in ev[:10]:
                lines.append(f"  - {e}")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Council Note")
    lines.append("")
    lines.append(str(r.get("council_note", "")).strip())
    return "\n".join(lines)


app = FastAPI(
    title="UNICC Frontend API Suite",
    description="All frontend-callable APIs in one folder for designers/developers.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Expert1AttackRequest(BaseModel):
    agent_id: str = Field(..., description="Unique ID, e.g. refugee-assist-v2")
    system_name: str = Field("", description="Display name")
    system_description: str = Field(..., description="Description for evaluation")
    purpose: str = Field("", description="Optional purpose")
    deployment_context: str = Field("", description="Optional deployment context")
    data_access: list[str] = Field(default_factory=list)
    risk_indicators: list[str] = Field(default_factory=list)
    mode: str = Field("B", description="A=document analysis, B=active attack")
    mock_level: str = Field("medium", description="low|medium|high for MockAdapter in Mode B")
    backend: str = Field("claude", description="claude|mock")


class CouncilEvaluateRequest(BaseModel):
    agent_id: str
    system_name: str = ""
    system_description: str
    purpose: str = ""
    deployment_context: str = ""
    data_access: list[str] = Field(default_factory=list)
    risk_indicators: list[str] = Field(default_factory=list)
    backend: str = Field("claude", description="claude|vllm")
    vllm_base_url: str = "http://localhost:8000"
    vllm_model: str = "meta-llama/Meta-Llama-3-70B-Instruct"


class RepoAnalyzeRequest(BaseModel):
    source: str = Field(
        ...,
        description="GitHub URL (https://github.com/owner/repo) or absolute local path",
    )
    backend: str = Field("claude", description="claude|vllm — LLM used to generate the description")
    vllm_base_url: str = "http://localhost:8000"
    vllm_model: str = "meta-llama/Meta-Llama-3-70B-Instruct"
    github_token: str = Field("", description="Optional GitHub PAT for private repos")


def _run_expert1_attack(req: Expert1AttackRequest) -> dict:
    if str(EXPERT1_DIR) not in sys.path:
        sys.path.insert(0, str(EXPERT1_DIR))
    from expert1_module import run_full_evaluation
    from expert1_router import AgentProfile, ClaudeBackend, MockLLMBackend
    from adapters.mock_adapter import MockAdapter

    profile = AgentProfile(
        agent_id=req.agent_id,
        name=req.system_name or req.agent_id,
        description=req.system_description,
        purpose=req.purpose or "",
        deployment_context=req.deployment_context or "",
        data_access=req.data_access or [],
        risk_indicators=req.risk_indicators or [],
    )
    adapter = None if (req.mode or "B").upper() == "A" else MockAdapter(security_level=req.mock_level)

    if req.backend == "mock":
        llm = MockLLMBackend()
    else:
        llm = ClaudeBackend()

    report = run_full_evaluation(profile, adapter=adapter, llm=llm)
    return _ensure_serializable(report.to_dict())


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "frontend-api-suite"}


@app.post("/analyze/repo")
def analyze_repo_endpoint(request: RepoAnalyzeRequest) -> dict:
    """
    Collect key files from a GitHub URL or local path and call an LLM to
    generate a structured system description ready for /evaluate/council.
    """
    try:
        from council.repo_analyzer import analyze_repo
        description = analyze_repo(
            source=request.source,
            backend=request.backend,
            vllm_base_url=request.vllm_base_url,
            vllm_model=request.vllm_model,
            github_token=request.github_token or None,
        )
        return {"system_description": description, "source": request.source}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/evaluate/expert1-attack")
def evaluate_expert1_attack(request: Expert1AttackRequest) -> dict:
    session_id = str(uuid.uuid4())
    audit_log_event(
        stage="request_received",
        status="success",
        actor="frontend_api",
        message="Expert1 attack request accepted",
        payload={
            "mode": (request.mode or "B").upper(),
            "backend": request.backend,
            "description_length": len(request.system_description or ""),
        },
        source="frontend_api",
        session_id=session_id,
        agent_id=request.agent_id,
    )
    try:
        result = _run_expert1_attack(request)
        audit_log_event(
            stage="expert1_completed",
            status="success",
            actor="expert1",
            message="Expert1 active attack completed",
            payload={
                "recommendation": result.get("recommendation"),
                "risk_tier": result.get("risk_tier"),
            },
            source="frontend_api",
            session_id=session_id,
            agent_id=request.agent_id,
        )
        audit_log_event(
            stage="response_sent",
            status="success",
            actor="frontend_api",
            message="Expert1 response sent",
            payload={},
            source="frontend_api",
            session_id=session_id,
            agent_id=request.agent_id,
        )
        return result
    except Exception as e:
        audit_log_event(
            stage="evaluation_failed",
            status="error",
            actor="frontend_api",
            message="Expert1 attack failed",
            payload={"error": str(e)},
            severity="ERROR",
            source="frontend_api",
            session_id=session_id,
            agent_id=request.agent_id,
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/evaluate/council")
def evaluate_council(request: CouncilEvaluateRequest) -> dict:
    session_id = str(uuid.uuid4())
    audit_log_event(
        stage="request_received",
        status="success",
        actor="frontend_api",
        message="Council evaluation API request accepted",
        payload={
            "backend": request.backend,
            "description_length": len(request.system_description or ""),
        },
        source="frontend_api",
        session_id=session_id,
        agent_id=request.agent_id,
    )
    try:
        from council.agent_submission import AgentSubmission
        from council.council_orchestrator import CouncilOrchestrator

        submission = AgentSubmission(
            agent_id=request.agent_id,
            system_description=request.system_description,
            system_name=request.system_name,
            metadata={
                "purpose": request.purpose,
                "deployment_context": request.deployment_context,
                "data_access": request.data_access,
                "risk_indicators": request.risk_indicators,
            },
        )
        orch = CouncilOrchestrator(
            backend=request.backend,
            vllm_base_url=request.vllm_base_url,
            vllm_model=request.vllm_model,
        )
        report = orch.evaluate(submission)
        response = _ensure_serializable(report.to_dict())
        audit_log_event(
            stage="response_sent",
            status="success",
            actor="frontend_api",
            message="Council evaluation response sent",
            payload={"incident_id": response.get("incident_id")},
            source="frontend_api",
            session_id=session_id,
            incident_id=response.get("incident_id"),
            agent_id=request.agent_id,
        )
        return response
    except Exception as e:
        audit_log_event(
            stage="evaluation_failed",
            status="error",
            actor="frontend_api",
            message="Council evaluation failed",
            payload={"error": str(e)},
            severity="ERROR",
            source="frontend_api",
            session_id=session_id,
            agent_id=request.agent_id,
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/evaluations")
def list_evaluations(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    if not DB_PATH.exists():
        return {"items": [], "count": 0}
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT incident_id, agent_id, system_name, created_at, decision, risk_tier, consensus, summary_core, file_path
        FROM evaluations
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"items": rows, "count": len(rows)}


@app.get("/evaluations/{incident_id}")
def get_evaluation(incident_id: str) -> dict:
    return _load_report_json(incident_id)


@app.get("/evaluations/{incident_id}/markdown")
def get_evaluation_markdown(incident_id: str) -> PlainTextResponse:
    report = _load_report_json(incident_id)
    md = _report_to_markdown(report)
    return PlainTextResponse(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={incident_id}.md"},
    )


@app.get("/knowledge/index")
def get_knowledge_index(limit: int = Query(default=20, ge=1, le=500)) -> dict:
    if not INDEX_PATH.exists():
        return {"items": [], "count": 0}
    lines = INDEX_PATH.read_text(encoding="utf-8").splitlines()
    items = []
    for ln in lines[-limit:][::-1]:
        try:
            items.append(json.loads(ln))
        except Exception:
            continue
    return {"items": items, "count": len(items)}


@app.get("/knowledge/search")
def search_knowledge(
    query: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=200),
) -> dict:
    if not DB_PATH.exists():
        return {"items": [], "count": 0}
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    like_q = f"%{query}%"
    cur.execute(
        """
        SELECT incident_id, agent_id, system_name, created_at, decision, risk_tier, consensus, summary_core, file_path
        FROM evaluations
        WHERE summary_core LIKE ? OR agent_id LIKE ? OR system_name LIKE ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (like_q, like_q, like_q, limit),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"items": rows, "count": len(rows)}


@app.get("/audits/{incident_id}")
def get_audits_by_incident(
    incident_id: str,
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict:
    events = audit_list_events(incident_id=incident_id, limit=limit, offset=offset)
    spans = audit_list_spans(incident_id=incident_id, limit=limit, offset=offset)
    return {"incident_id": incident_id, "events": events, "spans": spans, "count": len(events)}


@app.get("/audits/session/{session_id}")
def get_audits_by_session(
    session_id: str,
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict:
    events = audit_list_events(session_id=session_id, limit=limit, offset=offset)
    spans = audit_list_spans(session_id=session_id, limit=limit, offset=offset)
    return {"session_id": session_id, "events": events, "spans": spans, "count": len(events)}


@app.get("/audits")
def get_recent_audits(
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict:
    events = audit_list_events(limit=limit, offset=offset)
    return {"items": events, "count": len(events)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("frontend_api.main:app", host="0.0.0.0", port=8100, reload=True)

