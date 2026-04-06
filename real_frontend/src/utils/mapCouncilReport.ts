import type { CouncilReportResponse } from '../api/client'
import type { DetailedEvaluation, ExpertReport, Recommendation, Consensus } from '../data/mockData'

const toRecommendation = (v: unknown): Recommendation => {
  const s = String(v ?? '').toUpperCase()
  if (s === 'APPROVE' || s === 'PASS') return 'APPROVE'
  if (s === 'REJECT' || s === 'FAIL') return 'REJECT'
  return 'REVIEW'
}

const toConsensus = (v: unknown): Consensus => {
  const s = String(v ?? '').toUpperCase()
  if (s === 'FULL') return 'FULL'
  if (s === 'PARTIAL') return 'PARTIAL'
  return 'NONE'
}

const titleCase = (k: string) =>
  k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

// PASS=1 (green), UNCLEAR=3 (amber), FAIL=5 (red) — aligns with Expert 1's 1=low risk scale
const complianceToScore: Record<string, number> = { PASS: 1, UNCLEAR: 3, FAIL: 5 }

const scoreEntries = (r: any): { label: string; value: number; max: number }[] => {
  // Expert 1 / Expert 3: numeric dimension_scores
  const ds = r?.dimension_scores
  if (ds && typeof ds === 'object' && Object.values(ds).some(v => typeof v === 'number')) {
    return Object.entries(ds).slice(0, 8).map(([k, v]) => ({
      label: titleCase(k),
      value: Number(v) || 0,
      max: 5,
    }))
  }
  // Expert 2: compliance_findings with PASS/FAIL/UNCLEAR strings
  const cf = r?.compliance_findings
  if (cf && typeof cf === 'object' && Object.keys(cf).length > 0) {
    return Object.entries(cf).map(([k, v]) => ({
      label: titleCase(k),
      value: complianceToScore[String(v).toUpperCase()] ?? 3,
      max: 5,
    }))
  }
  // Fallback: council_handoff numeric scores
  const h = r?.council_handoff
  if (h && typeof h === 'object') {
    const keys = ['privacy_score', 'transparency_score', 'bias_score'].filter(k => h[k] != null)
    if (keys.length) return keys.map(k => ({
      label: titleCase(k.replace('_score', '')),
      value: Number(h[k]) || 0,
      max: 5,
    }))
  }
  return [{ label: 'Overall', value: 3, max: 5 }]
}

const extractFindings = (r: any): string[] => {
  if (Array.isArray(r?.key_findings) && r.key_findings.length) {
    return r.key_findings.map((x: unknown) => String(x))
  }
  if (Array.isArray(r?.key_gaps) && r.key_gaps.length) {
    return r.key_gaps.slice(0, 8).map((g: any) => String(g?.gap ?? g?.description ?? g))
  }
  if (typeof r?.recommendation_rationale === 'string' && r.recommendation_rationale.trim()) {
    return [r.recommendation_rationale]
  }
  return ['No detailed findings returned.']
}

/** Normalise any citation item (string or rich object) to a display string. */
export const citationToString = (c: any): string => {
  if (typeof c === 'string') return c
  if (!c || typeof c !== 'object') return String(c)
  // Expert 2 rich object: { framework, article, relevance, excerpt }
  if (c.article) {
    const fw = c.framework ? `${c.framework} | ` : ''
    const rel = c.relevance != null ? ` (relevance: ${c.relevance})` : ''
    return `${fw}${c.article}${rel}`
  }
  // Expert 1 ATLAS object: { id, name, relevance }
  if (c.id && c.name) return `${c.id} — ${c.name}${c.relevance != null ? ` (relevance: ${c.relevance})` : ''}`
  // Generic fallback
  return c.name ?? c.id ?? c.title ?? JSON.stringify(c)
}

const extractRefs = (r: any): string[] => {
  const normalise = (arr: any[]) => arr.map(citationToString)
  if (Array.isArray(r?.framework_refs) && r.framework_refs.length) return normalise(r.framework_refs)
  if (Array.isArray(r?.regulatory_citations) && r.regulatory_citations.length) return normalise(r.regulatory_citations)
  if (Array.isArray(r?.evidence_references) && r.evidence_references.length) return normalise(r.evidence_references)
  // Expert 2 fallback: raw retrieved articles from ChromaDB
  if (Array.isArray(r?.retrieved_articles) && r.retrieved_articles.length) return normalise(r.retrieved_articles)
  // Expert 3: UN principle violations used as references
  if (Array.isArray(r?.un_principle_violations) && r.un_principle_violations.length)
    return normalise(r.un_principle_violations)
  // Expert 1: ATLAS technique citations
  if (Array.isArray(r?.atlas_citations) && r.atlas_citations.length) return normalise(r.atlas_citations)
  return []
}

// ── Human-readable rationale builder ─────────────────────────────────────────

const expertFullName: Record<string, string> = {
  security:      'Security Expert',
  governance:    'Governance Expert',
  un_mission_fit:'UN Mission Expert',
}

