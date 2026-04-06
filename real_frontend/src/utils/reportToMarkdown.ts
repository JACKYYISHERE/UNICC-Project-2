/**
 * Convert DetailedEvaluation to Markdown for download.
 * Handles structured [RISK]/[EVIDENCE]/[IMPACT]/[SCORE] findings
 * and Expert 1 live attack trail.
 */
import type { DetailedEvaluation, ExpertReport } from '../data/mockData'
import { citationToString } from './mapCouncilReport'

// ── Parse a structured finding string into its tagged sections ────────────────
function parseFinding(f: string): { risk: string; evidence: string; impact: string; score: string } | null {
  if (!f.includes('[RISK]') || !f.includes('[EVIDENCE]')) return null
  const extract = (tag: string, next: string) => {
    const re = new RegExp(`\\[${tag}\\]\\s*(.*?)(?=\\[${next}\\]|$)`, 's')
    return f.match(re)?.[1]?.trim() ?? ''
  }
  return {
    risk:     extract('RISK',     'EVIDENCE'),
    evidence: extract('EVIDENCE', 'IMPACT'),
    impact:   extract('IMPACT',   'SCORE'),
    score:    extract('SCORE',    '$'),
  }
}

// ── Render key findings section for one expert ────────────────────────────────
function renderFindings(report: ExpertReport): string[] {
  const lines: string[] = []
  lines.push(`#### Key Findings`)
  lines.push('')

  for (let i = 0; i < report.findings.length; i++) {
    const f = report.findings[i]
    const parsed = parseFinding(f)
    if (parsed) {
      lines.push(`**Finding ${i + 1}**`)
      lines.push('')
      lines.push(`> **[RISK]** ${parsed.risk}`)
      lines.push(`>`)
      lines.push(`> **[EVIDENCE]** ${parsed.evidence}`)
      if (parsed.impact) {
        lines.push(`>`)
        lines.push(`> **[IMPACT]** ${parsed.impact}`)
      }
      if (parsed.score) {
        lines.push(`>`)
        lines.push(`> **[SCORE]** ${parsed.score}`)
      }
      lines.push('')
    } else {
      lines.push(`- ${f}`)
    }
  }
  lines.push('')
  return lines
}

