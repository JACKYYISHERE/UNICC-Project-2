from __future__ import annotations

import glob
import json
import os
import re  # noqa: F401 (re-exported for pdf_renderer compat)
import sqlite3
import sys
import time
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Optional

import threading as _threading
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Load API keys from .env files — checked in priority order.
# The evaluator is expected to set ANTHROPIC_API_KEY as a real env var;
# these files are a convenience fallback for local development.
def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for _line in path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            if not os.environ.get(_k.strip()):
                os.environ[_k.strip()] = _v.strip()

# Priority: Expert1/.env → expert3_rag/env (first found wins)
_load_env_file(BASE_DIR / "Expert1" / ".env")
_load_env_file(BASE_DIR / "expert3_rag" / "env")

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


# ── In-memory evaluation status store ────────────────────────────────────────
# Maps incident_id → {"status": "running"|"complete"|"failed",
#                      "started_at": float, "elapsed_seconds": float,
#                      "phase": str, "progress_pct": int,
#                      "error": str|None}
#
# progress_pct milestones (approximate, based on observed timing):
#   0  → request received
#  10  → repo analysis complete
#  20  → experts started
#  50  → all experts complete
#  75  → critiques complete
#  90  → arbitration complete
# 100  → evaluation complete
_eval_status: dict[str, dict] = {}
_eval_status_lock = _threading.Lock()


def _set_phase(incident_id: str, phase: str, pct: int) -> None:
    """Update progress phase + percentage for a running evaluation."""
    with _eval_status_lock:
        if incident_id in _eval_status:
            _eval_status[incident_id]["phase"] = phase
            _eval_status[incident_id]["progress_pct"] = pct


def _resolve_backend(requested: str, vllm_base_url: str = "http://localhost:8000") -> str:
    """
    Auto-select the best available LLM backend.

    Priority order:
      1. UNICC_MOCK_MODE=1  → always "mock" (no API calls, for CI/Sandbox/portability tests)
      2. requested="mock"   → "mock"
      3. requested="claude" → "claude" (if ANTHROPIC_API_KEY present)
      4. requested="vllm"   → "vllm"  (if server reachable)
         └─ fallback to "claude" if key present, else "mock"
      5. No key, no vLLM    → "mock"  (graceful degradation, never raises)
    """
    # Env-var override — useful in Docker/CI where no real LLM is available
    if os.environ.get("UNICC_MOCK_MODE", "").strip() in ("1", "true", "yes"):
        print("[backend] UNICC_MOCK_MODE=1 — using mock backend")
        return "mock"
    if requested == "mock":
        return "mock"
    if requested == "claude":
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "claude"
        print("[backend] backend=claude requested but ANTHROPIC_API_KEY not set — falling back to mock")
        return "mock"
    # vllm path
    import urllib.request, urllib.error
    try:
        urllib.request.urlopen(f"{vllm_base_url.rstrip('/')}/health", timeout=3)
        return "vllm"
    except Exception:
        pass
    # vLLM unreachable — try Claude, then mock
    if os.environ.get("ANTHROPIC_API_KEY"):
        print(f"[backend] vLLM unreachable at {vllm_base_url} — falling back to Claude")
        return "claude"
    print(f"[backend] vLLM unreachable and no ANTHROPIC_API_KEY — falling back to mock")
    return "mock"


_EVAL_COLUMNS = (
    "incident_id, agent_id, system_name, created_at, decision, risk_tier, consensus, "
    "summary_core, file_path, rec_security, rec_governance, rec_un_mission"
)

