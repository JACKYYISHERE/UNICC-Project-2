import { type FC, useState } from 'react'
import { detailedEval, type DetailedEvaluation } from '../data/mockData'
import { RecBadge, ConsensusBadge } from '../components/Badge'
import { hapticButton } from '../utils/haptic'
import { evaluationToMarkdown } from '../utils/reportToMarkdown'
import { downloadEvaluationPdf } from '../api/client'

interface Props { evaluation?: DetailedEvaluation | null }

const FinalReport: FC<Props> = ({ evaluation }) => {
  const eval_ = evaluation ?? detailedEval
  const [copied, setCopied] = useState(false)
  const [pdfLoading, setPdfLoading] = useState(false)
  const [pdfError, setPdfError] = useState<string | null>(null)
  const { system_name, agent_id, category, decision, consensus, expert_reports,
          final_rationale, key_conditions, submitted_at, description, council_critiques } = eval_

  const date = new Date(submitted_at).toLocaleDateString('en-US', {
    year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit'
  })

  const handleCopy = () => {
    hapticButton()
    navigator.clipboard.writeText(final_rationale)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleDownloadMarkdown = () => {
    hapticButton()
    const md = evaluationToMarkdown(eval_)
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `UNICC-Report-${agent_id}-${new Date().toISOString().slice(0, 10)}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleDownloadPdf = async () => {
    if (!eval_.incident_id) {
      setPdfError('No incident ID — PDF only available for real evaluations (not mock data).')
      return
    }
    hapticButton()
    setPdfError(null)
    setPdfLoading(true)
    try {
      await downloadEvaluationPdf(eval_.incident_id)
    } catch (e) {
      setPdfError(e instanceof Error ? e.message : String(e))
    } finally {
      setPdfLoading(false)
    }
  }

  return (
    <div className="p-8 space-y-8 animate-fade-in max-w-4xl">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-apple-gray-900 mb-1">Full Assessment Report</h1>
          <p className="text-sm text-apple-gray-400">UNICC AI Safety Council · Complete pipeline from expert analysis to arbitration</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button className="btn-secondary text-xs" onClick={handleDownloadMarkdown}>↓ Markdown</button>
          <button
            className={`btn-primary text-xs ${pdfLoading ? 'opacity-60 pointer-events-none' : ''}`}
            onClick={handleDownloadPdf}
            disabled={pdfLoading}
          >
            {pdfLoading ? 'Generating…' : '↓ PDF'}
          </button>
        </div>
        {pdfError && <p className="text-xs text-apple-red mt-1 w-full">{pdfError}</p>}
      </div>

      {/* 0. System under evaluation */}
      <section className="card p-6">
        <h2 className="text-base font-bold text-apple-gray-900 mb-3">0. System Under Evaluation</h2>
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <span className="text-sm font-semibold">{system_name}</span>
          <span className="text-xs text-apple-gray-400">{agent_id}</span>
          <span className="text-xs text-apple-gray-500">{category}</span>
          <span className="text-xs text-apple-gray-400">{date}</span>
        </div>
        <p className="text-sm text-apple-gray-700 leading-relaxed">{description}</p>
      </section>

      {/* 1. Each expert: analysis → scores → findings (evidence) → judgment */}
      <section>
        <h2 className="text-base font-bold text-apple-gray-900 mb-4">1. Expert Analyses → Judgments & Evidence</h2>
        <div className="space-y-6">
          {expert_reports.map(r => (
            <div key={r.id} className="card p-6 border-l-4 border-apple-blue">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-bold text-apple-gray-900">{r.icon} {r.title}</h3>
                <RecBadge rec={r.recommendation} />
              </div>
              <p className="text-[11px] text-apple-gray-400 mb-4">Elapsed: {r.elapsed}s</p>

              <p className="section-label mb-2">Dimension Scores</p>
              <div className="grid grid-cols-2 gap-2 mb-4">
                {r.scores.map(s => {
                  const pct = (s.value / s.max) * 100
                  // 1=low risk (green) → 5=high risk (red)
                  const color = pct <= 20 ? 'bg-apple-green' : pct <= 60 ? 'bg-apple-orange' : 'bg-apple-red'
                  return (
                    <div key={s.label} className="flex items-center gap-2">
                      <span className="text-xs text-apple-gray-600 shrink-0 w-32">{s.label}</span>
                      <div className="score-bar flex-1 min-w-0">
                        <div className={`score-fill ${color}`} style={{ width: `${pct}%` }} />
                      </div>
                      <span className="text-xs font-semibold shrink-0">{s.value}/{s.max}</span>
                    </div>
                  )
                })}
              </div>

              <p className="section-label mb-2">Key Findings</p>
              <ul className="space-y-3 mb-4">
                {r.findings.map((f, i) => {
                  const isAudit = f.includes('[RISK]') && f.includes('[EVIDENCE]')
                  if (isAudit) {
                    const extract = (tag: string, next: string) => {
                      const re = new RegExp(`\\[${tag}\\]\\s*(.*?)(?=\\[${next}\\]|$)`, 's')
                      return f.match(re)?.[1]?.trim() ?? ''
                    }
                    const risk  = extract('RISK',     'EVIDENCE')
                    const evid  = extract('EVIDENCE', 'IMPACT')
                    const imp   = extract('IMPACT',   'SCORE')
                    const score = extract('SCORE',    '$')
                    return (
                      <li key={i} className="rounded-apple border border-apple-gray-100 bg-apple-gray-50 overflow-hidden">
                        <div className="px-3 py-1.5 bg-apple-gray-100 border-b border-apple-gray-100">
                          <span className="text-[10px] font-bold text-apple-gray-400 uppercase tracking-wider">Finding {i + 1}</span>
                        </div>
                        <div className="p-3 space-y-2">
                          <div className="flex gap-2 items-start">
                            <span className="shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded bg-apple-red-bg text-apple-red uppercase tracking-wide mt-0.5 border border-apple-red/20">Risk</span>
                            <p className="text-xs font-medium text-apple-gray-800 leading-relaxed">{risk}</p>
                          </div>
                          <div className="flex gap-2 items-start">
                            <span className="shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded bg-blue-50 text-blue-600 uppercase tracking-wide mt-0.5 border border-blue-100">Evidence</span>
                            <p className="text-xs text-apple-gray-600 leading-relaxed">{evid}</p>
                          </div>
                          {imp && (
                            <div className="flex gap-2 items-start">
                              <span className="shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded bg-orange-50 text-orange-600 uppercase tracking-wide mt-0.5 border border-orange-100">Impact</span>
                              <p className="text-xs text-apple-gray-600 leading-relaxed">{imp}</p>
                            </div>
                          )}
                          {score && (
                            <div className="flex gap-2 items-start">
                              <span className="shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded bg-purple-50 text-purple-600 uppercase tracking-wide mt-0.5 border border-purple-100">Score</span>
                              <p className="text-xs text-apple-gray-500 leading-relaxed italic">{score}</p>
                            </div>
                          )}
                        </div>
                      </li>
                    )
                  }
                  return (
                    <li key={i} className="flex gap-2 text-sm text-apple-gray-700">
                      <span className="text-apple-red shrink-0 mt-0.5">•</span>
                      <span className="text-xs leading-relaxed">{f}</span>
                    </li>
                  )
                })}
              </ul>

              <p className="section-label mb-2">Regulatory / Framework References</p>
              <div className="flex flex-wrap gap-2">
                {r.framework_refs.map((ref, i) => (
                  <span key={i} className="px-2 py-1 rounded bg-apple-gray-100 text-[11px] text-apple-gray-600">{ref}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 2. Council debate (dialogue) */}
      <section>
        <h2 className="text-base font-bold text-apple-gray-900 mb-4">2. Council Debate (Cross-Expert Critiques)</h2>
        <div className="space-y-4">
          {council_critiques.map((c, i) => (
            <div key={i} className="card p-5 border-l-4 border-apple-orange">
              <p className="text-xs font-semibold text-apple-gray-500 mb-2">
                {c.from} → {c.on} · {c.agrees ? 'Agrees' : 'Disagrees'} · {c.divergence_type.replace(/_/g, ' ')}
              </p>
              <blockquote className="text-sm text-apple-gray-700 italic border-l-2 border-apple-gray-200 pl-3 mb-3">
                &ldquo;{c.key_point}&rdquo;
              </blockquote>
              <p className="text-sm text-apple-gray-700 mb-2"><strong>Stance:</strong> {c.stance}</p>
              <p className="text-[11px] font-semibold text-apple-gray-400 mb-1">Evidence:</p>
              <ul className="space-y-1 text-xs text-apple-gray-600">
                {c.evidence.map((ev, j) => (
                  <li key={j} className="flex gap-2">
                    <span className="text-apple-blue">§</span>
                    <span>{ev}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* 3. Each expert final opinion */}
      <section>
        <h2 className="text-base font-bold text-apple-gray-900 mb-4">3. Expert Final Opinions</h2>
        <div className="card p-5">
          <div className="flex flex-wrap gap-6">
            {expert_reports.map(r => (
              <div key={r.id} className="flex items-center gap-2">
                <span className="text-lg">{r.icon}</span>
                <span className="text-sm font-medium text-apple-gray-700">{r.shortTitle}</span>
                <RecBadge rec={r.recommendation} size="sm" />
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 4. Arbitration outcome */}
      <section>
        <h2 className="text-base font-bold text-apple-gray-900 mb-4">4. Arbitration Outcome</h2>
        <div className={`card overflow-hidden ${decision === 'REJECT' ? 'border-apple-red' : decision === 'REVIEW' ? 'border-apple-orange' : 'border-apple-green'}`}>
          <div className={`px-6 py-4 flex items-center justify-between ${
            decision === 'REJECT' ? 'bg-apple-red-bg' : decision === 'REVIEW' ? 'bg-apple-orange-bg' : 'bg-apple-green-bg'
          }`}>
            <span className="text-sm font-semibold">Council Decision</span>
            <div className="flex items-center gap-2">
              <RecBadge rec={decision} />
              <ConsensusBadge consensus={consensus} />
            </div>
          </div>
          <div className="px-6 py-5 border-t border-apple-gray-100">
            <div className="flex justify-between mb-2">
              <p className="section-label mb-0">Rationale</p>
              <button onClick={handleCopy} className="text-[11px] text-apple-blue hover:underline">
                {copied ? '✓ Copied' : 'Copy'}
              </button>
            </div>
            <p className="text-sm text-apple-gray-700 leading-relaxed">{final_rationale}</p>
          </div>
          {key_conditions.length > 0 && (
            <div className="px-6 py-5 border-t border-apple-gray-100">
              <p className="section-label mb-2">
                {decision === 'REJECT' ? 'Conditions for Re-submission' : 'Required Actions'}
              </p>
              <ol className="space-y-2">
                {key_conditions.map((cond, i) => (
                  <li key={i} className="flex gap-3 text-sm text-apple-gray-700">
                    <span className="shrink-0 font-semibold">{i + 1}.</span>
                    <span>{cond}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      </section>

      <div className="p-4 rounded-apple bg-apple-gray-50 border border-apple-gray-100">
        <p className="text-[11px] text-apple-gray-400 leading-relaxed text-center">
          This report was generated by the UNICC AI Safety Council. All findings should be reviewed by qualified human evaluators.
        </p>
      </div>
    </div>
  )
}

export default FinalReport
