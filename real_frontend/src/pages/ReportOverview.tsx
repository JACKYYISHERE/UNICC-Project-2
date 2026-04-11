import { type FC } from 'react'
import { type DetailedEvaluation } from '../data/mockData'
import { RecBadge, ConsensusBadge } from '../components/Badge'
import { hapticButton } from '../utils/haptic'

export type ReportStep = 'overview' | 'experts' | 'council' | 'final'

const STEPS: { id: ReportStep; label: string; short: string }[] = [
  { id: 'overview', label: 'Overview', short: 'Summary' },
  { id: 'experts', label: 'Expert Analysis', short: 'Experts' },
  { id: 'council', label: 'Council Review', short: 'Council' },
  { id: 'final', label: 'Final Report', short: 'Final' },
]

interface Props {
  eval: DetailedEvaluation
  currentStep: ReportStep
  onStep: (step: ReportStep) => void
  /** Expert 1 report from the backend (optional, only present after a live submission) */
  expert1Report?: Record<string, any>
  onViewFull?: () => void
}

// Maps live_attack_error_code → banner style + user-visible copy
const LIVE_ATTACK_BANNERS: Record<string, {
  type: 'error' | 'warning'
  title: string
  detail: string
  action: string
}> = {
  unreachable: {
    type: 'error',
    title: 'Project not running',
    detail: 'The target URL was unreachable — connection refused, timed out, or missing API key.',
    action: 'Start the target project server (with required API keys configured) and re-submit to enable live attack testing.',
  },
  server_error: {
    type: 'error',
    title: 'Target server error',
    detail: 'The target is running but returned an HTTP error (5xx). A dependency or internal service may have crashed.',
    action: 'Check the target project\'s logs and restart it.',
  },
  auth_error: {
    type: 'error',
    title: 'Target API key not configured',
    detail: 'The target server started successfully but its backend service (e.g. OpenAI) is not authenticated.',
    action: 'Set the required API key in the target project\'s .env file and restart the server.',
  },
  response_error: {
    type: 'error',
    title: 'Target returned an unrecognised response',
    detail: 'The target responded (HTTP 200) but the content could not be parsed — it may be an error page or a missing dependency.',
    action: 'Ensure all dependencies (API keys, databases, services) are configured and healthy in the target project.',
  },
  unknown: {
    type: 'error',
    title: 'Live attack could not proceed',
    detail: 'An unexpected error occurred before the live attack began.',
    action: 'Check the backend logs for details. The evaluation fell back to document analysis.',
  },
}

const recMap = (r: string) => (r === 'PASS' || r === 'APPROVE' ? 'APPROVE' : r === 'FAIL' || r === 'REJECT' ? 'REJECT' : 'REVIEW')

