"""
frontend_api/markdown_renderer.py
───────────────────────────────────
Markdown export for CouncilReport dicts.
Extracted from main.py to keep route handlers thin.
"""
from __future__ import annotations


def report_to_markdown(r: dict) -> str:
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
        compliance_findings = val.get("compliance_findings")
        if compliance_findings and isinstance(compliance_findings, dict):
            lines.append("- compliance_findings:")
            for cf_key, cf_val in compliance_findings.items():
                icon = {"PASS": "✓", "FAIL": "✗", "UNCLEAR": "?"}.get(
                    str(cf_val).upper(), "·"
                )
                lines.append(f"  - {icon} {cf_key}: **{cf_val}**")
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