// ── Render Expert 1 live attack trail ─────────────────────────────────────────
function renderAttackTrail(report: ExpertReport): string[] {
  if (report.id !== 'security' || !report.attack_trace || report.attack_trace.length === 0) return []

  const lines: string[] = []
  lines.push(`#### Live Attack Trail`)
  lines.push('')
  lines.push('> Expert 1 ran in **Live Attack Mode** against a live target endpoint.')
  lines.push('')

  // Phase 0 fingerprint
  if (report.fingerprint) {
    const fp = report.fingerprint
    lines.push(`##### Phase 0 — Target Fingerprint`)
    lines.push('')
    lines.push(`| Property | Value |`)
    lines.push(`|----------|-------|`)
    lines.push(`| Output Format | \`${fp.output_format}\` |`)
    lines.push(`| Fail Behavior | \`${fp.fail_behavior}\` |`)
    lines.push(`| Stateful | ${fp.stateful ? '⚠️ Yes' : '✓ No'} |`)
    lines.push(`| Tool Exposure | ${fp.tool_exposure ? '⚠️ Yes' : '✓ No'} |`)
    lines.push(`| Pipeline Complexity | ${fp.pipeline_complexity} |`)
    if (fp.boosted_tags.length > 0) {
      lines.push(`| Adaptive Techniques Injected | ${fp.boosted_tags.join(', ')} |`)
    }
    lines.push('')
    if (fp.raw_notes.length > 0) {
      lines.push(`**Probe Notes:**`)
      for (const note of fp.raw_notes) {
        lines.push(`- ${note}`)
      }
      lines.push('')
    }
  }

  // Phase counters
  lines.push(`| Phase | Count |`)
  lines.push(`|-------|-------|`)
  lines.push(`| 🔍 Phase 1 — Probe | ${report.probe_trace?.length ?? 0} turns |`)
  lines.push(`| ⚠️ Phase 2 — Boundary | ${report.boundary_trace?.length ?? 0} turns |`)
  lines.push(`| ⚡ Phase 3 — Attack | ${report.attack_trace.length} turns |`)
  lines.push(`| 🧪 Standard Suite | ${report.standard_suite?.length ?? 0} tests |`)
  lines.push('')

  const breachTurns = report.attack_trace.filter(t => t.classification === 'BREACH')
  if (breachTurns.length > 0) {
    lines.push(`**⚠️ ${breachTurns.length} BREACH${breachTurns.length > 1 ? 'ES' : ''} CONFIRMED**`)
    lines.push('')
  }

  // LLM-structured breach records
  if (report.breach_details && report.breach_details.length > 0) {
    lines.push(`##### Breach Records`)
    lines.push('')
    for (const bd of report.breach_details) {
      lines.push(`###### 🔴 ${bd.severity ?? 'HIGH'} BREACH — ${bd.technique_id}: ${bd.technique_name} (Turn ${bd.turn})`)
      lines.push('')
      lines.push(`- **Attack Vector:** ${bd.attack_vector}`)
      lines.push(`- **Breach Type:** ${bd.breach_type?.replace(/_/g, ' ')}`)
      if (bd.attack_message_excerpt) {
        lines.push(`- **Attack Message:**`)
        lines.push(`  \`\`\``)
        lines.push(`  ${bd.attack_message_excerpt}`)
        lines.push(`  \`\`\``)
      }
      if (bd.response_excerpt) {
        lines.push(`- **Target Response:**`)
        lines.push(`  \`\`\``)
        lines.push(`  ${bd.response_excerpt}`)
        lines.push(`  \`\`\``)
      }
      lines.push('')
    }
  }

  // Full attack turn timeline
  if (report.attack_trace.length > 0) {
    lines.push(`##### Phase 3 — Attack Timeline`)
    lines.push('')
    lines.push(`| Turn | Technique | Classification | Score |`)
    lines.push(`|------|-----------|----------------|-------|`)
    for (const t of report.attack_trace) {
      const flag = t.classification === 'BREACH' ? '🔴' : t.classification === 'SAFE_FAILURE' ? '🟡' : '🟢'
      lines.push(`| ${t.turn} | \`${t.technique_id}\` | ${flag} ${t.classification} | ${t.score}/10 |`)
    }
    lines.push('')

    for (const t of report.attack_trace) {
      const isBreach = t.classification === 'BREACH'
      lines.push(`**Turn ${t.turn}** — \`${t.technique_id}\` ${isBreach ? '⚠️ BREACH' : ''}`)
      lines.push('')
      lines.push(`*Attack:*`)
      lines.push(`\`\`\``)
      lines.push(t.message_sent)
      lines.push(`\`\`\``)
      lines.push(`*Response:*`)
      lines.push(`\`\`\``)
      lines.push(t.response)
      lines.push(`\`\`\``)
      if (t.evidence) {
        lines.push(`*Evidence:* ${t.evidence}`)
      }
      lines.push('')
    }
  }

  // Standard Suite summary
  if (report.standard_suite && report.standard_suite.length > 0) {
    lines.push(`##### Standard Suite Results`)
    lines.push('')
    const cats = ['B1_bias', 'B2_harmful', 'B3_privacy', 'B4_transparency', 'B5_un_specific']
    lines.push(`| Category | Result |`)
    lines.push(`|----------|--------|`)
    for (const cat of cats) {
      const tests = report.standard_suite.filter(t => t.category === cat)
      const result = tests.every(t => t.result === 'PASS') ? '✅ PASS'
        : tests.some(t => t.result === 'FAIL') ? '❌ FAIL' : '⚠️ PARTIAL'
      lines.push(`| ${cat.replace('_', ' ').toUpperCase()} | ${result} |`)
    }
    lines.push('')
  }

  return lines
}

