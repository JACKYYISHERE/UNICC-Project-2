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
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Load API keys from expert3_rag/env if not already in environment
import os as _os
_env_file = BASE_DIR / "expert3_rag" / "env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            if not _os.environ.get(_k.strip()):
                _os.environ[_k.strip()] = _v.strip()

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


def _resolve_backend(requested: str, vllm_base_url: str = "http://localhost:8000") -> str:
    """
    If the requested backend is 'vllm' but the server is unreachable,
    fall back to 'claude' automatically (only when ANTHROPIC_API_KEY is set).
    Logs a warning but never raises.
    """
    import os
    if requested != "vllm":
        return requested
    import urllib.request, urllib.error
    try:
        urllib.request.urlopen(f"{vllm_base_url.rstrip('/')}/health", timeout=3)
        return "vllm"
    except Exception:
        pass
    # vLLM unreachable — fall back to Claude if key is present
    if os.environ.get("ANTHROPIC_API_KEY"):
        print(f"[backend] vLLM unreachable at {vllm_base_url} — falling back to Claude")
        return "claude"
    # Neither available
    raise HTTPException(
        status_code=503,
        detail=(
            f"vLLM endpoint unreachable at {vllm_base_url}: Connection refused\n"
            "Either start vLLM (`vllm serve <model> --port 8000`) "
            "or set ANTHROPIC_API_KEY on the server for Claude fallback."
        ),
    )


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
    """Generate a structured PDF from a CouncilReport dict. Returns raw bytes."""
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, KeepTogether,
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=22*mm, bottomMargin=22*mm,
    )

    # ── palette ───────────────────────────────────────────────────────────────
    BLUE   = colors.HexColor("#007AFF")
    GREEN  = colors.HexColor("#34C759")
    ORANGE = colors.HexColor("#FF9500")
    RED    = colors.HexColor("#FF3B30")
    GRAY1  = colors.HexColor("#1C1C1E")
    GRAY3  = colors.HexColor("#48484A")
    GRAY5  = colors.HexColor("#8E8E93")
    GRAY6  = colors.HexColor("#F2F2F7")

    def decision_color(rec: str) -> object:
        rec = (rec or "").upper()
        if rec == "APPROVE": return GREEN
        if rec == "REJECT":  return RED
        return ORANGE

    base = getSampleStyleSheet()

    def S(name, **kw):
        return ParagraphStyle(name, parent=base["Normal"], **kw)

    cover_title  = S("CoverTitle",  fontSize=22, textColor=BLUE,  spaceAfter=4, fontName="Helvetica-Bold")
    cover_sub    = S("CoverSub",    fontSize=11, textColor=GRAY3, spaceAfter=2)
    cover_meta   = S("CoverMeta",   fontSize=9,  textColor=GRAY5, spaceAfter=2)
    h1_style     = S("H1",          fontSize=13, textColor=GRAY1, spaceBefore=10, spaceAfter=4, fontName="Helvetica-Bold")
    h2_style     = S("H2",          fontSize=11, textColor=BLUE,  spaceBefore=8,  spaceAfter=3, fontName="Helvetica-Bold")
    h3_style     = S("H3",          fontSize=10, textColor=GRAY3, spaceBefore=6,  spaceAfter=2, fontName="Helvetica-Bold")
    body_style   = S("Body",        fontSize=9,  textColor=GRAY3, spaceAfter=3,   leading=14)
    small_style  = S("Small",       fontSize=8,  textColor=GRAY5, spaceAfter=2,   leading=12)
    bullet_style = S("Bullet",      fontSize=9,  textColor=GRAY3, spaceAfter=2,   leftIndent=10, leading=13)
    label_style  = S("Label",       fontSize=8,  textColor=GRAY5, spaceAfter=1,   fontName="Helvetica-Bold", textTransform="uppercase")
    code_style   = S("Code",        fontSize=8,  textColor=GRAY3, fontName="Courier", spaceAfter=2, leading=12)

    def hr(): return HRFlowable(width="100%", thickness=0.5, color=GRAY6, spaceAfter=4, spaceBefore=4)
    def sp(h=4): return Spacer(1, h*mm)

    def safe(txt: str, max_chars: int = 2000) -> str:
        if not txt: return ""
        txt = str(txt)[:max_chars]
        return txt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    story = []

    # ── Cover ─────────────────────────────────────────────────────────────────
    cd   = r.get("council_decision") or {}
    rec  = cd.get("final_recommendation", "N/A")
    cons = cd.get("consensus_level", "N/A")

    story.append(sp(8))
    story.append(Paragraph("UNICC AI Safety Council", cover_title))
    story.append(Paragraph("Full Assessment Report", cover_sub))
    story.append(sp(2))

    dec_color = decision_color(rec)
    story.append(Table(
        [[Paragraph(f'<font color="{dec_color.hexval()}"><b>{rec}</b></font>', S("Dec", fontSize=18, fontName="Helvetica-Bold")),
          Paragraph(f"Consensus: {cons}", S("Cons", fontSize=10, textColor=GRAY5))]],
        colWidths=["60%", "40%"],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), GRAY6),
            ("ROUNDEDCORNERS", (0, 0), (-1, -1), [4, 4, 4, 4]),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ]),
    ))
    story.append(sp(3))
    story.append(Paragraph(f"<b>System:</b>  {safe(r.get('system_name', r.get('agent_id', '')))}",  cover_meta))
    story.append(Paragraph(f"<b>Agent ID:</b> {safe(r.get('agent_id', ''))}",  cover_meta))
    story.append(Paragraph(f"<b>Incident:</b> {safe(r.get('incident_id', ''))}",  cover_meta))
    story.append(Paragraph(f"<b>Timestamp:</b> {safe(r.get('timestamp', '')[:19].replace('T', ' '))} UTC",  cover_meta))
    story.append(hr())

    # ── Section 0: System description ─────────────────────────────────────────
    story.append(Paragraph("0. System Under Evaluation", h1_style))
    desc = r.get("system_description") or ""
    story.append(Paragraph(safe(desc, 1200), body_style))
    story.append(hr())

    # ── Section 1: Expert Reports ──────────────────────────────────────────────
    story.append(Paragraph("1. Expert Analyses &amp; Judgments", h1_style))
    expert_map = {
        "security":      ("🔒", "Expert 1 — Security &amp; Adversarial"),
        "governance":    ("⚖️",  "Expert 2 — Governance &amp; Compliance"),
        "un_mission_fit":("🌐", "Expert 3 — UN Mission Fit"),
    }
    for key, (icon, title) in expert_map.items():
        er = (r.get("expert_reports") or {}).get(key, {})
        if not er:
            continue
        exp_rec = er.get("recommendation", "N/A")
        ec = decision_color(exp_rec)
        block = []
        block.append(Paragraph(
            f'{title} — <font color="{ec.hexval()}"><b>{exp_rec}</b></font>', h2_style))

        # error fallback
        if er.get("error"):
            block.append(Paragraph(f"⚠ Module error: {safe(er['error'])}", small_style))
        else:
            # dimension scores
            dim_scores = er.get("dimension_scores") or {}
            if dim_scores:
                block.append(Paragraph("Dimension Scores", label_style))
                rows = [[Paragraph(f"<b>{k.replace('_',' ').title()}</b>", small_style),
                         Paragraph(str(v), small_style)]
                        for k, v in dim_scores.items()]
                t = Table(rows, colWidths=["60%", "40%"],
                          style=TableStyle([
                              ("BACKGROUND", (0, 0), (-1, -1), GRAY6),
                              ("TOPPADDING",    (0, 0), (-1, -1), 3),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                              ("LEFTPADDING",   (0, 0), (-1, -1), 6),
                          ]))
                block.append(t)
                block.append(sp(2))

            # key findings
            findings = er.get("key_findings") or []
            if findings:
                block.append(Paragraph("Key Findings", label_style))
                for f in findings[:6]:
                    block.append(Paragraph(f"• {safe(f, 400)}", bullet_style))
                block.append(sp(1))

            # narrative
            narrative = er.get("narrative") or ""
            if narrative:
                block.append(Paragraph("Narrative", label_style))
                block.append(Paragraph(safe(narrative, 800), body_style))

            # violations / gaps
            violations = er.get("un_principle_violations") or er.get("key_gaps") or []
            if violations:
                block.append(Paragraph("Compliance Gaps / Violations", label_style))
                for v in violations[:5]:
                    block.append(Paragraph(f"• {safe(v, 300)}", bullet_style))

        story.append(KeepTogether(block))
        story.append(sp(2))

    story.append(hr())

    # ── Section 2: Council Debate ──────────────────────────────────────────────
    story.append(Paragraph("2. Council Debate (Cross-Expert Critiques)", h1_style))
    critiques = r.get("critiques") or {}
    for i, (ckey, cv) in enumerate(critiques.items()):
        agrees = cv.get("agrees", True)
        agree_label = "Agrees" if agrees else "Disagrees"
        agree_color = GREEN.hexval() if agrees else ORANGE.hexval()
        from_e = cv.get("from_expert", "").replace("_", " ").title()
        on_e   = cv.get("on_expert",   "").replace("_", " ").title()
        block = []
        block.append(Paragraph(
            f'Critique {i+1}: {safe(from_e)} → {safe(on_e)} '
            f'— <font color="{agree_color}"><b>{agree_label}</b></font>',
            h3_style))
        kp = safe(cv.get("key_point", ""), 400)
        block.append(Paragraph(f'<i>"{kp}"</i>', body_style))
        stance = safe(cv.get("stance", ""), 200)
        if stance:
            block.append(Paragraph(f"<b>Stance:</b> {stance}", small_style))
        evs = cv.get("evidence_references") or []
        for ev in evs[:3]:
            block.append(Paragraph(f"§ {safe(ev, 200)}", bullet_style))
        story.append(KeepTogether(block))
        story.append(sp(1))

    story.append(hr())

    # ── Section 3: Final Decision ──────────────────────────────────────────────
    story.append(Paragraph("3. Expert Final Opinions &amp; Arbitration", h1_style))
    rows = []
    for key, (_, title) in expert_map.items():
        er = (r.get("expert_reports") or {}).get(key, {})
        exp_rec = er.get("recommendation", "N/A")
        ec = decision_color(exp_rec)
        rows.append([
            Paragraph(title, small_style),
            Paragraph(f'<font color="{ec.hexval()}"><b>{exp_rec}</b></font>', small_style),
        ])
    t = Table(rows, colWidths=["70%", "30%"],
              style=TableStyle([
                  ("BACKGROUND", (0, 0), (-1, -1), GRAY6),
                  ("TOPPADDING",    (0, 0), (-1, -1), 4),
                  ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                  ("LEFTPADDING",   (0, 0), (-1, -1), 8),
                  ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.white),
              ]))
    story.append(t)
    story.append(sp(3))

    story.append(Paragraph("Council Decision", h2_style))
    dec_col = decision_color(rec)
    story.append(Table(
        [[Paragraph(f'<font color="{dec_col.hexval()}"><b>{rec}</b></font>',
                    S("BigDec", fontSize=16, fontName="Helvetica-Bold")),
          Paragraph(f"Consensus: <b>{cons}</b><br/>Human Oversight: <b>{cd.get('human_oversight_required','?')}</b><br/>Blocks Deployment: <b>{cd.get('compliance_blocks_deployment','?')}</b>",
                    small_style)]],
        colWidths=["35%", "65%"],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), GRAY6),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ]),
    ))
    story.append(sp(3))

    rationale = cd.get("rationale") or r.get("council_note") or ""
    if rationale:
        story.append(Paragraph("Rationale", label_style))
        story.append(Paragraph(safe(rationale, 1200), body_style))

    story.append(hr())
    story.append(Paragraph(
        "This report was generated by the UNICC AI Safety Council automated pipeline. "
        "All findings should be reviewed by qualified human evaluators before any deployment decision.",
        S("Footer", fontSize=8, textColor=GRAY5, alignment=TA_CENTER)
    ))

    doc.build(story)
    return buf.getvalue()


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
    backend: str = Field("vllm", description="claude|vllm")
    vllm_base_url: str = "http://localhost:8000"
    vllm_model: str = "meta-llama/Meta-Llama-3-70B-Instruct"


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
    effective_backend = _resolve_backend(request.backend, request.vllm_base_url)
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
            backend=effective_backend,
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
        SELECT incident_id, agent_id, system_name, created_at, decision, risk_tier, consensus,
               summary_core, file_path, rec_security, rec_governance, rec_un_mission
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
        SELECT incident_id, agent_id, system_name, created_at, decision, risk_tier, consensus,
               summary_core, file_path, rec_security, rec_governance, rec_un_mission
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

