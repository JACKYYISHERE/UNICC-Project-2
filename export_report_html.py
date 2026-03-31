#!/usr/bin/env python3
"""
export_report_html.py
Exports a council evaluation report as a fully self-contained HTML file.
No server required — the HTML embeds all data and renders entirely in-browser.

Usage:
    python3 export_report_html.py                          # export latest report
    python3 export_report_html.py inc_20260330_xxx_abc123  # export specific incident
    python3 export_report_html.py --list                   # list available incidents
"""

import argparse
import json
import sys
import textwrap
from pathlib import Path

import requests

API = "http://localhost:8100"


# ── Fetch helpers ─────────────────────────────────────────────────────────────

def list_incidents(limit: int = 30) -> list:
    r = requests.get(f"{API}/evaluations?limit={limit}&offset=0", timeout=10)
    r.raise_for_status()
    return r.json().get("items", [])


def fetch_report(incident_id: str) -> dict:
    r = requests.get(f"{API}/evaluations/{incident_id}", timeout=10)
    r.raise_for_status()
    return r.json()


# ── HTML template ─────────────────────────────────────────────────────────────

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title} — UNICC AI Safety Council Report</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
    .finding-card {{ break-inside: avoid; }}
    @media print {{
      .no-print {{ display: none !important; }}
      body {{ background: white; }}
    }}
  </style>
</head>
<body class="bg-gray-50 text-gray-900">

<div id="root"></div>

<script>
// ── Embedded report data ────────────────────────────────────────────────────
const REPORT = {report_json};

// ── Utilities ────────────────────────────────────────────────────────────────
const titleCase = k => k.replace(/_/g, ' ').replace(/\\b\\w/g, c => c.toUpperCase());

const fmtDate = iso => new Date(iso).toLocaleString('en-US', {{
  year: 'numeric', month: 'short', day: 'numeric',
  hour: '2-digit', minute: '2-digit',
}});

const complianceToScore = {{ PASS: 1, UNCLEAR: 3, FAIL: 5 }};

function scoreEntries(r) {{
  const ds = r?.dimension_scores;
  if (ds && typeof ds === 'object' && Object.values(ds).some(v => typeof v === 'number')) {{
    return Object.entries(ds).slice(0, 8).map(([k, v]) => ({{
      label: titleCase(k), value: Number(v) || 0, max: 5,
    }}));
  }}
  const cf = r?.compliance_findings;
  if (cf && typeof cf === 'object' && Object.keys(cf).length > 0) {{
    return Object.entries(cf).map(([k, v]) => ({{
      label: titleCase(k),
      value: complianceToScore[String(v).toUpperCase()] ?? 3,
      max: 5,
    }}));
  }}
  const h = r?.council_handoff;
  if (h && typeof h === 'object') {{
    const keys = ['privacy_score', 'transparency_score', 'bias_score'].filter(k => h[k] != null);
    if (keys.length) return keys.map(k => ({{
      label: titleCase(k.replace('_score', '')),
      value: Number(h[k]) || 0, max: 5,
    }}));
  }}
  return [{{ label: 'Overall', value: 3, max: 5 }}];
}}

function extractFindings(r) {{
  if (Array.isArray(r?.key_findings) && r.key_findings.length)
    return r.key_findings.map(x => String(x));
  if (Array.isArray(r?.key_gaps) && r.key_gaps.length)
    return r.key_gaps.slice(0, 8).map(g => String(g?.gap ?? g?.description ?? g));
  if (typeof r?.recommendation_rationale === 'string' && r.recommendation_rationale.trim())
    return [r.recommendation_rationale];
  return ['No detailed findings returned.'];
}}

function extractRefs(r) {{
  if (Array.isArray(r?.framework_refs) && r.framework_refs.length) return r.framework_refs;
  if (Array.isArray(r?.regulatory_citations) && r.regulatory_citations.length) return r.regulatory_citations;
  return [];
}}

// ── Render helpers ────────────────────────────────────────────────────────────