export function evaluationToMarkdown(e: DetailedEvaluation): string {
  const date = new Date(e.submitted_at).toLocaleString('en-US', {
    year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })

  const lines: string[] = []
  lines.push(`# UNICC AI Safety Council — Full Assessment Report`)
  lines.push('')
  lines.push(`## System Under Evaluation`)
  lines.push('')
  lines.push(`- **Name:** ${e.system_name}`)
  lines.push(`- **Agent ID:** ${e.agent_id}`)
  lines.push(`- **Category:** ${e.category}`)
  lines.push(`- **Submitted:** ${date}`)
  if (e.incident_id) lines.push(`- **Incident ID:** ${e.incident_id}`)
  lines.push('')
  lines.push(`### Description`)
  lines.push('')
  lines.push(e.description)
  lines.push('')
  lines.push('---')
  lines.push('')
  lines.push('## Part 1 — Expert Analyses')
  lines.push('')

  for (const r of e.expert_reports) {
    const isLive = r.id === 'security' && r.attack_trace && r.attack_trace.length > 0
    lines.push(`### ${r.icon} ${r.title}${isLive ? ' ⚡ *(Live Attack Mode)*' : ''}`)
    lines.push('')
    lines.push(`**Recommendation:** \`${r.recommendation}\`  |  *${r.elapsed}s elapsed*`)
    lines.push('')
    lines.push(`#### Dimension Scores`)
    lines.push('')
    lines.push(`| Dimension | Score |`)
    lines.push(`|-----------|-------|`)
    for (const s of r.scores) {
      const bar = '█'.repeat(s.value) + '░'.repeat(s.max - s.value)
      lines.push(`| ${s.label} | ${bar} ${s.value}/${s.max} |`)
    }
    lines.push('')

    // Structured findings
    lines.push(...renderFindings(r))

    lines.push(`#### Regulatory / Framework References`)
    lines.push('')
    for (const ref of r.framework_refs) {
      lines.push(`- § ${citationToString(ref)}`)
    }
    lines.push('')

    // Live attack trail
    lines.push(...renderAttackTrail(r))
  }

  lines.push('---')
  lines.push('')
  lines.push('## Part 2 — Council Debate')
  lines.push('')

  for (let i = 0; i < e.council_critiques.length; i++) {
    const c = e.council_critiques[i]
    lines.push(`### Critique ${i + 1}: ${c.from} → ${c.on}`)
    lines.push('')
    lines.push(`**${c.agrees ? '✅ Agrees' : '❌ Disagrees'}** | Divergence: \`${c.divergence_type.replace(/_/g, ' ')}\``)
    lines.push('')
    lines.push(`> "${c.key_point}"`)
    lines.push('')
    lines.push(`**Stance:** ${c.stance}`)
    lines.push('')
    if (c.evidence.length > 0) {
      lines.push(`**Evidence:**`)
      for (const ev of c.evidence) {
        lines.push(`- § ${ev}`)
      }
    }
    lines.push('')
  }

  lines.push('---')
  lines.push('')
  lines.push('## Part 3 — Expert Final Opinions')
  lines.push('')
  lines.push(`| Expert | Recommendation |`)
  lines.push(`|--------|----------------|`)
  for (const r of e.expert_reports) {
    lines.push(`| ${r.icon} ${r.shortTitle} | \`${r.recommendation}\` |`)
  }
  lines.push('')

  lines.push('---')
  lines.push('')
  lines.push('## Part 4 — Arbitration Outcome')
  lines.push('')
  lines.push(`**Council Decision:** \`${e.decision}\`  |  Consensus: \`${e.consensus}\``)
  lines.push('')
  lines.push(`### Rationale`)
  lines.push('')
  lines.push(e.final_rationale)
  lines.push('')

  if (e.key_conditions.length > 0) {
    lines.push(`### Required Actions`)
    lines.push('')
    for (let i = 0; i < e.key_conditions.length; i++) {
      lines.push(`${i + 1}. ${e.key_conditions[i]}`)
    }
    lines.push('')
  }

  lines.push('---')
  lines.push('')
  lines.push('*Generated by UNICC AI Safety Council. All findings should be reviewed by qualified human evaluators before any deployment decision.*')
  return lines.join('\n')
}
