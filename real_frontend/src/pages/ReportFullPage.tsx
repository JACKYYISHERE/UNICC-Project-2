import { useEffect, useState, type FC } from 'react'
import { getEvaluationByIncident, type CouncilReportResponse } from '../api/client'

// ── Helpers ───────────────────────────────────────────────────────────────────

const titleCase = (k: string) =>
  k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

const fmtDate = (iso: string) =>
  new Date(iso).toLocaleString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })

const complianceToScore: Record<string, number> = { PASS: 1, UNCLEAR: 3, FAIL: 5 }

function scoreEntries(r: any): { label: string; value: number; max: number }[] {
  const ds = r?.dimension_scores
  if (ds && typeof ds === 'object' && Object.values(ds).some(v => typeof v === 'number')) {
    return Object.entries(ds).slice(0, 8).map(([k, v]) => ({
      label: titleCase(k), value: Number(v) || 0, max: 5,
    }))
  }
  const cf = r?.compliance_findings
  if (cf && typeof cf === 'object' && Object.keys(cf).length > 0) {
    return Object.entries(cf).map(([k, v]) => ({
      label: titleCase(k),
      value: complianceToScore[String(v).toUpperCase()] ?? 3,
      max: 5,
    }))
  }
  const h = r?.council_handoff
  if (h && typeof h === 'object') {
    const keys = ['privacy_score', 'transparency_score', 'bias_score'].filter(k => h[k] != null)
    if (keys.length) return keys.map(k => ({
      label: titleCase(k.replace('_score', '')),
      value: Number(h[k]) || 0, max: 5,
    }))
  }
  return [{ label: 'Overall', value: 3, max: 5 }]
}

function extractFindings(r: any): string[] {
  if (Array.isArray(r?.key_findings) && r.key_findings.length)
    return r.key_findings.map((x: unknown) => String(x))
  if (Array.isArray(r?.key_gaps) && r.key_gaps.length)
    return r.key_gaps.slice(0, 8).map((g: any) => String(g?.gap ?? g?.description ?? g))
  if (typeof r?.recommendation_rationale === 'string' && r.recommendation_rationale.trim())
    return [r.recommendation_rationale]
  return ['No detailed findings returned.']
}

function extractRefs(r: any): string[] {
  if (Array.isArray(r?.framework_refs) && r.framework_refs.length) return r.framework_refs
  if (Array.isArray(r?.regulatory_citations) && r.regulatory_citations.length) return r.regulatory_citations
  if (Array.isArray(r?.evidence_references) && r.evidence_references.length) return r.evidence_references
  return []
}

// ── Recommendation pill ───────────────────────────────────────────────────────

const REC_CONFIG = {
  APPROVE: { label: 'Approve', bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200', dot: 'bg-emerald-500' },
  REVIEW:  { label: 'Review',  bg: 'bg-amber-50',   text: 'text-amber-700',   border: 'border-amber-200',  dot: 'bg-amber-500' },
  REJECT:  { label: 'Reject',  bg: 'bg-red-50',     text: 'text-red-700',     border: 'border-red-200',    dot: 'bg-red-500' },
} as const

const RecPill: FC<{ rec: string; large?: boolean }> = ({ rec, large }) => {
  const k = (rec?.toUpperCase() in REC_CONFIG ? rec.toUpperCase() : 'REVIEW') as keyof typeof REC_CONFIG
  const c = REC_CONFIG[k]
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border font-semibold
      ${c.bg} ${c.text} ${c.border}
      ${large ? 'px-4 py-1.5 text-sm' : 'px-2.5 py-0.5 text-xs'}`}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${c.dot}`} />
      {c.label}
    </span>
  )
}

// ── Score bar ─────────────────────────────────────────────────────────────────