def _query_evaluations(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a SELECT against the evaluations table; returns list of row dicts."""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in conn.cursor().execute(sql, params).fetchall()]
    finally:
        conn.close()
    return rows


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


def _report_to_pdf(r: dict) -> bytes:
    """Generate a structured PDF — see frontend_api/pdf_renderer.py."""
    from frontend_api.pdf_renderer import report_to_pdf as _pdf
    return _pdf(r)

def _report_to_markdown(r: dict) -> str:
    """Generate a Markdown summary — see frontend_api/markdown_renderer.py."""
    from frontend_api.markdown_renderer import report_to_markdown as _md
    return _md(r)


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
    system_description: str = Field(
        "",
        description=(
            "Full description of the AI system under review. "
            "If omitted and github_url is provided, the system will automatically "
            "call /analyze/repo to extract a description from the repository."
        ),
    )
    github_url: str = Field(
        "",
        description=(
            "Optional GitHub repository URL (e.g. https://github.com/owner/repo). "
            "When provided and system_description is empty, the backend auto-calls "
            "/analyze/repo to extract the system description before running the council."
        ),
    )
    purpose: str = ""
    deployment_context: str = ""
    data_access: list[str] = Field(default_factory=list)
    risk_indicators: list[str] = Field(default_factory=list)
    backend: str = Field("vllm", description="claude|vllm")
    vllm_base_url: str = "http://localhost:8000"
    vllm_model: str = "meta-llama/Meta-Llama-3-70B-Instruct"
    live_target_url: str = Field(
        "",
        description="If set, Expert 1 runs in Live Attack mode against this URL (e.g. http://localhost:5001)"
    )


class RepoAnalyzeRequest(BaseModel):
    source: str = Field(
        default="",
        description="GitHub URL or absolute local path (omit when sending raw text)",
    )
    text: str = Field(
        default="",
        description="Raw text to analyse (PDF/Markdown content). Overrides source.",
    )
    backend: str = Field("vllm", description="claude|vllm")
    vllm_base_url: str = "http://localhost:8000"
    vllm_model: str = "meta-llama/Meta-Llama-3-70B-Instruct"
    github_token: str = Field("", description="Optional GitHub PAT for private repos")


app = FastAPI(
    title="UNICC Frontend API Suite",
    description="All frontend-callable APIs in one folder for designers/developers.",
    version="1.0.0",
)

# CORS: default to localhost dev server; override with CORS_ORIGINS env var
# e.g. CORS_ORIGINS="http://localhost:5173,https://your-deployment.example.com"
_cors_origins_env = os.environ.get("CORS_ORIGINS", "").strip()
_cors_origins = (
    [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
    if _cors_origins_env
    else ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Serve built React frontend as static files (present after `npm run build`) ─
# When running in Docker or after a local build the dist/ folder exists and the
# single-page app is served at /.  API routes take priority because FastAPI
# registers them first; the SPA catch-all comes last.
_FRONTEND_DIST = BASE_DIR / "real_frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse as _FileResponse

    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="assets")

    # Serve index.html for SPA client-side routes via a 404 exception handler.
    # This fires ONLY when FastAPI has no matching route, so all API routes
    # take natural priority — no registration-order issues.
    from fastapi.responses import JSONResponse as _JSONResponse

    _API_PREFIXES = (
        "/health", "/evaluate", "/evaluations", "/analyze",
        "/audit", "/knowledge", "/expert1", "/docs", "/openapi",
    )

    @app.exception_handler(404)
    async def _spa_404_handler(request: Request, exc: Exception):
        path = request.url.path
        # API paths return proper JSON 404
        if any(path.startswith(prefix) for prefix in _API_PREFIXES):
            detail = getattr(exc, "detail", f"Not found: {path}")
            return _JSONResponse({"detail": detail}, status_code=404)
        # SPA routes serve index.html
        index = _FRONTEND_DIST / "index.html"
        if index.exists():
            return _FileResponse(str(index))
        return _JSONResponse({"detail": "Frontend not built — run `npm run build` in real_frontend/"}, status_code=404)


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
    Structured analysis of a GitHub repo, local path, or raw text.
    Returns: system_description, capabilities, data_sources, human_oversight,
             category, deploy_zone, source.
    """
    effective_backend = _resolve_backend(request.backend, request.vllm_base_url)
    kwargs = dict(
        backend=effective_backend,
        vllm_base_url=request.vllm_base_url,
        vllm_model=request.vllm_model,
    )
    try:
        if request.text.strip():
            from council.repo_analyzer import analyze_text
            result = analyze_text(text=request.text, source_label="uploaded text", **kwargs)
            result["source"] = "text"
        else:
            from council.repo_analyzer import analyze_repo
            result = analyze_repo(
                source=request.source,
                github_token=request.github_token or None,
                **kwargs,
            )
            result["source"] = request.source
        return result
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


def _mock_council_report(request: "CouncilEvaluateRequest", incident_id: str) -> "Any":
    """Generate zero-LLM mock report — see frontend_api/mock_report.py."""
    from frontend_api.mock_report import generate_mock_report
    return generate_mock_report(request, incident_id)


def _run_council_evaluation(
    request: "CouncilEvaluateRequest",
    incident_id: str,
    session_id: str,
    effective_backend: str,
) -> None:
    """Background worker: run the full council evaluation and update status store."""
    started = time.time()
    try:
        # ── Mock path: no LLM calls, instant response ─────────────────────────
        if effective_backend == "mock":
            _mock_council_report(request, incident_id)
            elapsed = time.time() - started
            with _eval_status_lock:
                _eval_status[incident_id] = {
                    "status": "complete",
                    "started_at": started,
                    "elapsed_seconds": round(elapsed, 2),
                    "error": None,
                }
            return

        from council.agent_submission import AgentSubmission
        from council.council_orchestrator import CouncilOrchestrator

        # Auto-extract system description from GitHub URL if not provided
        _set_phase(incident_id, "Analysing repository…", 5)
        resolved_description = request.system_description or ""
        resolved_system_name = request.system_name or request.agent_id
        if not resolved_description.strip() and request.github_url.strip():
            try:
                print(f"[Council API] system_description empty — auto-analyzing {request.github_url}")
                from council.repo_analyzer import analyze_repo
                repo_info = analyze_repo(
                    source=request.github_url.strip(),
                    backend=effective_backend,
                    vllm_base_url=request.vllm_base_url,
                    vllm_model=request.vllm_model,
                )
                resolved_description = repo_info.get("system_description", "")
                if not resolved_system_name or resolved_system_name == request.agent_id:
                    resolved_system_name = repo_info.get("system_name", resolved_system_name) or resolved_system_name
            except Exception as _repo_err:
                print(f"[Council API] WARNING: repo analysis failed: {_repo_err}")
        _set_phase(incident_id, "Repository analysis complete — starting experts…", 15)

        if not resolved_description.strip():
            raise ValueError(
                "system_description is required. Provide it directly or supply a github_url "
                "so the backend can extract it automatically."
            )

        submission = AgentSubmission(
            incident_id=incident_id,
            agent_id=request.agent_id,
            system_description=resolved_description,
            system_name=resolved_system_name,
            metadata={
                "purpose": request.purpose,
                "deployment_context": request.deployment_context,
                "data_access": request.data_access,
                "risk_indicators": request.risk_indicators,
            },
            live_target_url=request.live_target_url or "",
        )
        orch = CouncilOrchestrator(
            backend=effective_backend,
            vllm_base_url=request.vllm_base_url,
            vllm_model=request.vllm_model,
        )

        def _on_progress(phase: str, pct: int) -> None:
            _set_phase(incident_id, phase, pct)

        report = orch.evaluate(submission, on_progress=_on_progress)
        elapsed = time.time() - started
        with _eval_status_lock:
            _eval_status[incident_id] = {
                "status": "complete",
                "started_at": started,
                "elapsed_seconds": round(elapsed, 1),
                "error": None,
            }
        audit_log_event(
            stage="response_sent",
            status="success",
            actor="frontend_api",
            message="Council evaluation complete",
            payload={"incident_id": incident_id, "elapsed_seconds": round(elapsed, 1)},
            source="frontend_api",
            session_id=session_id,
            incident_id=incident_id,
            agent_id=request.agent_id,
        )
    except Exception as e:
        elapsed = time.time() - started
        with _eval_status_lock:
            _eval_status[incident_id] = {
                "status": "failed",
                "started_at": started,
                "elapsed_seconds": round(elapsed, 1),
                "error": str(e),
            }
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


@app.post("/evaluate/council")
def evaluate_council(
    request: CouncilEvaluateRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Submit a council evaluation.  Returns immediately with an incident_id.
    The evaluation runs in the background; poll /evaluations/{incident_id}/status
    to track progress, and /evaluations/{incident_id} (or /evaluations/latest)
    to retrieve the full report once complete.
    """
    session_id = str(uuid.uuid4())

    # Pre-generate a stable incident_id so the client can start polling immediately.
    ts = time.strftime("%Y%m%d")
    slug = (request.agent_id or "unknown").lower()[:24].replace(" ", "-")
    suffix = str(uuid.uuid4())[:6]
    incident_id = f"inc_{ts}_{slug}_{suffix}"

    audit_log_event(
        stage="request_received",
        status="success",
        actor="frontend_api",
        message="Council evaluation accepted — running in background",
        payload={
            "incident_id": incident_id,
            "backend": request.backend,
            "description_length": len(request.system_description or ""),
        },
        source="frontend_api",
        session_id=session_id,
        agent_id=request.agent_id,
    )

    effective_backend = _resolve_backend(request.backend, request.vllm_base_url)

    # Register as "running" before spawning so /status is immediately useful.
    with _eval_status_lock:
        _eval_status[incident_id] = {
            "status": "running",
            "started_at": time.time(),
            "elapsed_seconds": 0,
            "phase": "Starting evaluation…",
            "progress_pct": 0,
            "error": None,
        }

    background_tasks.add_task(
        _run_council_evaluation, request, incident_id, session_id, effective_backend
    )

    return {
        "incident_id": incident_id,
        "status": "running",
        "message": "Evaluation started. Poll /evaluations/{incident_id}/status for progress.",
        "poll_url": f"/evaluations/{incident_id}/status",
        "result_url": f"/evaluations/{incident_id}",
    }


@app.get("/evaluations")
def list_evaluations(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    rows = _query_evaluations(
        f"SELECT {_EVAL_COLUMNS} FROM evaluations ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    return {"items": rows, "count": len(rows)}


@app.get("/evaluations/latest")
def get_latest_evaluation(agent_id: str = Query(default="")) -> dict:
    """
    Returns the most recently written report file.
    Useful when the POST /evaluate/council client timed out but the
    backend finished and saved the report — call this to retrieve it.
    Optional: filter by agent_id substring match.
    """
    files = sorted(
        glob.glob(str(REPORTS_DIR / "*.json")),
        key=lambda p: Path(p).stat().st_mtime,
        reverse=True,
    )
    for fpath in files:
        name = Path(fpath).stem
        if agent_id and agent_id not in name:
            continue
        try:
            return json.loads(Path(fpath).read_text(encoding="utf-8"))
        except Exception:
            continue
    raise HTTPException(status_code=404, detail="No matching report found")


@app.get("/evaluations/{incident_id}/status")
def get_evaluation_status(incident_id: str) -> dict:
    """
    Returns the live status of a background evaluation.
    status: "running" | "complete" | "failed" | "unknown"
    When complete, result_url points to the full report.
    """
    with _eval_status_lock:
        info = _eval_status.get(incident_id)
    if info is None:
        # May have been started in a previous server process — check disk
        p = REPORTS_DIR / f"{incident_id}.json"
        if p.exists():
            return {"incident_id": incident_id, "status": "complete",
                    "elapsed_seconds": None, "error": None,
                    "result_url": f"/evaluations/{incident_id}"}
        return {"incident_id": incident_id, "status": "unknown",
                "elapsed_seconds": None, "error": None}
    elapsed = (
        info["elapsed_seconds"]
        if info["status"] != "running"
        else round(time.time() - info["started_at"], 1)
    )
    return {
        "incident_id": incident_id,
        "status": info["status"],
        "elapsed_seconds": elapsed,
        "phase": info.get("phase", ""),
        "progress_pct": 100 if info["status"] == "complete" else info.get("progress_pct", 0),
        "error": info.get("error"),
        "result_url": f"/evaluations/{incident_id}" if info["status"] == "complete" else None,
    }


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


@app.get("/evaluations/{incident_id}/pdf")
def get_evaluation_pdf(incident_id: str) -> Response:
    report = _load_report_json(incident_id)
    try:
        pdf_bytes = _report_to_pdf(report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={incident_id}.pdf"},
    )


@app.get("/audit/recent")
def get_recent_audit(limit: int = Query(default=30, ge=1, le=100)) -> dict:
    """Return the most recent audit events across all sessions (for live polling)."""
    try:
        events = audit_list_events(limit=limit)
        return {"events": events}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/evaluations/{incident_id}/audit")
def get_evaluation_audit(incident_id: str) -> dict:
    """Return audit events + timing spans for a single evaluation run."""
    try:
        from council.audit import list_events, list_spans
        events = list_events(incident_id=incident_id, limit=200)
        spans  = list_spans(incident_id=incident_id,  limit=50)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"incident_id": incident_id, "events": events, "spans": spans}


@app.get("/knowledge/stats")
def get_knowledge_stats() -> dict:
    """Return doc counts for each expert's ChromaDB plus indexed cases count."""
    experts = [
        {
            "key": "expert1",
            "label": "Expert 1 · Security",
            "description": "MITRE ATLAS attack techniques & case studies",
            "path": str(BASE_DIR / "Expert1" / "rag" / "chroma_db_expert1"),
            "collection": "expert1_attack_techniques",
            "collection2": "expert1_attack_strategies",
        },
        {
            "key": "expert2",
            "label": "Expert 2 · Governance",
            "description": "EU AI Act legal compliance",
            "path": str(BASE_DIR / "Expert 2" / "chroma_db_expert2"),
            "collection": "expert2_legal_compliance",
            "collection2": None,
        },
        {
            "key": "expert3",
            "label": "Expert 3 · UN Mission",
            "description": "UN Charter AI safety reference",
            "path": str(BASE_DIR / "Expert 3" / "expert3_rag" / "chroma_db"),
            "collection": "expert3_un_context",
            "collection2": None,
        },
    ]
    results = []
    try:
        import chromadb as _chroma
        for ex in experts:
            try:
                client = _chroma.PersistentClient(path=ex["path"])
                total = 0
                for col_name in [ex["collection"], ex.get("collection2")]:
                    if not col_name:
                        continue
                    try:
                        total += client.get_collection(col_name).count()
                    except Exception:
                        pass
                results.append({
                    "key": ex["key"],
                    "label": ex["label"],
                    "description": ex["description"],
                    "doc_count": total,
                    "status": "ok",
                })
            except Exception as e:
                results.append({
                    "key": ex["key"],
                    "label": ex["label"],
                    "description": ex["description"],
                    "doc_count": 0,
                    "status": f"error: {e}",
                })
    except ImportError:
        results = [
            {"key": ex["key"], "label": ex["label"], "description": ex["description"],
             "doc_count": 0, "status": "chromadb not installed"}
            for ex in experts
        ]
    # Cases indexed in knowledge_index.jsonl
    cases_indexed = 0
    if INDEX_PATH.exists():
        cases_indexed = sum(1 for _ in INDEX_PATH.read_text(encoding="utf-8").splitlines() if _.strip())
    return {"experts": results, "cases_indexed": cases_indexed}


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
    like_q = f"%{query}%"
    rows = _query_evaluations(
        f"SELECT {_EVAL_COLUMNS} FROM evaluations "
        "WHERE summary_core LIKE ? OR agent_id LIKE ? OR system_name LIKE ? "
        "ORDER BY created_at DESC LIMIT ?",
        (like_q, like_q, like_q, limit),
    )
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

