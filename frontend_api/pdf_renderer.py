"""
frontend_api/pdf_renderer.py
────────────────────────────
ReportLab PDF generator for CouncilReport dicts.
Extracted from main.py to keep route handlers thin.
"""
from __future__ import annotations

import io
import re


def report_to_pdf(r: dict) -> bytes:
    """Generate a structured PDF from a CouncilReport dict. Returns raw bytes."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, KeepTogether, PageBreak,
    )
    from reportlab.lib.enums import TA_LEFT, TA_CENTER  # noqa: F401

    PAGE_W = A4[0]
    CONTENT_W = PAGE_W - 40 * mm  # leftMargin + rightMargin

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=25 * mm, bottomMargin=25 * mm,
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
    WHITE  = colors.white

    def decision_color(rec: str) -> object:
        rec = (rec or "").upper()
        if rec == "APPROVE": return GREEN
        if rec == "REJECT":  return RED
        return ORANGE

    base = getSampleStyleSheet()

    def S(name, **kw):
        return ParagraphStyle(name, parent=base["Normal"], **kw)

    # All spaceAfter / spaceBefore are in POINTS (1mm ≈ 2.83pt)
    cover_title  = S("CoverTitle",  fontSize=24, textColor=BLUE,   leading=30, spaceAfter=6,  fontName="Helvetica-Bold")
    cover_sub    = S("CoverSub",    fontSize=12, textColor=GRAY3,  leading=18, spaceAfter=4)
    cover_meta   = S("CoverMeta",   fontSize=9,  textColor=GRAY5,  leading=16, spaceAfter=3)
    h1_style     = S("H1",          fontSize=13, textColor=GRAY1,  leading=20, spaceBefore=14, spaceAfter=6,  fontName="Helvetica-Bold")
    h2_style     = S("H2",          fontSize=11, textColor=BLUE,   leading=18, spaceBefore=12, spaceAfter=5,  fontName="Helvetica-Bold")
    h3_style     = S("H3",          fontSize=10, textColor=GRAY3,  leading=16, spaceBefore=8,  spaceAfter=4,  fontName="Helvetica-Bold")
    body_style   = S("Body",        fontSize=9,  textColor=GRAY3,  leading=15, spaceAfter=5,   wordWrap="CJK")
    small_style  = S("Small",       fontSize=8,  textColor=GRAY5,  leading=13, spaceAfter=3,   wordWrap="CJK")
    bullet_style = S("Bullet",      fontSize=9,  textColor=GRAY3,  leading=14, spaceAfter=3,   leftIndent=12, wordWrap="CJK")
    label_style  = S("Label",       fontSize=8,  textColor=GRAY5,  leading=13, spaceAfter=4,   spaceBefore=6, fontName="Helvetica-Bold")
    code_style   = S("Code",        fontSize=8,  textColor=GRAY3,  leading=12, fontName="Courier", spaceAfter=2)

    def hr():
        return HRFlowable(width="100%", thickness=0.5, color=GRAY6, spaceAfter=6, spaceBefore=6)

    def sp(h_mm: float = 4):
        return Spacer(1, h_mm * mm)

    def safe(txt: str, max_chars: int = 2000) -> str:
        if not txt:
            return ""
        txt = str(txt)[:max_chars]
        return txt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def col(pct: float) -> float:
        """Convert percentage to absolute column width."""
        return CONTENT_W * pct / 100

    # ── reusable table style helpers ──────────────────────────────────────────
    BASE_TABLE = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), GRAY6),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 7),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS",(0, 0), (-1, -1), [GRAY6, colors.HexColor("#E8E8ED")]),
    ])

    HEADER_TABLE = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  8),
        ("BACKGROUND",    (0, 1), (-1, -1), GRAY6),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [GRAY6, colors.HexColor("#E8E8ED")]),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 7),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ])

    # ── parse / render helpers ────────────────────────────────────────────────
    def parse_finding(f: str):
        if "[RISK]" not in f or "[EVIDENCE]" not in f:
            return None
        def extract(tag, nxt):
            m = re.search(rf'\[{tag}\]\s*(.*?)(?=\[{nxt}\]|$)', f, re.S)
            return (m.group(1) or "").strip() if m else ""
        return {
            "risk":     extract("RISK",     "EVIDENCE"),
            "evidence": extract("EVIDENCE", "IMPACT"),
            "impact":   extract("IMPACT",   "SCORE"),
            "score":    extract("SCORE",    r"\Z"),
        }

    def render_findings(block, findings):
        block.append(Paragraph("Key Findings", label_style))
        for idx, f in enumerate(findings[:8]):
            parsed = parse_finding(str(f))
            if parsed:
                sev_col = RED if "critical" in f.lower() else ORANGE
                block.append(Paragraph(
                    f'<font color="{sev_col.hexval()}"><b>Finding {idx + 1}</b></font>',
                    S(f"FH{idx}", fontSize=9, textColor=GRAY1, fontName="Helvetica-Bold",
                      spaceBefore=5, spaceAfter=2, leading=14)))
                rows = []
                for tag, val in [
                    ("RISK",     parsed["risk"]),
                    ("EVIDENCE", parsed["evidence"]),
                    ("IMPACT",   parsed["impact"]),
                    ("SCORE",    parsed["score"]),
                ]:
                    if val:
                        rows.append([
                            Paragraph(f"<b>{tag}</b>",
                                      S(f"Tag{idx}{tag}", fontSize=7, textColor=GRAY5,
                                        fontName="Helvetica-Bold", leading=11)),
                            Paragraph(safe(val, 350),
                                      S(f"Val{idx}{tag}", fontSize=8, textColor=GRAY3,
                                        leading=13, wordWrap="CJK")),
                        ])
                if rows:
                    t = Table(
                        rows,
                        colWidths=[col(15), col(85)],
                        style=TableStyle([
                            ("BACKGROUND",    (0, 0), (-1, -1), GRAY6),
                            ("TOPPADDING",    (0, 0), (-1, -1), 3),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
                            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
                            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
                            ("LINEBELOW",     (0, 0), (-1, -2), 0.3, WHITE),
                        ]),
                    )
                    block.append(t)
                    block.append(sp(1.5))
            else:
                block.append(Paragraph(f"• {safe(str(f), 450)}", bullet_style))
        block.append(sp(2))

    def render_attack_trail(block, er):
        attack_trace   = er.get("attack_trace")  or []
        probe_trace    = er.get("probe_trace")    or []
        boundary_trace = er.get("boundary_trace") or []
        breach_details = er.get("breach_details") or []
        std_suite      = (er.get("standard_suite_results") or {}).get("all_results") or []

        if not attack_trace:
            return

        block.append(sp(2))
        block.append(Paragraph("Live Attack Trail", label_style))
        block.append(sp(1))

        breaches = sum(1 for t in attack_trace if (t.get("classification") or "") == "BREACH")
        summary_rows = [
            [Paragraph("<b>Phase</b>",     small_style),
             Paragraph("<b>Turns</b>",     small_style),
             Paragraph("<b>Breaches</b>",  small_style)],
            [Paragraph("Phase 1 — Probe",    body_style), Paragraph(str(len(probe_trace)),    small_style), Paragraph("—", small_style)],
            [Paragraph("Phase 2 — Boundary", body_style), Paragraph(str(len(boundary_trace)), small_style), Paragraph("—", small_style)],
            [Paragraph("Phase 3 — Attack",   body_style), Paragraph(str(len(attack_trace)),   small_style),
             Paragraph(f'<font color="{RED.hexval() if breaches else GREEN.hexval()}"><b>{breaches}</b></font>', small_style)],
            [Paragraph("Standard Suite",     body_style), Paragraph(str(len(std_suite)),       small_style), Paragraph("—", small_style)],
        ]
        t = Table(
            summary_rows,
            colWidths=[col(55), col(22), col(23)],
            style=HEADER_TABLE,
        )
        block.append(t)
        block.append(sp(2))

        if breach_details:
            block.append(Paragraph("Breach Records", label_style))
            for bd in breach_details[:6]:
                sev   = (bd.get("severity") or "HIGH").upper()
                sev_c = RED if sev == "CRITICAL" else ORANGE
                tid   = safe(bd.get("technique_id", ""), 30)
                tname = safe(bd.get("technique_name", ""), 60)
                turn  = bd.get("turn", "?")
                vec   = safe(bd.get("attack_vector", ""), 250)
                btype = safe(bd.get("breach_type", ""), 50).replace("_", " ")
                atk   = safe(bd.get("attack_message_excerpt", ""), 200)
                resp  = safe(bd.get("response_excerpt", ""), 200)

                brows = [[
                    Paragraph(
                        f'<font color="{sev_c.hexval()}"><b>{sev} — {tid}: {tname}</b></font>'
                        f'<font color="{GRAY5.hexval()}"> (Turn {turn})</font>',
                        S(f"BH{turn}", fontSize=8, textColor=GRAY1,
                          fontName="Helvetica-Bold", leading=13))
                ]]
                for lbl, val in [
                    ("Attack Vector", vec),
                    ("Breach Type",   btype),
                    ("Attack Msg",    atk),
                    ("Response",      resp),
                ]:
                    if val:
                        brows.append([Paragraph(
                            f'<b>{lbl}:</b> <font color="{GRAY3.hexval()}">{val}</font>',
                            S(f"BR{turn}{lbl}", fontSize=7, textColor=GRAY3,
                              leading=12, wordWrap="CJK"))])

                bt = Table(
                    brows,
                    colWidths=[col(100)],
                    style=TableStyle([
                        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#FFF0F0")),
                        ("BACKGROUND",    (0, 1), (-1, -1), GRAY6),
                        ("TOPPADDING",    (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
                        ("RIGHTPADDING",  (0, 0), (-1, -1), 7),
                        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
                        ("LINEBELOW",     (0, 0), (-1, -2), 0.3, WHITE),
                    ]),
                )
                block.append(bt)
                block.append(sp(1.5))

        if attack_trace:
            block.append(sp(1))
            block.append(Paragraph("Phase 3 — Attack Timeline", label_style))
            atrows = [[
                Paragraph("<b>Turn</b>",           small_style),
                Paragraph("<b>Technique</b>",       small_style),
                Paragraph("<b>Classification</b>",  small_style),
                Paragraph("<b>Score</b>",           small_style),
            ]]
            for at in attack_trace[:20]:
                cls   = (at.get("classification") or "").upper()
                cls_c = RED if cls == "BREACH" else (ORANGE if cls == "SAFE_FAILURE" else GREEN)
                atrows.append([
                    Paragraph(str(at.get("turn", "")),               small_style),
                    Paragraph(safe(at.get("technique_id", ""), 30),  code_style),
                    Paragraph(f'<font color="{cls_c.hexval()}"><b>{cls}</b></font>', small_style),
                    Paragraph(str(at.get("score", "")),               small_style),
                ])
            att = Table(
                atrows,
                colWidths=[col(10), col(30), col(42), col(18)],
                style=HEADER_TABLE,
            )
            block.append(att)
            block.append(sp(1.5))

    # ─────────────────────────────────────────────────────────────────────────
    # Build story
    # ─────────────────────────────────────────────────────────────────────────
    story = []

    cd   = r.get("council_decision") or {}
    rec  = cd.get("final_recommendation", "N/A")
    cons = cd.get("consensus_level", "N/A")

    # ── Cover ─────────────────────────────────────────────────────────────────
    story.append(sp(10))
    story.append(Paragraph("UNICC AI Safety Council", cover_title))
    story.append(Paragraph("Full Assessment Report", cover_sub))
    story.append(sp(4))

    dec_color = decision_color(rec)
    story.append(Table(
        [[
            Paragraph(
                f'<font color="{dec_color.hexval()}"><b>{rec}</b></font>',
                S("Dec", fontSize=20, fontName="Helvetica-Bold", leading=26)),
            Paragraph(
                f"Consensus: {cons}",
                S("Cons", fontSize=10, textColor=GRAY5, leading=16)),
        ]],
        colWidths=[col(55), col(45)],
        style=TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), GRAY6),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING",   (0, 0), (-1, -1), 12),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]),
    ))
    story.append(sp(4))

    meta_items = [
        ("System",    r.get("system_name", r.get("agent_id", ""))),
        ("Agent ID",  r.get("agent_id", "")),
        ("Incident",  r.get("incident_id", "")),
        ("Timestamp", r.get("timestamp", "")[:19].replace("T", " ") + " UTC"),
    ]
    meta_rows = [
        [Paragraph(f"<b>{k}</b>", cover_meta), Paragraph(safe(v), cover_meta)]
        for k, v in meta_items if v
    ]
    if meta_rows:
        mt = Table(
            meta_rows,
            colWidths=[col(18), col(82)],
            style=TableStyle([
                ("TOPPADDING",    (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ]),
        )
        story.append(mt)

    story.append(hr())

    # ── Section 0: System Under Evaluation ───────────────────────────────────
    story.append(Paragraph("0. System Under Evaluation", h1_style))
    desc = r.get("system_description") or ""
    if desc:
        story.append(Paragraph(safe(desc, 1400), body_style))
    story.append(hr())

    # ── Section 1: Expert Analyses ────────────────────────────────────────────
    story.append(Paragraph("1. Expert Analyses &amp; Judgments", h1_style))

    expert_map = {
        "security":       ("Expert 1", "Security &amp; Adversarial Testing"),
        "governance":     ("Expert 2", "Governance &amp; Compliance"),
        "un_mission_fit": ("Expert 3", "UN Mission Fit"),
    }

    for key, (badge, title) in expert_map.items():
        er = (r.get("expert_reports") or {}).get(key, {})
        if not er:
            continue

        exp_rec = er.get("recommendation", "N/A")
        ec = decision_color(exp_rec)

        # ── expert header ────────────────────────────────────────────────────
        block = []
        block.append(Paragraph(
            f'<b>{badge}</b> — {title} '
            f'<font color="{ec.hexval()}"><b>[{exp_rec}]</b></font>',
            h2_style,
        ))

        if er.get("error"):
            block.append(Paragraph(f"⚠ Module error: {safe(er['error'])}", small_style))
        else:
            # dimension scores
            dim_scores = er.get("dimension_scores") or {}
            if dim_scores:
                block.append(Paragraph("Dimension Scores", label_style))
                score_rows = []
                for k, v in dim_scores.items():
                    label = k.replace("_", " ").title()
                    score_rows.append([
                        Paragraph(f"<b>{safe(label)}</b>", small_style),
                        Paragraph(str(v), small_style),
                    ])
                t = Table(
                    score_rows,
                    colWidths=[col(55), col(45)],
                    style=TableStyle([
                        ("BACKGROUND",    (0, 0), (-1, -1), GRAY6),
                        ("ROWBACKGROUNDS",(0, 0), (-1, -1), [GRAY6, colors.HexColor("#E8E8ED")]),
                        ("TOPPADDING",    (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
                        ("RIGHTPADDING",  (0, 0), (-1, -1), 7),
                        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                    ]),
                )
                block.append(t)
                block.append(sp(2))

            # key findings — rendered separately to avoid huge KeepTogether
            findings = er.get("key_findings") or []
            if findings:
                render_findings(block, findings)

            # narrative
            narrative = er.get("narrative") or ""
            if narrative:
                block.append(Paragraph("Narrative", label_style))
                block.append(Paragraph(safe(narrative, 900), body_style))
                block.append(sp(1))

            # compliance gaps / violations
            violations = er.get("un_principle_violations") or er.get("key_gaps") or []
            if violations:
                block.append(Paragraph("Compliance Gaps / Violations", label_style))
                for v in violations[:6]:
                    block.append(Paragraph(f"• {safe(str(v), 350)}", bullet_style))
                block.append(sp(1))

            # compliance findings table (Expert 2)
            compliance = er.get("compliance_findings") or {}
            if compliance:
                block.append(Paragraph("Compliance Findings", label_style))
                ICONS = {"PASS": "✓", "FAIL": "✗", "UNCLEAR": "?"}
                COLS  = {"PASS": GREEN, "FAIL": RED, "UNCLEAR": ORANGE}
                cf_rows = []
                for cf_k, cf_v in compliance.items():
                    icon = ICONS.get(str(cf_v).upper(), "·")
                    col_c = COLS.get(str(cf_v).upper(), GRAY5)
                    cf_rows.append([
                        Paragraph(cf_k.replace("_", " ").title(), small_style),
                        Paragraph(
                            f'<font color="{col_c.hexval()}"><b>{icon} {cf_v}</b></font>',
                            small_style),
                    ])
                if cf_rows:
                    cf_t = Table(
                        cf_rows,
                        colWidths=[col(65), col(35)],
                        style=TableStyle([
                            ("BACKGROUND",    (0, 0), (-1, -1), GRAY6),
                            ("ROWBACKGROUNDS",(0, 0), (-1, -1), [GRAY6, colors.HexColor("#E8E8ED")]),
                            ("TOPPADDING",    (0, 0), (-1, -1), 3),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                            ("LEFTPADDING",   (0, 0), (-1, -1), 7),
                            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                        ]),
                    )
                    block.append(cf_t)
                    block.append(sp(2))

            # ATLAS citations
            atlas = er.get("atlas_citations") or []
            if atlas:
                block.append(Paragraph("ATLAS Citations", label_style))
                for cite in atlas[:8]:
                    if isinstance(cite, dict):
                        cid   = safe(cite.get("id", ""), 30)
                        cname = safe(cite.get("name", ""), 70)
                        rel   = cite.get("relevance", "")
                        rel_s = f"  (rel: {rel:.2f})" if isinstance(rel, (int, float)) else ""
                        block.append(Paragraph(f"§ {cid} — {cname}{rel_s}", bullet_style))
                    else:
                        block.append(Paragraph(f"§ {safe(str(cite), 130)}", bullet_style))
                block.append(sp(1))

            # attack trail (Expert 1 only)
            if key == "security":
                render_attack_trail(block, er)

        # Use KeepTogether only for the header + first few elements;
        # render the rest normally to avoid overflow overlaps.
        story.append(KeepTogether(block[:4]))
        for elem in block[4:]:
            story.append(elem)
        story.append(sp(3))

    story.append(hr())

    # ── Section 2: Council Debate ─────────────────────────────────────────────
    story.append(Paragraph("2. Council Debate (Cross-Expert Critiques)", h1_style))

    critiques = r.get("critiques") or {}
    if isinstance(critiques, dict):
        critique_items = list(critiques.items())
    elif isinstance(critiques, list):
        critique_items = [(str(i), c) for i, c in enumerate(critiques)]
    else:
        critique_items = []

    for i, (ckey, cv) in enumerate(critique_items):
        if not isinstance(cv, dict):
            continue
        agrees      = cv.get("agrees", True)
        agree_label = "Agrees" if agrees else "Disagrees"
        agree_color = GREEN.hexval() if agrees else ORANGE.hexval()
        from_e      = safe(cv.get("from_expert", "").replace("_", " ").title(), 60)
        on_e        = safe(cv.get("on_expert",   "").replace("_", " ").title(), 60)

        block = []
        block.append(Paragraph(
            f'<b>Critique {i + 1}:</b> {from_e} → {on_e} '
            f'— <font color="{agree_color}"><b>{agree_label}</b></font>',
            h3_style,
        ))
        kp = safe(cv.get("key_point", ""), 500)
        if kp:
            block.append(Paragraph(f'<i>"{kp}"</i>', body_style))
        stance = safe(cv.get("stance", ""), 250)
        if stance:
            block.append(Paragraph(f"<b>Stance:</b> {stance}", small_style))
        for ev in (cv.get("evidence_references") or [])[:3]:
            block.append(Paragraph(f"§ {safe(ev, 220)}", bullet_style))

        story.append(KeepTogether(block))
        story.append(sp(1.5))

    story.append(hr())

    # ── Section 3: Expert Final Opinions & Arbitration ───────────────────────
    story.append(Paragraph("3. Expert Final Opinions &amp; Arbitration", h1_style))

    summary_rows = []
    for key, (badge, title) in expert_map.items():
        er      = (r.get("expert_reports") or {}).get(key, {})
        exp_rec = er.get("recommendation", "N/A")
        ec      = decision_color(exp_rec)
        summary_rows.append([
            Paragraph(f"<b>{badge}</b> — {title}", body_style),
            Paragraph(f'<font color="{ec.hexval()}"><b>{exp_rec}</b></font>', body_style),
        ])

    if summary_rows:
        t = Table(
            summary_rows,
            colWidths=[col(70), col(30)],
            style=TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), GRAY6),
                ("ROWBACKGROUNDS",(0, 0), (-1, -1), [GRAY6, colors.HexColor("#E8E8ED")]),
                ("TOPPADDING",    (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING",   (0, 0), (-1, -1), 9),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 9),
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ]),
        )
        story.append(t)

    story.append(sp(4))

    # Council decision box
    story.append(Paragraph("Council Decision", h2_style))
    dec_col = decision_color(rec)
    story.append(Table(
        [[
            Paragraph(
                f'<font color="{dec_col.hexval()}"><b>{rec}</b></font>',
                S("BigDec", fontSize=18, fontName="Helvetica-Bold", leading=24)),
            Paragraph(
                f"Consensus: <b>{cons}</b><br/>"
                f"Human Oversight: <b>{cd.get('human_oversight_required', '?')}</b><br/>"
                f"Blocks Deployment: <b>{cd.get('compliance_blocks_deployment', '?')}</b>",
                S("DecMeta", fontSize=9, textColor=GRAY3, leading=16)),
        ]],
        colWidths=[col(32), col(68)],
        style=TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), GRAY6),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING",   (0, 0), (-1, -1), 12),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]),
    ))
    story.append(sp(3))

    rationale = cd.get("rationale") or r.get("council_note") or ""
    if rationale:
        story.append(Paragraph("Rationale", label_style))
        story.append(Paragraph(safe(rationale, 1500), body_style))

    story.append(hr())
    story.append(Paragraph(
        "This report was generated by the UNICC AI Safety Council automated pipeline. "
        "All findings should be reviewed by qualified human evaluators before any deployment decision.",
        S("Footer", fontSize=8, textColor=GRAY5, alignment=TA_CENTER, leading=13),
    ))

    doc.build(story)
    return buf.getvalue()