const ReportOverview: FC<Props> = ({ eval: ev, currentStep, onStep, expert1Report, onViewFull }) => {
  const date = new Date(ev.submitted_at).toLocaleDateString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
  })

  return (
    <div className="p-8 space-y-6 animate-fade-in">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-apple-gray-900 mb-1">Report</h1>
          <p className="text-sm text-apple-gray-400">{ev.system_name} · {ev.category}</p>
        </div>
        {onViewFull && (
          <button
            onClick={() => { hapticButton(); onViewFull() }}
            className="flex items-center gap-2 px-4 py-2 rounded-apple-lg bg-apple-blue text-white text-xs font-semibold hover:opacity-90 transition-opacity shadow-sm"
          >
            <span>🗂</span>
            View Full Report
          </button>
        )}
      </div>

      {/* Expert 1 live attack section
          analysis_mode values:
            "live_attack"                → attack ran fully, show results
            "document_analysis_fallback" → URL given but attack failed, show banner + doc results
            "document_analysis"          → no URL given, silent doc mode, hide this section entirely */}
      {expert1Report && expert1Report.analysis_mode !== 'document_analysis' && (() => {
        const mode      = expert1Report.analysis_mode as string
        const errorCode = (expert1Report.live_attack_error_code || '') as string
        const errorMsg  = (expert1Report.live_attack_error  || '') as string
        const banner    = errorCode ? (LIVE_ATTACK_BANNERS[errorCode] ?? LIVE_ATTACK_BANNERS.unknown) : null
        const isLive    = mode === 'live_attack'

        return (
          <div className="space-y-3">

            {/* ── Error / warning banner ───────────────────────────────── */}
            {banner && (() => {
              const isErr = banner.type === 'error'
              return (
                <div className={`card p-4 border-2 ${isErr
                  ? 'border-red-300 bg-red-50'
                  : 'border-amber-300 bg-amber-50'}`}>
                  <div className="flex items-start gap-3">
                    <span className={`text-lg leading-none mt-0.5 ${isErr ? 'text-red-500' : 'text-amber-500'}`}>
                      {isErr ? '⚠' : 'ℹ'}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className={`text-sm font-semibold ${isErr ? 'text-red-700' : 'text-amber-700'}`}>
                        {banner.title}
                      </p>
                      <p className="text-xs text-apple-gray-600 mt-0.5">{banner.detail}</p>
                      <p className={`text-xs font-medium mt-1 ${isErr ? 'text-red-600' : 'text-amber-600'}`}>
                        → {banner.action}
                      </p>
                      {errorMsg && (
                        <details className="mt-2">
                          <summary className="text-[11px] text-apple-gray-400 cursor-pointer select-none">
                            Technical details
                          </summary>
                          <p className="text-[11px] text-apple-gray-500 mt-1 font-mono break-all whitespace-pre-wrap">
                            {errorMsg.slice(0, 400)}{errorMsg.length > 400 ? '…' : ''}
                          </p>
                        </details>
                      )}
                      <p className="text-[11px] text-apple-gray-400 mt-2 italic">
                        Live attack was skipped — security results below are from document analysis only.
                      </p>
                    </div>
                  </div>
                </div>
              )
            })()}

            {/* ── Results card ─────────────────────────────────────────── */}
            <div className={`card p-6 border-2 ${isLive
              ? 'border-apple-blue/20 bg-apple-blue-light/30'
              : 'border-apple-gray-100'}`}>
              <div className="flex items-center gap-2 mb-2">
                <p className="section-label mb-0">
                  {isLive ? 'Expert 1 — Live Attack Results' : 'Expert 1 — Security Assessment'}
                </p>
                {!isLive && (
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-apple-gray-100 text-apple-gray-500 uppercase tracking-wide">
                    Doc mode
                  </span>
                )}
                {isLive && (
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-apple-blue/10 text-apple-blue uppercase tracking-wide">
                    Live
                  </span>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-3 mt-2">
                {expert1Report.recommendation != null && (
                  <RecBadge rec={recMap(expert1Report.recommendation)} />
                )}
                {expert1Report.risk_tier != null && (
                  <span className="px-3 py-1 rounded-full text-xs font-semibold bg-apple-gray-100 text-apple-gray-700">
                    Risk: {expert1Report.risk_tier}
                  </span>
                )}
                {expert1Report.session_id != null && (
                  <span className="text-[11px] text-apple-gray-400">
                    Session: {String(expert1Report.session_id).slice(0, 20)}…
                  </span>
                )}
              </div>
              {isLive && Array.isArray(expert1Report.test_coverage?.attack_techniques_tested) &&
                expert1Report.test_coverage!.attack_techniques_tested!.length > 0 && (
                <p className="text-xs text-apple-gray-600 mt-3">
                  Attack techniques tested: {expert1Report.test_coverage!.attack_techniques_tested!.length}
                </p>
              )}
              {Array.isArray(expert1Report.key_findings) && expert1Report.key_findings!.length > 0 && (
                <ul className="mt-3 space-y-1.5">
                  {expert1Report.key_findings!.slice(0, 5).map((f: unknown, i: number) => (
                    <li key={i} className="text-xs text-apple-gray-700 flex gap-2">
                      <span className="text-apple-red shrink-0">•</span>
                      <span>{String(f)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )
      })()}

      {/* Summary card */}
      <div className="card p-6">
        <p className="section-label">Assessment Summary</p>
        <div className="flex flex-wrap items-center gap-4 mt-3">
          <RecBadge rec={ev.decision} />
          <ConsensusBadge consensus={ev.consensus} />
          <span className="text-xs text-apple-gray-400">{date}</span>
        </div>
        <div className="mt-4 flex flex-wrap gap-3">
          {ev.expert_reports.map(r => (
            <div key={r.id} className="flex items-center gap-2 px-3 py-2 rounded-apple bg-apple-gray-50 border border-apple-gray-100">
              <span>{r.icon}</span>
              <span className="text-xs font-medium text-apple-gray-700">{r.shortTitle}</span>
              <RecBadge rec={r.recommendation} size="sm" />
            </div>
          ))}
        </div>
        <p className="text-sm text-apple-gray-600 mt-4 leading-relaxed line-clamp-3">{ev.final_rationale}</p>
      </div>

      {/* Step navigation — clear order */}
      <div className="card p-6">
        <p className="section-label">View full report</p>
        <p className="text-sm text-apple-gray-500 mb-4">Follow the evaluation flow in order.</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {STEPS.map((s, i) => {
            const active = currentStep === s.id
            const isOverview = s.id === 'overview'
            return (
              <button
                key={s.id}
                onClick={() => {
                  hapticButton()
                  onStep(s.id)
                }}
                className={`text-left p-4 rounded-apple-lg border-2 transition-all duration-200
                  ${active ? 'border-apple-blue bg-apple-blue-light' : 'border-apple-gray-100 bg-white hover:border-apple-gray-200 hover:bg-apple-gray-50'}`}
              >
                <span className="text-xs font-semibold text-apple-gray-400">Step {i + 1}</span>
                <p className="text-sm font-semibold text-apple-gray-900 mt-1">{s.label}</p>
                {!isOverview && (
                  <span className="text-[11px] text-apple-gray-400 mt-0.5 inline-block">View details →</span>
                )}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

export default ReportOverview
export { STEPS as REPORT_STEPS }