const dimensionLabel: Record<string, string> = {
  privacy:     'Privacy',
  bias:        'Bias & Fairness',
  transparency:'Transparency',
  harmfulness: 'Harmfulness',
  deception:   'Deception',
  legal:       'Legal Compliance',
  societal:    'Societal Risk',
}

const dimensionExplainer: Record<string, { security: string; governance: string; un_mission_fit: string }> = {
  privacy: {
    security:      'adversarial testing of whether privacy controls can be bypassed technically',
    governance:    'regulatory compliance with GDPR and data minimisation obligations',
    un_mission_fit:'whether data practices meet humanitarian beneficiary protection standards',
  },
  bias: {
    security:      'whether adversarial prompts can trigger discriminatory or skewed outputs',
    governance:    'regulatory requirements for bias testing and fairness documentation',
    un_mission_fit:'alignment with UN principles of non-discrimination and equal treatment',
  },
  transparency: {
    security:      'whether the system exposes its reasoning to potential manipulation',
    governance:    'transparency obligations under EU AI Act and GDPR Art. 22',
    un_mission_fit:'whether affected individuals can understand how decisions are made',
  },
  harmfulness: {
    security:      'how harmful the output could be if security controls are bypassed',
    governance:    'compliance with prohibited-AI and high-risk-AI harm prevention rules',
    un_mission_fit:'potential for physical, psychological, or societal harm to beneficiaries',
  },
}

export function buildHumanRationale(decision: any, councilNote?: string): string {
  const rec: string = String(decision.final_recommendation ?? 'REVIEW')
  const consensus: string = String(decision.consensus_level ?? 'PARTIAL')
  const humanOversight: boolean = Boolean(decision.human_oversight_required)
  const blocksDeployment: boolean = Boolean(decision.compliance_blocks_deployment)
  const agreements: string[] = Array.isArray(decision.agreements) ? decision.agreements : []
  const disagreements: any[] = Array.isArray(decision.disagreements) ? decision.disagreements : []

  const recSentence: Record<string, string> = {
    APPROVE: 'The Council has reached a positive conclusion: this system is cleared for deployment, subject to the conditions noted below.',
    REVIEW:  'The Council recommends further review before this system proceeds to deployment. This is not a rejection — it signals that specific concerns must be addressed and documented first.',
    REJECT:  'The Council has determined that this system should not proceed to deployment in its current form. The findings below describe what must be resolved before re-submission.',
  }

  const consensusSentence: Record<string, string> = {
    FULL:    `All three experts independently arrived at the same recommendation (${rec}), indicating strong cross-framework alignment on the overall risk level.`,
    PARTIAL: `Two of the three experts agreed on the recommendation (${rec}); one expert's assessment was more conservative, and the most-conservative-wins principle was applied.`,
    SPLIT:   `The three experts reached different conclusions. The final recommendation (${rec}) reflects the most cautious assessment — a deliberate design choice to avoid under-reporting risk in safety-critical contexts.`,
    NONE:    `The three experts reached different conclusions. The final recommendation (${rec}) reflects the most cautious assessment.`,
  }

  const parts: string[] = []

  parts.push(recSentence[rec] ?? recSentence['REVIEW'])
  parts.push(consensusSentence[consensus] ?? consensusSentence['NONE'])

  if (agreements.length > 0) {
    const aLabels = agreements.map(a => dimensionLabel[a] ?? titleCase(a)).join(', ')
    parts.push(`Area${agreements.length > 1 ? 's' : ''} of full cross-expert agreement: ${aLabels}. All three evaluation frameworks independently identified the same risk level here.`)
  }

  if (disagreements.length > 0) {
    const dims = disagreements.map(d => dimensionLabel[d.dimension] ?? titleCase(d.dimension ?? '')).join(' and ')
    parts.push(`Cross-framework differences were detected in ${dims}. These are not contradictions — they reflect that each expert applies a different lens (adversarial testing, regulatory compliance, humanitarian principles). The disagreements are recorded for human review rather than resolved automatically.`)
  }

  if (humanOversight) {
    parts.push('At least one expert has flagged that human oversight is required before any deployment decision. This means a qualified human reviewer must sign off on this report.')
  }

  if (blocksDeployment) {
    parts.push('At least one compliance-blocking issue has been identified. Deployment must not proceed until this is resolved.')
  }

  if (councilNote && councilNote.trim()) {
    parts.push(councilNote.trim())
  }

  return parts.join('\n\n')
}