function recConfig(rec) {{
  const k = String(rec || '').toUpperCase();
  const map = {{
    APPROVE: {{ label: 'Approve', bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200', dot: 'bg-emerald-500' }},
    REVIEW:  {{ label: 'Review',  bg: 'bg-amber-50',   text: 'text-amber-700',   border: 'border-amber-200',  dot: 'bg-amber-500' }},
    REJECT:  {{ label: 'Reject',  bg: 'bg-red-50',     text: 'text-red-700',     border: 'border-red-200',    dot: 'bg-red-500' }},
  }};
  return map[k] ?? map.REVIEW;
}}

function recPill(rec, large = false) {{
  const c = recConfig(rec);
  const sz = large ? 'px-4 py-1.5 text-sm' : 'px-2.5 py-0.5 text-xs';
  return `<span class="inline-flex items-center gap-1.5 rounded-full border font-semibold ${{c.bg}} ${{c.text}} ${{c.border}} ${{sz}}">
    <span class="w-1.5 h-1.5 rounded-full shrink-0 ${{c.dot}}"></span>
    ${{c.label}}
  </span>`;
}}

function scoreBar(label, value, max) {{
  const pct = (value / max) * 100;
  const color = pct <= 20 ? 'bg-emerald-500' : pct <= 60 ? 'bg-amber-500' : 'bg-red-500';
  const tcolor = pct <= 20 ? 'text-emerald-700' : pct <= 60 ? 'text-amber-700' : 'text-red-700';
  return `
    <div class="space-y-1 mb-3">
      <div class="flex justify-between items-center">
        <span class="text-xs text-gray-500">${{label}}</span>
        <span class="text-xs font-bold ${{tcolor}}">${{value}}/${{max}}</span>
      </div>
      <div class="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
        <div class="h-full rounded-full ${{color}}" style="width:${{pct}}%"></div>
      </div>
    </div>`;
}}

function findingCard(text, index) {{
  const isAudit = text.includes('[RISK]') && text.includes('[EVIDENCE]');
  if (isAudit) {{
    const extract = (tag, next) => {{
      const re = new RegExp(`\\\\[${{tag}}\\\\]\\\\s*(.*?)(?=\\\\[${{next}}\\\\]|$)`, 's');
      return (text.match(re)?.[1] ?? '').trim();
    }};
    const risk  = extract('RISK',     'EVIDENCE');
    const evid  = extract('EVIDENCE', 'IMPACT');
    const imp   = extract('IMPACT',   'SCORE');
    const score = extract('SCORE',    '$');
    return `
      <div class="finding-card rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden mb-3">
        <div class="px-4 py-2 bg-gray-50 border-b border-gray-100">
          <span class="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Finding ${{index + 1}}</span>
        </div>
        <div class="p-4 space-y-3">
          <div class="flex gap-2.5">
            <span class="shrink-0 px-1.5 py-0.5 rounded text-[9px] font-bold bg-red-50 text-red-600 uppercase tracking-wide border border-red-100 self-start mt-0.5">Risk</span>
            <p class="text-xs font-medium text-gray-800 leading-relaxed">${{risk}}</p>
          </div>
          <div class="flex gap-2.5">
            <span class="shrink-0 px-1.5 py-0.5 rounded text-[9px] font-bold bg-blue-50 text-blue-600 uppercase tracking-wide border border-blue-100 self-start mt-0.5">Evidence</span>
            <p class="text-xs text-gray-600 leading-relaxed">${{evid}}</p>
          </div>
          ${{imp ? `<div class="flex gap-2.5">
            <span class="shrink-0 px-1.5 py-0.5 rounded text-[9px] font-bold bg-orange-50 text-orange-600 uppercase tracking-wide border border-orange-100 self-start mt-0.5">Impact</span>
            <p class="text-xs text-gray-600 leading-relaxed">${{imp}}</p>
          </div>` : ''}}
          ${{score ? `<div class="flex gap-2.5">
            <span class="shrink-0 px-1.5 py-0.5 rounded text-[9px] font-bold bg-purple-50 text-purple-600 uppercase tracking-wide border border-purple-100 self-start mt-0.5">Score</span>
            <p class="text-xs text-gray-500 leading-relaxed italic">${{score}}</p>
          </div>` : ''}}
        </div>
      </div>`;
  }}
  return `
    <div class="finding-card flex gap-2.5 rounded-xl border border-gray-100 bg-white p-4 mb-3">
      <span class="shrink-0 w-5 h-5 rounded-full bg-red-50 text-red-500 text-[10px] font-bold flex items-center justify-center mt-0.5">${{index + 1}}</span>
      <p class="text-xs text-gray-700 leading-relaxed">${{text}}</p>
    </div>`;
}}

// ── Expert section ────────────────────────────────────────────────────────────

const EXPERT_META = {{
  security:       {{ icon: '🛡',  label: 'Security & Adversarial Robustness',  accent: 'border-red-200 bg-red-50/40' }},
  governance:     {{ icon: '⚖️', label: 'Governance & Regulatory Compliance', accent: 'border-violet-200 bg-violet-50/40' }},
  un_mission_fit: {{ icon: '🌐', label: 'UN Mission Fit & Human Rights',       accent: 'border-sky-200 bg-sky-50/40' }},
}};

function expertSection(key, report) {{
  const meta     = EXPERT_META[key] ?? {{ icon: '◈', label: key, accent: 'border-gray-200' }};
  const scores   = scoreEntries(report);
  const findings = extractFindings(report);
  const refs     = extractRefs(report);
  const rec      = String(report?.recommendation ?? report?.overall_compliance ?? 'REVIEW');

  return `
    <section class="rounded-2xl border-2 ${{meta.accent}} overflow-hidden mb-6">
      <div class="px-6 py-4 flex items-center justify-between border-b border-black/5">
        <div class="flex items-center gap-3">
          <span class="text-2xl">${{meta.icon}}</span>
          <div>
            <h3 class="font-bold text-gray-900 text-sm">${{meta.label}}</h3>
            ${{report?.risk_tier ? `<span class="text-xs text-gray-400">Risk tier: ${{report.risk_tier}}</span>` : ''}}
          </div>
        </div>
        ${{recPill(rec)}}
      </div>
      <div class="p-6 grid grid-cols-2 gap-8">
        <div>
          <p class="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-4">Dimension Scores</p>
          ${{scores.map(s => scoreBar(s.label, s.value, s.max)).join('')}}
          ${{report?.recommendation_rationale ? `
            <div class="mt-5 p-3 rounded-xl bg-white/70 border border-black/5">
              <p class="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-2">Rationale Summary</p>
              <p class="text-xs text-gray-600 leading-relaxed">${{report.recommendation_rationale}}</p>
            </div>` : ''}}
          ${{report?.narrative && !report?.recommendation_rationale ? `
            <div class="mt-5 p-3 rounded-xl bg-white/70 border border-black/5">
              <p class="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-2">Narrative</p>
              <p class="text-xs text-gray-600 leading-relaxed">${{report.narrative}}</p>
            </div>` : ''}}
          ${{refs.length > 0 ? `
            <div class="mt-5">
              <p class="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-2">Regulatory References</p>
              ${{refs.slice(0, 6).map(ref => `
                <div class="flex items-start gap-1.5 text-xs text-gray-500 mb-1.5">
                  <span class="text-blue-400 shrink-0">§</span><span>${{ref}}</span>
                </div>`).join('')}}
              ${{refs.length > 6 ? `<p class="text-xs text-gray-400 italic">+ ${{refs.length - 6}} more</p>` : ''}}
            </div>` : ''}}
        </div>
        <div>
          <p class="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-4">Key Findings · ${{findings.length}}</p>
          ${{findings.map((f, i) => findingCard(f, i)).join('')}}
        </div>
      </div>
    </section>`;
}}

// ── Critique card ─────────────────────────────────────────────────────────────

const EXPERT_LABEL = {{
  security_adversarial:  {{ short: 'Security',  color: 'bg-red-50 text-red-700 border-red-200' }},
  governance_compliance: {{ short: 'Governance', color: 'bg-violet-50 text-violet-700 border-violet-200' }},
  un_mission_fit:        {{ short: 'UN Mission', color: 'bg-sky-50 text-sky-700 border-sky-200' }},
}};

function critiqueCard(c) {{
  const from = EXPERT_LABEL[c.from_expert] ?? {{ short: c.from_expert ?? '?', color: 'bg-gray-100 text-gray-600 border-gray-200' }};
  const on   = EXPERT_LABEL[c.on_expert]   ?? {{ short: c.on_expert   ?? '?', color: 'bg-gray-100 text-gray-600 border-gray-200' }};
  return `
    <div class="rounded-xl border border-gray-200 bg-white shadow-sm p-5 space-y-3">
      <div class="flex items-center gap-2 flex-wrap">
        <span class="px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${{from.color}}">${{from.short}}</span>
        <span class="text-gray-400 text-xs">reviewed</span>
        <span class="px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${{on.color}}">${{on.short}}</span>
        <span class="ml-auto">${{c.agrees
          ? '<span class="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">Agrees</span>'
          : '<span class="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-red-50 text-red-700 border border-red-200">Disagrees</span>'}}</span>
      </div>
      <p class="text-xs text-gray-700 leading-relaxed italic">"${{c.key_point ?? ''}}"</p>
      ${{c.stance ? `<p class="text-xs text-gray-500 leading-relaxed">${{c.stance}}</p>` : ''}}
      ${{Array.isArray(c.evidence_references) && c.evidence_references.length > 0 ? `
        <div class="space-y-1 pt-1 border-t border-gray-50">
          ${{c.evidence_references.slice(0, 3).map(ev => `
            <div class="flex items-start gap-1.5 text-xs text-gray-400">
              <span class="text-blue-400 shrink-0">§</span><span>${{ev}}</span>
            </div>`).join('')}}
        </div>` : ''}}
    </div>`;
}}

// ── Main render ───────────────────────────────────────────────────────────────

function render() {{
  const R = REPORT;
  const decision      = R.council_decision ?? {{}};
  const finalRec      = String(decision.final_recommendation ?? 'REVIEW');
  const consensus     = String(decision.consensus_level ?? '');
  const rationale     = String(decision.rationale ?? R.council_note ?? '');
  const disagreements = Array.isArray(decision.disagreements) ? decision.disagreements : [];
  const critiques     = Object.values(R.critiques ?? {{}});
  const expertKeys    = ['security', 'governance', 'un_mission_fit'];

  const gradient = finalRec === 'APPROVE' ? 'from-emerald-500 to-teal-500'
                 : finalRec === 'REJECT'  ? 'from-red-500 to-rose-500'
                 : 'from-amber-400 to-orange-400';

  const expertRecs = expertKeys.map(k => {{
    const meta = EXPERT_META[k];
    const rec  = String((R.expert_reports?.[k])?.recommendation ?? 'REVIEW');
    return `
      <div class="flex items-center justify-between p-3 rounded-xl bg-white border border-gray-200 shadow-sm">
        <div class="flex items-center gap-2">
          <span class="text-xl">${{meta?.icon}}</span>
          <span class="text-xs font-medium text-gray-600">${{(meta?.label ?? '').split('&')[0].trim()}}</span>
        </div>
        ${{recPill(rec)}}
      </div>`;
  }}).join('');

  document.getElementById('root').innerHTML = `
    <!-- Sticky top bar -->
    <div class="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-gray-200">
      <div class="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
        <span class="text-sm font-semibold text-gray-700 truncate max-w-xs">${{R.system_name ?? R.agent_id}}</span>
        <div class="flex items-center gap-3">
          ${{recPill(finalRec)}}
          <span class="text-xs text-gray-400">${{fmtDate(R.timestamp)}}</span>
          <button onclick="window.print()" class="no-print ml-2 px-3 py-1.5 rounded-lg bg-gray-100 text-xs font-semibold text-gray-600 hover:bg-gray-200 transition-colors">Print / Save PDF</button>
        </div>
      </div>
    </div>

    <div class="max-w-5xl mx-auto px-6 py-10 space-y-14">

      <!-- Hero -->
      <section class="space-y-5">
        <div class="h-1 w-16 rounded-full bg-gradient-to-r ${{gradient}}"></div>
        <div>
          <h1 class="text-3xl font-bold text-gray-900 leading-tight">${{R.system_name ?? R.agent_id}}</h1>
          <p class="text-sm text-gray-400 mt-1">${{R.incident_id}} · ${{fmtDate(R.timestamp)}}</p>
        </div>
        <div class="flex flex-wrap items-center gap-3">
          ${{recPill(finalRec, true)}}
          ${{consensus ? `<span class="px-3 py-1 rounded-full bg-gray-100 text-xs font-semibold text-gray-600">${{consensus}} consensus</span>` : ''}}
          ${{decision.human_oversight_required ? `<span class="px-3 py-1 rounded-full bg-amber-50 text-amber-700 text-xs font-semibold border border-amber-200">Human oversight required</span>` : ''}}
          ${{decision.compliance_blocks_deployment ? `<span class="px-3 py-1 rounded-full bg-red-50 text-red-700 text-xs font-semibold border border-red-200">Blocks deployment</span>` : ''}}
        </div>
        <div class="grid grid-cols-3 gap-3">${{expertRecs}}</div>
      </section>

      <!-- System description -->
      ${{R.system_description ? `
        <section>
          <h2 class="text-lg font-bold text-gray-900 mb-4">System Under Evaluation</h2>
          <div class="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <p class="text-sm text-gray-700 leading-relaxed">${{R.system_description}}</p>
          </div>
        </section>` : ''}}

      <!-- Expert analyses -->
      <section>
        <h2 class="text-lg font-bold text-gray-900 mb-6">Expert Analyses</h2>
        ${{expertKeys.map(k => R.expert_reports?.[k] ? expertSection(k, R.expert_reports[k]) : '').join('')}}
      </section>

      <!-- Critiques -->
      ${{critiques.length > 0 ? `
        <section>
          <h2 class="text-lg font-bold text-gray-900 mb-4">Cross-Expert Critiques <span class="text-base font-normal text-gray-400">· ${{critiques.length}} filed</span></h2>
          <div class="grid grid-cols-2 gap-4">
            ${{critiques.map(c => critiqueCard(c)).join('')}}
          </div>
        </section>` : ''}}

      <!-- Disagreements -->
      ${{disagreements.length > 0 ? `
        <section>
          <h2 class="text-lg font-bold text-gray-900 mb-4">Score Disagreements</h2>
          <div class="space-y-2">
            ${{disagreements.map(d => `
              <div class="flex items-start gap-3 p-3 rounded-xl bg-amber-50 border border-amber-200">
                <span class="shrink-0 w-5 h-5 rounded-full bg-amber-500 text-white text-[10px] font-bold flex items-center justify-center mt-0.5">!</span>
                <div>
                  <p class="text-xs font-semibold text-amber-800 capitalize">${{d.dimension}} — ${{String(d.type ?? '').replace(/_/g, ' ')}}</p>
                  <p class="text-xs text-amber-700 leading-relaxed mt-0.5">${{d.description}}</p>
                  ${{d.values ? `<div class="flex gap-2 mt-1.5 flex-wrap">
                    ${{Object.entries(d.values).map(([k,v]) => `<span class="text-[10px] text-amber-600 bg-amber-100 px-1.5 py-0.5 rounded">${{k.replace(/_/g,' ')}}: ${{v}}</span>`).join('')}}
                  </div>` : ''}}
                </div>
              </div>`).join('')}}
          </div>
        </section>` : ''}}

      <!-- Final decision -->
      <section>
        <h2 class="text-lg font-bold text-gray-900 mb-4">Final Decision & Rationale</h2>
        <div class="rounded-2xl border-2 p-6 space-y-4
          ${{finalRec === 'APPROVE' ? 'border-emerald-200 bg-emerald-50/50'
           : finalRec === 'REJECT'  ? 'border-red-200 bg-red-50/50'
           : 'border-amber-200 bg-amber-50/50'}}">
          <div class="flex items-center gap-3 flex-wrap">
            ${{recPill(finalRec, true)}}
            ${{consensus ? `<span class="text-sm text-gray-500">${{consensus}} consensus among three experts</span>` : ''}}
          </div>
          <pre class="text-xs text-gray-600 leading-relaxed whitespace-pre-wrap font-sans">${{rationale}}</pre>
        </div>
      </section>

      <!-- Footer -->
      <footer class="pt-6 border-t border-gray-100 flex items-center justify-between text-xs text-gray-400">
        <span>UNICC AI Safety Council</span>
        <span>${{R.incident_id}}</span>
      </footer>

    </div>
  `;
}}

render();
</script>
</body>
</html>
"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Export a council report as self-contained HTML.")
    parser.add_argument("incident_id", nargs="?", help="Incident ID (default: latest)")
    parser.add_argument("--list", action="store_true", help="List available incidents")
    parser.add_argument("--out", default=None, help="Output path (default: auto-named in ./exports/)")
    args = parser.parse_args()

    try:
        incidents = list_incidents(50)
    except Exception as e:
        print(f"ERROR: Cannot reach API at {API} — is the backend running?\n  {e}", file=sys.stderr)
        sys.exit(1)

    if args.list:
        print(f"{'Incident ID':<55} {'System':<40} {'Decision'}")
        print("─" * 105)
        for item in incidents:
            print(f"{item['incident_id']:<55} {item['system_name'][:38]:<40} {item.get('decision','?')}")
        return

    if args.incident_id:
        incident_id = args.incident_id
    elif incidents:
        incident_id = incidents[0]["incident_id"]
        print(f"No incident_id provided — using latest: {incident_id}")
    else:
        print("No evaluations found in database.", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching report: {incident_id} …")
    try:
        report = fetch_report(incident_id)
    except Exception as e:
        print(f"ERROR fetching report: {e}", file=sys.stderr)
        sys.exit(1)

    system_name = report.get("system_name") or report.get("agent_id") or "report"
    safe_name   = "".join(c if c.isalnum() or c in "-_" else "_" for c in system_name)[:40]

    out_dir = Path("exports")
    out_dir.mkdir(exist_ok=True)

    out_path = Path(args.out) if args.out else out_dir / f"{incident_id}_{safe_name}.html"

    report_json = json.dumps(report, ensure_ascii=False, indent=None)
    html = HTML_TEMPLATE.format(
        title=system_name,
        report_json=report_json,
    )

    out_path.write_text(html, encoding="utf-8")
    size_kb = out_path.stat().st_size / 1024
    print(f"✓ Exported: {out_path}  ({size_kb:.1f} KB)")
    print(f"  Open in browser or send as a file attachment.")


if __name__ == "__main__":
    main()
