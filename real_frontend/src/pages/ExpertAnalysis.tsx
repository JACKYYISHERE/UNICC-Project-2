import { type FC, useState, useCallback } from 'react'
import { detailedEval, type DetailedEvaluation, type ExpertReport } from '../data/mockData'
import { RecBadge } from '../components/Badge'
import { hapticSelect } from '../utils/haptic'
import { getEvaluationAudit, type AuditEvent, type AuditSpan } from '../api/client'

// ── Score bar row ─────────────────────────────────────────────────────────────
const ScoreRow: FC<{ label: string; value: number; max: number }> = ({ label, value, max }) => {
  const pct = (value / max) * 100
  // 1=low risk (green/short) → 5=critical risk (red/full) — inverted from typical progress bars
  const color = pct <= 20 ? 'bg-apple-green' : pct <= 40 ? 'bg-apple-orange' : pct <= 60 ? 'bg-apple-orange' : 'bg-apple-red'
  return (
    <div>
      <div className="flex justify-between mb-1.5">
        <span className="text-xs text-apple-gray-600">{label}</span>
        <span className="text-xs font-bold text-apple-gray-900">{value}/{max}</span>
      </div>
      <div className="score-bar">
        <div className={`score-fill ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

// ── Expert card ───────────────────────────────────────────────────────────────
const ExpertCard: FC<{ report: ExpertReport; active: boolean; onClick: () => void }> = ({ report, active, onClick }) => (
  <button
    onClick={() => { hapticSelect(); onClick() }}
    className={`w-full text-left p-4 rounded-apple-lg border-2 transition-all duration-200
      ${active ? 'border-apple-blue bg-apple-blue-light' : 'border-apple-gray-100 bg-white hover:border-apple-gray-200'}`}
  >
    <div className="flex items-center justify-between mb-2">
      <span className="text-xl">{report.icon}</span>
      <RecBadge rec={report.recommendation} size="sm" />
    </div>
    <p className="text-sm font-semibold text-apple-gray-900 leading-snug mb-0.5">{report.title}</p>
    <p className="text-[11px] text-apple-gray-400">{report.elapsed}s elapsed</p>
  </button>
)

// ── Severity color chip ───────────────────────────────────────────────────────
const sevColor = (sev: string) => {
  if (sev === 'ERROR' || sev === 'CRITICAL') return 'text-apple-red'
  if (sev === 'WARN')  return 'text-apple-orange'
  if (sev === 'DEBUG') return 'text-apple-gray-400'
  return 'text-apple-green'
}

const actorLabel = (actor: string) =>
  actor.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

// ── Audit Log panel ───────────────────────────────────────────────────────────
const AuditPanel: FC<{ incidentId: string | undefined }> = ({ incidentId }) => {
  const [open, setOpen]         = useState(false)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState<string | null>(null)
  const [events, setEvents]     = useState<AuditEvent[]>([])
  const [spans, setSpans]       = useState<AuditSpan[]>([])

  const load = useCallback(async () => {
    if (!incidentId) return
    setLoading(true)
    setError(null)
    try {
      const data = await getEvaluationAudit(incidentId)
      setEvents(data.events)
      setSpans(data.spans)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [incidentId])

  const toggle = () => {
    hapticSelect()
    if (!open && events.length === 0) void load()
    setOpen(o => !o)
  }

  const totalMs = spans.reduce((acc, s) => acc + (s.duration_ms ?? 0), 0)

  return (
    <div className="card overflow-hidden">
      {/* Header — always visible */}
      <button
        className="w-full flex items-center justify-between px-5 py-3.5 hover:bg-apple-gray-50 transition-colors"
        onClick={toggle}
      >
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-bold uppercase tracking-wider text-apple-gray-400">Audit / Pipeline Log</span>
          {events.length > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-apple-gray-100 text-apple-gray-500 font-semibold">
              {events.length} events
            </span>
          )}
          {totalMs > 0 && (
            <span className="text-[10px] text-apple-gray-400">· {(totalMs / 1000).toFixed(1)}s total</span>
          )}
          {!incidentId && (
            <span className="text-[10px] text-apple-gray-400 italic">mock data — not available</span>
          )}
        </div>
        <span className="text-apple-gray-400 text-xs">{open ? '▲' : '▼'}</span>
      </button>

      {/* Expandable body */}
      {open && (
        <div className="border-t border-apple-gray-100">
          {loading && (
            <div className="flex items-center gap-2 px-5 py-4 text-xs text-apple-gray-400">
              <div className="w-3 h-3 border border-apple-blue border-t-transparent rounded-full animate-spin" />
              Loading audit log…
            </div>
          )}
          {error && (
            <p className="px-5 py-3 text-xs text-apple-red">{error}</p>
          )}
          {!loading && !error && events.length === 0 && (
            <p className="px-5 py-3 text-xs text-apple-gray-400">No audit events found for this evaluation.</p>
          )}

          {/* Timing spans summary */}
          {spans.length > 0 && (
            <div className="px-5 py-3 border-b border-apple-gray-50 flex flex-wrap gap-3">
              {spans.map(s => (
                <div key={s.span_id} className="flex items-center gap-1.5 text-[11px]">
                  <span className={`w-1.5 h-1.5 rounded-full ${s.status === 'success' ? 'bg-apple-green' : 'bg-apple-red'}`} />
                  <span className="text-apple-gray-600 font-medium">{s.span_name.replace(/_/g, ' ')}</span>
                  <span className="text-apple-gray-400">{s.duration_ms != null ? `${(s.duration_ms / 1000).toFixed(1)}s` : '—'}</span>
                </div>
              ))}
            </div>
          )}

          {/* Event list — terminal style */}
          {events.length > 0 && (
            <div className="bg-[#1c1c1e] rounded-b-apple mx-0 max-h-64 overflow-y-auto font-mono">
              {events.map((ev, i) => (
                <div
                  key={ev.event_id}
                  className={`flex gap-3 px-4 py-1.5 text-[11px] leading-relaxed
                    ${i % 2 === 0 ? 'bg-transparent' : 'bg-white/[0.02]'}
                    hover:bg-white/[0.05] transition-colors`}
                >
                  <span className="text-[#636366] shrink-0 select-none">
                    {ev.created_at.slice(11, 19)}
                  </span>
                  <span className={`shrink-0 w-10 font-bold ${sevColor(ev.severity)}`}>
                    {ev.severity.slice(0, 4)}
                  </span>
                  <span className="text-[#98989d] shrink-0 w-28 truncate">
                    {actorLabel(ev.actor)}
                  </span>
                  <span className="text-[#e5e5ea] flex-1 min-w-0">
                    {ev.message}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Collapsible description card ──────────────────────────────────────────────
const DescriptionCard: FC<{ description: string }> = ({ description }) => {
  const [expanded, setExpanded] = useState(false)
  const PREVIEW_CHARS = 280
  const isLong = description.length > PREVIEW_CHARS

  return (
    <div className="card overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-5 py-3.5 hover:bg-apple-gray-50 transition-colors"
        onClick={() => { hapticSelect(); setExpanded(e => !e) }}
      >
        <span className="text-[11px] font-bold uppercase tracking-wider text-apple-gray-400">
          System Under Evaluation
        </span>
        {isLong && (
          <span className="text-[11px] text-apple-blue">{expanded ? '▲ Collapse' : '▼ Expand'}</span>
        )}
      </button>
      <div className="px-5 pb-4 border-t border-apple-gray-50">
        <p className="text-sm text-apple-gray-700 leading-relaxed mt-3">
          {isLong && !expanded
            ? description.slice(0, PREVIEW_CHARS) + '…'
            : description}
        </p>
        {isLong && (
          <button
            className="mt-2 text-xs text-apple-blue hover:underline"
            onClick={() => { hapticSelect(); setExpanded(e => !e) }}
          >
            {expanded ? 'Show less' : 'Show full description'}
          </button>
        )}
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
interface Props { evaluation?: DetailedEvaluation | null }

const ExpertAnalysis: FC<Props> = ({ evaluation }) => {
  const eval_ = evaluation ?? detailedEval
  const [activeId, setActiveId] = useState<ExpertReport['id']>('security')
  const active = eval_.expert_reports.find(r => r.id === activeId)!

  return (
    <div className="p-8 space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-apple-gray-900 mb-1">Expert Analysis</h1>
          <p className="text-sm text-apple-gray-400">{eval_.system_name} · {eval_.category}</p>
        </div>
        <RecBadge rec={eval_.decision} />
      </div>

      {/* Description + Audit Log — side by side */}
      <div className="grid grid-cols-2 gap-4">
        <DescriptionCard description={eval_.description} />
        <AuditPanel incidentId={eval_.incident_id} />
      </div>

      {/* Expert selector */}
      <div className="grid grid-cols-3 gap-3">
        {eval_.expert_reports.map(r => (
          <ExpertCard key={r.id} report={r} active={activeId === r.id} onClick={() => setActiveId(r.id)} />
        ))}
      </div>

      {/* Active expert detail */}
      <div className="card p-6 animate-slide-up" key={activeId}>
        <div className="flex items-center gap-3 mb-6">
          <span className="text-2xl">{active.icon}</span>
          <div>
            <h2 className="text-base font-bold text-apple-gray-900">{active.title}</h2>
            <div className="flex items-center gap-2 mt-0.5">
              <RecBadge rec={active.recommendation} />
              <span className="text-xs text-apple-gray-400">· {active.elapsed}s</span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-8">
          {/* Scores */}
          <div>
            <p className="section-label">Dimension Scores</p>
            <div className="space-y-3.5">
              {active.scores.map(s => <ScoreRow key={s.label} {...s} />)}
            </div>
          </div>

          {/* Findings + refs */}
          <div className="space-y-6">
            <div>
              <p className="section-label">Key Findings</p>
              <ul className="space-y-3">
                {active.findings.map((f, i) => {
                  const isAudit = f.includes('[RISK]') && f.includes('[EVIDENCE]');
                  if (isAudit) {
                    const extract = (tag: string, next: string) => {
                      const re = new RegExp(`\\[${tag}\\]\\s*(.*?)(?=\\[${next}\\]|$)`, 's');
                      return f.match(re)?.[1]?.trim() ?? '';
                    };
                    const risk  = extract('RISK', 'EVIDENCE');
                    const evid  = extract('EVIDENCE', 'IMPACT');
                    const imp   = extract('IMPACT', 'SCORE');
                    const score = extract('SCORE', '$');
                    return (
                      <li key={i} className="rounded-apple border border-apple-gray-100 bg-apple-gray-50 p-3 space-y-1.5">
                        <div className="flex gap-1.5 items-start">
                          <span className="shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded bg-apple-red-bg text-apple-red uppercase tracking-wide mt-0.5">Risk</span>
                          <p className="text-xs text-apple-gray-800 font-medium leading-snug">{risk}</p>
                        </div>
                        <div className="flex gap-1.5 items-start">
                          <span className="shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded bg-blue-50 text-blue-600 uppercase tracking-wide mt-0.5">Evidence</span>
                          <p className="text-xs text-apple-gray-600 leading-snug">{evid}</p>
                        </div>
                        <div className="flex gap-1.5 items-start">
                          <span className="shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded bg-orange-50 text-orange-600 uppercase tracking-wide mt-0.5">Impact</span>
                          <p className="text-xs text-apple-gray-600 leading-snug">{imp}</p>
                        </div>
                        {score && (
                          <div className="flex gap-1.5 items-start">
                            <span className="shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded bg-purple-50 text-purple-600 uppercase tracking-wide mt-0.5">Score</span>
                            <p className="text-xs text-apple-gray-500 leading-snug italic">{score}</p>
                          </div>
                        )}
                      </li>
                    );
                  }
                  const hasImpact = f.includes('Impact:');
                  if (hasImpact) {
                    const impactIdx = f.indexOf('Impact:');
                    const body = f.slice(0, impactIdx).trim();
                    const impact = f.slice(impactIdx + 7).trim();
                    return (
                      <li key={i} className="rounded-apple border border-apple-gray-100 bg-apple-gray-50 p-3 space-y-1.5">
                        <div className="flex gap-1.5 items-start">
                          <span className="w-4 h-4 rounded-full bg-apple-red-bg text-apple-red text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">!</span>
                          <p className="text-xs text-apple-gray-700 leading-snug">{body}</p>
                        </div>
                        <div className="flex gap-1.5 items-start ml-6">
                          <span className="shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded bg-orange-50 text-orange-600 uppercase tracking-wide mt-0.5">Impact</span>
                          <p className="text-xs text-apple-gray-600 leading-snug italic">{impact}</p>
                        </div>
                      </li>
                    );
                  }
                  return (
                    <li key={i} className="flex gap-2.5">
                      <span className="w-4 h-4 rounded-full bg-apple-red-bg text-apple-red text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">!</span>
                      <p className="text-xs text-apple-gray-700 leading-relaxed">{f}</p>
                    </li>
                  );
                })}
              </ul>
            </div>
            <div>
              <p className="section-label">Regulatory References</p>
              <div className="space-y-1.5">
                {active.framework_refs.map((ref, i) => (
                  <div key={i} className="flex items-center gap-2 px-3 py-2 rounded-apple bg-apple-gray-50 border border-apple-gray-100">
                    <span className="text-apple-blue text-[10px]">§</span>
                    <span className="text-xs text-apple-gray-600">{ref}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ExpertAnalysis