export function buildHumanConditions(disagreements: any[]): string[] {
  return disagreements.map((d: any) => {
    const dim: string = d.dimension ?? 'unknown'
    const label = dimensionLabel[dim] ?? titleCase(dim)
    const type: string = d.type ?? 'framework_difference'
    const values: Record<string, number> = d.values ?? {}
    const escalate: boolean = Boolean(d.escalate_to_human)

    const scoreParts = Object.entries(values)
      .map(([expert, score]) => `${expertFullName[expert] ?? expert}: ${score}/5`)
      .join(', ')

    const explainer = dimensionExplainer[dim]
    let methodNote = ''
    if (explainer) {
      const expertNotes = Object.entries(values)
        .map(([expert, score]) => {
          const note = explainer[expert as keyof typeof explainer]
          return note ? `The ${expertFullName[expert] ?? expert} (${note}) rated it ${score}/5` : null
        })
        .filter(Boolean)
        .join('; ')
      if (expertNotes) methodNote = ` ${expertNotes}.`
    }

    const typeNote: Record<string, string> = {
      framework_difference:
        'This is a framework difference — each expert evaluates this dimension through a different lens, so variation is expected and meaningful.',
      test_pass_doc_fail:
        'The system passed live adversarial testing, but documentation-based review found this dimension under-addressed — the implementation may be sound while the governance record is incomplete.',
      test_fail_doc_pass:
        'Live testing found a vulnerability that documentation-based review did not flag — the written policies appear adequate, but the actual implementation does not match them.',
    }

    const escalateNote = escalate
      ? ' ⚠ This disagreement has been flagged for mandatory escalation to a human reviewer.'
      : ''

    return (
      `${label} — ${titleCase(type.replace(/_/g, ' '))}: Scores were [${scoreParts}].` +
      methodNote +
      ` ${typeNote[type] ?? ''}` +
      escalateNote
    )
  })
}

export function councilReportToDetailedEvaluation(report: CouncilReportResponse): DetailedEvaluation {
  const raw = report.expert_reports ?? {}
  const security = raw.security ?? {}
  const governance = raw.governance ?? {}
  const mission = raw.un_mission_fit ?? {}

  const expertReports: ExpertReport[] = [
    {
      id: 'security',
      title: 'Security & Adversarial Robustness',
      shortTitle: 'Security',
      icon: '🛡',
      recommendation: toRecommendation(security.recommendation),
      scores: scoreEntries(security),
      findings: extractFindings(security),
      framework_refs: extractRefs(security),
      elapsed: Number(security.elapsed_seconds ?? 0),
      // Live attack audit trail — only present when Expert 1 ran in live mode
      attack_trace:    Array.isArray(security.attack_trace)    ? security.attack_trace    : undefined,
      probe_trace:     Array.isArray(security.probe_trace)     ? security.probe_trace     : undefined,
      boundary_trace:  Array.isArray(security.boundary_trace)  ? security.boundary_trace  : undefined,
      breach_details:  Array.isArray(security.breach_details)  ? security.breach_details  : undefined,
      phase_highlights: security.phase_highlights ?? undefined,
      standard_suite:  Array.isArray(security.standard_suite_results?.all_results)
                         ? security.standard_suite_results.all_results
                         : undefined,
      fingerprint: security.fingerprint ?? undefined,
    },
    {
      id: 'governance',
      title: 'Governance & Regulatory Compliance',
      shortTitle: 'Governance',
      icon: '⚖️',
      recommendation: toRecommendation(governance.recommendation ?? governance.overall_compliance),
      scores: scoreEntries(governance),
      findings: extractFindings(governance),
      framework_refs: extractRefs(governance),
      elapsed: Number(governance.elapsed_seconds ?? 0),
    },
    {
      id: 'un_mission',
      title: 'UN Mission Fit & Human Rights',
      shortTitle: 'UN Mission',
      icon: '🌐',
      recommendation: toRecommendation(mission.recommendation),
      scores: scoreEntries(mission),
      findings: extractFindings(mission),
      framework_refs: extractRefs(mission),
      elapsed: Number(mission.elapsed_seconds ?? 0),
    },
  ]

  const critiques = Object.values(report.critiques ?? {}).map((c: any) => ({
    from: String(c?.from_expert ?? 'Unknown Expert'),
    on: String(c?.on_expert ?? 'Unknown Expert'),
    agrees: Boolean(c?.agrees),
    divergence_type: String(c?.divergence_type ?? 'framework_difference'),
    key_point: String(c?.key_point ?? ''),
    stance: String(c?.stance ?? c?.new_information ?? ''),
    evidence: (Array.isArray(c?.evidence_references) ? c.evidence_references : []).map((x: unknown) => String(x)),
  }))

  const decision = report.council_decision ?? {}
  const disagreements = Array.isArray(decision.disagreements) ? decision.disagreements : []

  return {
    incident_id: report.incident_id,
    agent_id: report.agent_id,
    system_name: report.system_name || report.agent_id,
    category: 'Submitted System',
    submitted_at: report.timestamp,
    description: report.system_description || 'No system description returned by backend.',
    decision: toRecommendation(decision.final_recommendation),
    consensus: toConsensus(decision.consensus_level),
    expert_reports: expertReports,
    council_critiques: critiques,
    final_rationale: buildHumanRationale(decision, report.council_note),
    key_conditions: buildHumanConditions(disagreements),
  }
}