const ScoreBar: FC<{ label: string; value: number; max: number }> = ({ label, value, max }) => {
  const pct = (value / max) * 100
  const color = pct <= 20 ? 'bg-emerald-500' : pct <= 60 ? 'bg-amber-500' : 'bg-red-500'
  const textColor = pct <= 20 ? 'text-emerald-700' : pct <= 60 ? 'text-amber-700' : 'text-red-700'
  return (
    <div className="space-y-1">
      <div className="flex justify-between items-center">
        <span className="text-xs text-gray-500">{label}</span>
        <span className={`text-xs font-bold ${textColor}`}>{value}/{max}</span>
      </div>
      <div className="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

// ── Structured finding card ───────────────────────────────────────────────────

const FindingCard: FC<{ text: string; index: number }> = ({ text, index }) => {
  const isAudit = text.includes('[RISK]') && text.includes('[EVIDENCE]')
  if (isAudit) {
    const extract = (tag: string, next: string) => {
      const re = new RegExp(`\\[${tag}\\]\\s*(.*?)(?=\\[${next}\\]|$)`, 's')
      return text.match(re)?.[1]?.trim() ?? ''
    }
    const risk  = extract('RISK', 'EVIDENCE')
    const evid  = extract('EVIDENCE', 'IMPACT')
    const imp   = extract('IMPACT', 'SCORE')
    const score = extract('SCORE', '$')

    return (
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <div className="px-4 py-2 bg-gray-50 border-b border-gray-100 flex items-center gap-2">
          <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Finding {index + 1}</span>
        </div>
        <div className="p-4 space-y-3">
          <div className="flex gap-2.5 items-start">
            <span className="shrink-0 px-1.5 py-0.5 rounded text-[9px] font-bold bg-red-50 text-red-600 uppercase tracking-wide mt-0.5 border border-red-100">Risk</span>
            <p className="text-xs font-medium text-gray-800 leading-relaxed">{risk}</p>
          </div>
          <div className="flex gap-2.5 items-start">
            <span className="shrink-0 px-1.5 py-0.5 rounded text-[9px] font-bold bg-blue-50 text-blue-600 uppercase tracking-wide mt-0.5 border border-blue-100">Evidence</span>
            <p className="text-xs text-gray-600 leading-relaxed">{evid}</p>
          </div>
          {imp && (
            <div className="flex gap-2.5 items-start">
              <span className="shrink-0 px-1.5 py-0.5 rounded text-[9px] font-bold bg-orange-50 text-orange-600 uppercase tracking-wide mt-0.5 border border-orange-100">Impact</span>
              <p className="text-xs text-gray-600 leading-relaxed">{imp}</p>
            </div>
          )}
          {score && (
            <div className="flex gap-2.5 items-start">
              <span className="shrink-0 px-1.5 py-0.5 rounded text-[9px] font-bold bg-purple-50 text-purple-600 uppercase tracking-wide mt-0.5 border border-purple-100">Score</span>
              <p className="text-xs text-gray-500 leading-relaxed italic">{score}</p>
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="flex gap-2.5 rounded-xl border border-gray-100 bg-white p-4">
      <span className="shrink-0 w-5 h-5 rounded-full bg-red-50 text-red-500 text-[10px] font-bold flex items-center justify-center mt-0.5">
        {index + 1}
      </span>
      <p className="text-xs text-gray-700 leading-relaxed">{text}</p>
    </div>
  )
}

// ── Expert section ────────────────────────────────────────────────────────────

const EXPERT_META = [
  { key: 'security',       icon: '🛡',  label: 'Security & Adversarial Robustness',  accent: 'border-red-200 bg-red-50/40' },
  { key: 'governance',     icon: '⚖️', label: 'Governance & Regulatory Compliance', accent: 'border-violet-200 bg-violet-50/40' },
  { key: 'un_mission_fit', icon: '🌐', label: 'UN Mission Fit & Human Rights',       accent: 'border-sky-200 bg-sky-50/40' },
]

const ExpertSection: FC<{ expertKey: string; report: any }> = ({ expertKey, report }) => {
  const meta     = EXPERT_META.find(m => m.key === expertKey) ?? EXPERT_META[0]
  const scores   = scoreEntries(report)
  const findings = extractFindings(report)
  const refs     = extractRefs(report)
  const rec      = String(report?.recommendation ?? report?.overall_compliance ?? 'REVIEW')

  return (
    <section className={`rounded-2xl border-2 ${meta.accent} overflow-hidden`}>
      <div className="px-6 py-4 flex items-center justify-between border-b border-black/5">
        <div className="flex items-center gap-3">
          <span className="text-2xl">{meta.icon}</span>
          <div>
            <h3 className="font-bold text-gray-900 text-sm">{meta.label}</h3>
            {report?.risk_tier && (
              <span className="text-xs text-gray-400">Risk tier: {report.risk_tier}</span>
            )}
          </div>
        </div>
        <RecPill rec={rec} />
      </div>

      <div className="p-6 grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Left: Scores + rationale + refs */}
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-4">Dimension Scores</p>
          <div className="space-y-3">
            {scores.map(s => <ScoreBar key={s.label} {...s} />)}
          </div>

          {report?.recommendation_rationale && (
            <div className="mt-5 p-3 rounded-xl bg-white/70 border border-black/5">
              <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-2">Rationale Summary</p>
              <p className="text-xs text-gray-600 leading-relaxed line-clamp-6">{report.recommendation_rationale}</p>
            </div>
          )}

          {report?.narrative && !report?.recommendation_rationale && (
            <div className="mt-5 p-3 rounded-xl bg-white/70 border border-black/5">
              <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-2">Narrative</p>
              <p className="text-xs text-gray-600 leading-relaxed line-clamp-6">{report.narrative}</p>
            </div>
          )}

          {refs.length > 0 && (
            <div className="mt-5">
              <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-2">Regulatory References</p>
              <div className="space-y-1.5">
                {refs.slice(0, 6).map((ref, i) => (
                  <div key={i} className="flex items-start gap-1.5 text-xs text-gray-500 leading-snug">
                    <span className="text-blue-400 shrink-0">§</span>
                    <span>{ref}</span>
                  </div>
                ))}
                {refs.length > 6 && <p className="text-xs text-gray-400 italic">+ {refs.length - 6} more</p>}
              </div>
            </div>
          )}
        </div>

        {/* Right: Findings */}
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-4">
            Key Findings · {findings.length}
          </p>
          <div className="space-y-3 max-h-[620px] overflow-y-auto pr-1">
            {findings.map((f, i) => <FindingCard key={i} text={f} index={i} />)}
          </div>
        </div>
      </div>
    </section>
  )
}

// ── Critique card ─────────────────────────────────────────────────────────────

const EXPERT_LABEL: Record<string, { short: string; color: string }> = {
  security_adversarial:  { short: 'Security',  color: 'bg-red-50 text-red-700 border-red-200' },
  governance_compliance: { short: 'Governance', color: 'bg-violet-50 text-violet-700 border-violet-200' },
  un_mission_fit:        { short: 'UN Mission', color: 'bg-sky-50 text-sky-700 border-sky-200' },
}
const expertLabel = (k: string) =>
  EXPERT_LABEL[k] ?? { short: k.replace(/_/g, ' '), color: 'bg-gray-100 text-gray-600 border-gray-200' }

const CritiqueCard: FC<{ critique: any }> = ({ critique }) => {
  const from = expertLabel(critique.from_expert ?? '')
  const on   = expertLabel(critique.on_expert   ?? '')
  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm p-5 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${from.color}`}>{from.short}</span>
        <span className="text-gray-400 text-xs">reviewed</span>
        <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${on.color}`}>{on.short}</span>
        <span className="ml-auto">
          {critique.agrees
            ? <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">Agrees</span>
            : <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-red-50 text-red-700 border border-red-200">Disagrees</span>}
        </span>
      </div>
      <p className="text-xs text-gray-700 leading-relaxed italic">"{critique.key_point}"</p>
      {critique.stance && (
        <p className="text-xs text-gray-500 leading-relaxed">{critique.stance}</p>
      )}
      {Array.isArray(critique.evidence_references) && critique.evidence_references.length > 0 && (
        <div className="space-y-1 pt-1 border-t border-gray-50">
          {critique.evidence_references.slice(0, 3).map((ev: string, i: number) => (
            <div key={i} className="flex items-start gap-1.5 text-xs text-gray-400">
              <span className="text-blue-400 shrink-0">§</span>
              <span>{ev}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Section title ─────────────────────────────────────────────────────────────

const SectionTitle: FC<{ children: React.ReactNode }> = ({ children }) => (
  <h2 className="text-lg font-bold text-gray-900 mb-4">{children}</h2>
)

// ── Main page ─────────────────────────────────────────────────────────────────

interface Props {
  incidentId: string
  onBack?: () => void
}

const ReportFullPage: FC<Props> = ({ incidentId, onBack }) => {
  const [report, setReport]   = useState<CouncilReportResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    getEvaluationByIncident(incidentId)
      .then(setReport)
      .catch(e => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [incidentId])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center space-y-3">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-sm text-gray-400">Loading report…</p>
        </div>
      </div>
    )
  }

  if (error || !report) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center space-y-2">
          <p className="text-sm text-red-500">{error ?? 'Report not found.'}</p>
          {onBack && <button className="text-xs text-blue-500 hover:underline" onClick={onBack}>← Back</button>}
        </div>
      </div>
    )
  }

  const decision      = report.council_decision ?? {}
  const finalRec      = String(decision.final_recommendation ?? 'REVIEW')
  const consensus     = String(decision.consensus_level ?? '')
  const rationale     = String(decision.rationale ?? report.council_note ?? '')
  const disagreements: any[] = Array.isArray(decision.disagreements) ? decision.disagreements : []
  const critiques     = Object.values(report.critiques ?? {})
  const expertKeys    = ['security', 'governance', 'un_mission_fit']

  const recGradient = finalRec === 'APPROVE' ? 'from-emerald-500 to-teal-500'
                    : finalRec === 'REJECT'  ? 'from-red-500 to-rose-500'
                    : 'from-amber-400 to-orange-400'

  const expertRecs = expertKeys.map(k => ({
    key: k,
    meta: EXPERT_META.find(m => m.key === k)!,
    rec: String((report.expert_reports?.[k] as any)?.recommendation ?? 'REVIEW'),
  }))

  return (
    <div className="min-h-screen bg-gray-50 font-sans">

      {/* ── Sticky top bar ── */}
      <div className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {onBack && (
              <>
                <button onClick={onBack} className="text-xs text-gray-400 hover:text-gray-700 transition-colors">
                  ← Back
                </button>
                <span className="text-gray-200">|</span>
              </>
            )}
            <span className="text-sm font-semibold text-gray-700 truncate max-w-xs">
              {report.system_name ?? report.agent_id}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <RecPill rec={finalRec} />
            <span className="text-xs text-gray-400 hidden sm:block">{fmtDate(report.timestamp)}</span>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-10 space-y-14">

        {/* ── Hero ── */}
        <section className="space-y-5">
          <div className={`h-1 w-16 rounded-full bg-gradient-to-r ${recGradient}`} />
          <div>
            <h1 className="text-3xl font-bold text-gray-900 leading-tight">
              {report.system_name ?? report.agent_id}
            </h1>
            <p className="text-sm text-gray-400 mt-1">{incidentId} · {fmtDate(report.timestamp)}</p>
          </div>

          {/* Verdict + badges */}
          <div className="flex flex-wrap items-center gap-3">
            <RecPill rec={finalRec} large />
            {consensus && (
              <span className="px-3 py-1 rounded-full bg-gray-100 text-xs font-semibold text-gray-600">
                {consensus} consensus
              </span>
            )}
            {decision.human_oversight_required && (
              <span className="px-3 py-1 rounded-full bg-amber-50 text-amber-700 text-xs font-semibold border border-amber-200">
                Human oversight required
              </span>
            )}
            {decision.compliance_blocks_deployment && (
              <span className="px-3 py-1 rounded-full bg-red-50 text-red-700 text-xs font-semibold border border-red-200">
                Blocks deployment
              </span>
            )}
          </div>

          {/* 3-expert matrix */}
          <div className="grid grid-cols-3 gap-3">
            {expertRecs.map(({ key, meta, rec }) => (
              <div key={key} className="flex items-center justify-between p-3 rounded-xl bg-white border border-gray-200 shadow-sm">
                <div className="flex items-center gap-2">
                  <span className="text-xl">{meta?.icon}</span>
                  <span className="text-xs font-medium text-gray-600 hidden sm:block">
                    {meta?.label.split('&')[0].trim()}
                  </span>
                </div>
                <RecPill rec={rec} />
              </div>
            ))}
          </div>
        </section>

        {/* ── System description ── */}
        {report.system_description && (
          <section>
            <SectionTitle>System Under Evaluation</SectionTitle>
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
              <p className="text-sm text-gray-700 leading-relaxed">{report.system_description}</p>
            </div>
          </section>
        )}

        {/* ── Three expert analyses ── */}
        <section className="space-y-6">
          <SectionTitle>Expert Analyses</SectionTitle>
          {expertKeys.map(k =>
            report.expert_reports?.[k]
              ? <ExpertSection key={k} expertKey={k} report={report.expert_reports[k]} />
              : null
          )}
        </section>

        {/* ── Cross-expert critiques ── */}
        {critiques.length > 0 && (
          <section>
            <SectionTitle>
              Cross-Expert Critiques{' '}
              <span className="text-base font-normal text-gray-400">· {critiques.length} filed</span>
            </SectionTitle>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {critiques.map((c: any, i) => <CritiqueCard key={i} critique={c} />)}
            </div>
          </section>
        )}

        {/* ── Score disagreements ── */}
        {disagreements.length > 0 && (
          <section>
            <SectionTitle>Score Disagreements</SectionTitle>
            <div className="space-y-2">
              {disagreements.map((d: any, i) => (
                <div key={i} className="flex items-start gap-3 p-3 rounded-xl bg-amber-50 border border-amber-200">
                  <span className="shrink-0 w-5 h-5 rounded-full bg-amber-500 text-white text-[10px] font-bold flex items-center justify-center mt-0.5">!</span>
                  <div>
                    <p className="text-xs font-semibold text-amber-800 capitalize">
                      {d.dimension} — {String(d.type ?? '').replace(/_/g, ' ')}
                    </p>
                    <p className="text-xs text-amber-700 leading-relaxed mt-0.5">{d.description}</p>
                    {d.values && (
                      <div className="flex gap-2 mt-1.5 flex-wrap">
                        {Object.entries(d.values).map(([k, v]) => (
                          <span key={k} className="text-[10px] text-amber-600 bg-amber-100 px-1.5 py-0.5 rounded">
                            {k.replace(/_/g, ' ')}: {String(v)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* ── Final decision ── */}
        <section>
          <SectionTitle>Final Decision & Rationale</SectionTitle>
          <div className={`rounded-2xl border-2 p-6 space-y-4
            ${finalRec === 'APPROVE' ? 'border-emerald-200 bg-emerald-50/50'
            : finalRec === 'REJECT'  ? 'border-red-200 bg-red-50/50'
            : 'border-amber-200 bg-amber-50/50'}`}>
            <div className="flex items-center gap-3 flex-wrap">
              <RecPill rec={finalRec} large />
              {consensus && (
                <span className="text-sm text-gray-500">{consensus} consensus among three experts</span>
              )}
            </div>
            <pre className="text-xs text-gray-600 leading-relaxed whitespace-pre-wrap font-sans">{rationale}</pre>
          </div>
        </section>

        {/* ── Footer ── */}
        <footer className="pt-6 border-t border-gray-100 flex items-center justify-between text-xs text-gray-400">
          <span>UNICC AI Safety Council</span>
          <span>{incidentId}</span>
        </footer>

      </div>
    </div>
  )
}

export default ReportFullPage
