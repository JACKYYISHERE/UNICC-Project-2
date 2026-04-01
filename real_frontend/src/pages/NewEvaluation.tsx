import { type FC, useState, useRef, useEffect } from 'react'
import { hapticButton, hapticSelect } from '../utils/haptic'
import { submitAndWait, analyzeRepo, getRecentAudit, type CouncilReportResponse, type AuditEvent } from '../api/client'
import { parseAgentDoc } from '../utils/parseAgentDoc'

interface Props {
  onSubmit: (report: CouncilReportResponse) => void
}

const CATEGORIES = [
  'Humanitarian Aid', 'Peacekeeping', 'Child Protection', 'Labor Rights',
  'Governance', 'Language & Translation', 'Healthcare', 'Education', 'Other',
]
const DEPLOY_ZONES = [
  'Active Conflict Zone', 'Post-Conflict Zone', 'Development Context',
  'UN Headquarters', 'Field Office', 'Global/Multi-Region',
]

const defaultBackend = (): 'claude' | 'vllm' => {
  const v = import.meta.env.VITE_COUNCIL_BACKEND
  return v === 'claude' ? 'claude' : 'vllm'
}

type InputMode = 'paste' | 'file' | 'repo'

const NewEvaluation: FC<Props> = ({ onSubmit }) => {
  const [step, setStep]         = useState<1 | 2>(1)
  const [loading, setLoading]   = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [liveLog, setLiveLog]   = useState<AuditEvent[]>([])
  const [logOpen, setLogOpen]   = useState(true)
  const logEndRef               = useRef<HTMLDivElement>(null)
  const pollRef                 = useRef<ReturnType<typeof setInterval> | null>(null)

  const [form, setForm] = useState({
    system_name: '', agent_id: '', category: '', deploy_zone: '',
    description: '', capabilities: '', data_sources: '', human_oversight: '',
    live_target_url: '',
  })

  const [inputMode, setInputMode]       = useState<InputMode>('paste')
  const [repoSource, setRepoSource]     = useState('')
  const [analyzing, setAnalyzing]       = useState(false)
  const [analyzeError, setAnalyzeError] = useState<string | null>(null)
  const [autoFilled, setAutoFilled]     = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const set = (k: keyof typeof form) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
      setForm(f => ({ ...f, [k]: e.target.value }))
    }

  // Apply structured analysis result to the form
  const applyResult = (r: { system_name?: string; agent_id?: string; system_description: string; capabilities: string; data_sources: string; human_oversight: string; category: string; deploy_zone: string }) => {
    setForm(f => ({
      ...f,
      system_name:     r.system_name         || f.system_name,
      agent_id:        r.agent_id            || f.agent_id,
      description:     r.system_description  || f.description,
      capabilities:    r.capabilities        || f.capabilities,
      data_sources:    r.data_sources         || f.data_sources,
      human_oversight: r.human_oversight      || f.human_oversight,
      category:        r.category && CATEGORIES.includes(r.category) ? r.category : f.category,
      deploy_zone:     r.deploy_zone && DEPLOY_ZONES.includes(r.deploy_zone) ? r.deploy_zone : f.deploy_zone,
    }))
    setAutoFilled(true)
    setInputMode('paste')
  }

  // GitHub / local repo → structured extraction
  const handleRepoAnalyze = async () => {
    if (!repoSource.trim()) return
    hapticButton()
    setAnalyzeError(null)
    setAnalyzing(true)
    try {
      const result = await analyzeRepo({ source: repoSource.trim(), backend: defaultBackend() })
      applyResult(result)
    } catch (e) {
      setAnalyzeError(e instanceof Error ? e.message : String(e))
    } finally {
      setAnalyzing(false)
    }
  }

  // File upload → parse text → send to backend for structured extraction
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    setAnalyzeError(null)
    setAnalyzing(true)
    hapticSelect()
    try {
      const text = await parseAgentDoc(f)
      const result = await analyzeRepo({ text, backend: defaultBackend() })
      applyResult(result)
    } catch (err) {
      setAnalyzeError(err instanceof Error ? err.message : String(err))
    } finally {
      setAnalyzing(false)
      e.target.value = ''
    }
  }

  // Auto-scroll log to bottom when new events arrive
  useEffect(() => {
    if (loading && logOpen) logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [liveLog, loading, logOpen])

  const startPolling = () => {
    setLiveLog([])
    pollRef.current = setInterval(async () => {
      try {
        const events = await getRecentAudit(30)
        setLiveLog(events)
      } catch { /* ignore poll errors */ }
    }, 1500)
  }
  const stopPolling = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }

  const handleSubmit = async () => {
    setSubmitError(null)
    setLoading(true)
    startPolling()
    try {
      const payload: Parameters<typeof submitAndWait>[0] = {
        agent_id: form.agent_id,
        system_name: form.system_name || form.agent_id,
        system_description: [form.description, form.capabilities].filter(Boolean).join('\n\n'),
        purpose: form.category || undefined,
        deployment_context: form.deploy_zone || undefined,
        data_access:    form.data_sources    ? [form.data_sources]    : [],
        risk_indicators: form.human_oversight ? [form.human_oversight] : [],
        backend: defaultBackend(),
        vllm_base_url: import.meta.env.VITE_VLLM_BASE_URL || 'http://127.0.0.1:8000',
        vllm_model: import.meta.env.VITE_VLLM_MODEL || 'meta-llama/Meta-Llama-3-70B-Instruct',
        live_target_url: form.live_target_url.trim() || undefined,
      }
      // submitAndWait: POST returns immediately, then polls /status every 5 s
      const report = await submitAndWait(payload)
      stopPolling()
      // Final poll to capture completion events
      try { setLiveLog(await getRecentAudit(30)) } catch { /* ignore */ }
      onSubmit(report)
    } catch (e) {
      stopPolling()
      setSubmitError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const canProceed = !!(form.system_name && form.agent_id && form.description)

  return (
    <div className="p-8 max-w-3xl mx-auto animate-fade-in">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-apple-gray-900 mb-1">New Evaluation</h1>
        <p className="text-sm text-apple-gray-400">Submit an AI system for safety assessment by the UNICC Council</p>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-2 mb-7">
        {(['System Details', 'Review & Submit'] as const).map((label, i) => {
          const s = (i + 1) as 1 | 2
          const done   = step > s
          const active = step === s
          return (
            <div key={label} className="flex items-center gap-2">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold transition-all
                ${done ? 'bg-apple-green text-white' : active ? 'bg-apple-blue text-white' : 'bg-apple-gray-200 text-apple-gray-500'}`}>
                {done ? '✓' : s}
              </div>
              <span className={`text-xs font-medium ${active ? 'text-apple-gray-900' : 'text-apple-gray-400'}`}>{label}</span>
              {i < 1 && <div className="w-8 h-px bg-apple-gray-200 mx-1" />}
            </div>
          )
        })}
      </div>

      <div className="card p-7 space-y-6">

        {/* ── Step 1 ─────────────────────────────────────────────── */}
        {step === 1 && (
          <div className="space-y-6 animate-slide-up">

            {/* System identification */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-apple-gray-600 mb-1.5">System Name *</label>
                <input className="input-field" placeholder="e.g. RefugeeAssist v2"
                  value={form.system_name} onChange={set('system_name')} />
              </div>
              <div>
                <label className="block text-xs font-semibold text-apple-gray-600 mb-1.5">Agent ID *</label>
                <input className="input-field" placeholder="e.g. refugee-assist-v2"
                  value={form.agent_id} onChange={set('agent_id')} />
              </div>
            </div>

            {/* Input mode */}
            <div>
              <p className="section-label">System Description *</p>
              <div className="flex gap-4 mb-3 flex-wrap items-center">
                {(['paste', 'file', 'repo'] as InputMode[]).map(m => (
                  <label key={m} className="flex items-center gap-2 cursor-pointer">
                    <input type="radio" name="inputMode" checked={inputMode === m}
                      onChange={() => { hapticSelect(); setInputMode(m); setAnalyzeError(null) }}
                      className="text-apple-blue" />
                    <span className="text-sm capitalize">
                      {m === 'paste' ? 'Paste text' : m === 'file' ? 'Upload file' : 'GitHub / Local repo'}
                    </span>
                  </label>
                ))}

                {/* File picker */}
                {inputMode === 'file' && (
                  <>
                    <input ref={fileInputRef} type="file" accept=".pdf,.json,.md,.markdown"
                      className="hidden" onChange={handleFileChange} />
                    <button type="button" className="btn-secondary text-xs"
                      onClick={() => fileInputRef.current?.click()} disabled={analyzing}>
                      {analyzing ? 'Analyzing…' : 'Choose PDF / JSON / MD'}
                    </button>
                  </>
                )}
              </div>

              {/* Repo input */}
              {inputMode === 'repo' && (
                <div className="mb-3 space-y-2">
                  <div className="flex gap-2">
                    <input
                      className="input-field font-mono text-xs flex-1"
                      placeholder="https://github.com/owner/repo  or  /absolute/local/path"
                      value={repoSource}
                      onChange={e => setRepoSource(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') void handleRepoAnalyze() }}
                    />
                    <button
                      type="button"
                      className={`btn-primary text-xs whitespace-nowrap ${analyzing || !repoSource.trim() ? 'opacity-40 pointer-events-none' : ''}`}
                      onClick={handleRepoAnalyze}
                      disabled={analyzing || !repoSource.trim()}
                    >
                      {analyzing ? 'Analyzing…' : 'Auto-fill →'}
                    </button>
                  </div>
                  <p className="text-[11px] text-apple-gray-400">
                    Reads README, code, and dependencies — auto-fills all fields below.
                  </p>
                </div>
              )}

              {/* Analyzing spinner */}
              {analyzing && (
                <div className="flex items-center gap-2 text-xs text-apple-gray-500 mb-3">
                  <div className="w-3 h-3 border border-apple-blue border-t-transparent rounded-full animate-spin" />
                  Reading and analysing…
                </div>
              )}
              {analyzeError && <p className="text-xs text-apple-red mb-2">{analyzeError}</p>}
              {autoFilled && !analyzeError && (
                <p className="text-[11px] text-apple-green mb-2">✓ Fields auto-filled — review and edit as needed.</p>
              )}

              {/* Description textarea */}
              <textarea
                className="input-field resize-none h-28"
                placeholder="Describe what this AI system does…"
                value={form.description}
                onChange={e => { setForm(f => ({ ...f, description: e.target.value })); setAutoFilled(false) }}
              />
              {/* Paste mode: offer to analyze text for auto-fill */}
              {inputMode === 'paste' && form.description.trim().length > 80 && !autoFilled && (
                <div className="flex items-center gap-3 mt-1.5">
                  <button
                    type="button"
                    className={`btn-secondary text-xs ${analyzing ? 'opacity-40 pointer-events-none' : ''}`}
                    onClick={async () => {
                      hapticButton()
                      setAnalyzeError(null)
                      setAnalyzing(true)
                      try {
                        const result = await analyzeRepo({ text: form.description, backend: defaultBackend() })
                        applyResult(result)
                      } catch (e) {
                        setAnalyzeError(e instanceof Error ? e.message : String(e))
                      } finally {
                        setAnalyzing(false)
                      }
                    }}
                    disabled={analyzing}
                  >
                    {analyzing ? 'Analyzing…' : '✦ Auto-fill from this text'}
                  </button>
                  <span className="text-[11px] text-apple-gray-400">Fills category, zone & capabilities automatically</span>
                </div>
              )}
            </div>

            {/* Capabilities */}
            <div>
              <label className="block text-xs font-semibold text-apple-gray-600 mb-1.5">Key Capabilities</label>
              <textarea
                className="input-field resize-none h-16"
                placeholder="e.g. automated allocation, biometric matching, NLP…"
                value={form.capabilities}
                onChange={set('capabilities')}
              />
            </div>

            {/* Category + Deploy zone */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-apple-gray-600 mb-1.5">Category</label>
                <select className="input-field" value={form.category} onChange={set('category')}>
                  <option value="">Select category</option>
                  {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-apple-gray-600 mb-1.5">Deployment Zone</label>
                <select className="input-field" value={form.deploy_zone} onChange={set('deploy_zone')}>
                  <option value="">Select zone</option>
                  {DEPLOY_ZONES.map(z => <option key={z}>{z}</option>)}
                </select>
              </div>
            </div>

            {form.deploy_zone === 'Active Conflict Zone' || form.deploy_zone === 'Post-Conflict Zone' ? (
              <div className="p-3 rounded-apple bg-apple-blue-light border border-blue-100 flex gap-2.5">
                <span className="text-blue-500 text-sm mt-0.5">ℹ</span>
                <p className="text-xs text-apple-blue leading-relaxed">
                  Systems in <strong>{form.deploy_zone}</strong> automatically qualify as High-Risk under EU AI Act Annex III.
                </p>
              </div>
            ) : null}

            {/* Additional context — collapsed */}
            <details className="group">
              <summary className="text-[11px] text-apple-gray-500 cursor-pointer select-none list-none flex items-center gap-1 hover:text-apple-gray-700">
                <span className="group-open:rotate-90 inline-block transition-transform">▶</span>
                Additional context (Data Sources · Human Oversight)
              </summary>
              <div className="mt-3 grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-apple-gray-600 mb-1.5">Data Sources</label>
                  <textarea className="input-field resize-none h-20"
                    placeholder="Databases, APIs, user-provided data…"
                    value={form.data_sources} onChange={set('data_sources')} />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-apple-gray-600 mb-1.5">Human Oversight</label>
                  <textarea className="input-field resize-none h-20"
                    placeholder="Review processes, appeal mechanisms…"
                    value={form.human_oversight} onChange={set('human_oversight')} />
                </div>
              </div>
            </details>

            {/* Live Attack Target (optional) */}
            <details className="group">
              <summary className="text-[11px] text-apple-gray-500 cursor-pointer select-none list-none flex items-center gap-1 hover:text-apple-gray-700">
                <span className="group-open:rotate-90 inline-block transition-transform">▶</span>
                Live Attack Testing — Expert 1 (optional)
              </summary>
              <div className="mt-3 space-y-2">
                <div className="flex items-center gap-2 p-2.5 rounded-apple bg-orange-50 border border-orange-100">
                  <span className="text-orange-500 text-sm">⚡</span>
                  <p className="text-xs text-orange-700 leading-relaxed">
                    If set, Expert 1 will send live adversarial probes to this endpoint instead of static document analysis.
                    The target must implement the Dify workflow API at <code className="font-mono">/v1/workflows/run</code>.
                  </p>
                </div>
                <input
                  className="input-field font-mono text-xs"
                  placeholder="http://localhost:5001  (leave blank for document analysis)"
                  value={form.live_target_url}
                  onChange={set('live_target_url')}
                />
              </div>
            </details>
          </div>
        )}

        {/* ── Step 2: Review ───────────────────────────────────────── */}
        {step === 2 && (
          <div className="space-y-5 animate-slide-up">
            <p className="section-label">Review Submission</p>
            <div className="space-y-3">
              {[
                ['System Name',    form.system_name],
                ['Agent ID',       form.agent_id],
                ['Category',       form.category || '—'],
                ['Deployment Zone',form.deploy_zone || '—'],
                ...(form.live_target_url.trim() ? [['Live Attack Target', form.live_target_url.trim()]] : []),
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between py-2.5 border-b border-apple-gray-100">
                  <span className="text-xs text-apple-gray-400">{k}</span>
                  <span className={`text-sm font-semibold ${k === 'Live Attack Target' ? 'text-orange-600 font-mono text-xs' : 'text-apple-gray-900'}`}>{v}</span>
                </div>
              ))}
            </div>

            <div className="p-4 rounded-apple bg-apple-gray-50 border border-apple-gray-100">
              <p className="text-xs font-semibold text-apple-gray-600 mb-2">Description</p>
              <p className="text-sm text-apple-gray-700 leading-relaxed line-clamp-5">{form.description}</p>
            </div>

            <div className="p-4 rounded-apple bg-apple-gray-50 border border-apple-gray-100">
              <p className="text-xs font-semibold text-apple-gray-600 mb-3">Evaluation Pipeline</p>
              <div className="flex items-center gap-2">
                {['Expert 1\nSecurity', 'Expert 2\nGovernance', 'Expert 3\nUN Mission', 'Council\nReview', 'Final\nReport'].map((label, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <div className="text-center">
                      <div className="w-9 h-9 rounded-full border-2 border-apple-blue bg-apple-blue-light flex items-center justify-center text-apple-blue text-xs font-bold">
                        {i + 1}
                      </div>
                      <p className="text-[10px] text-apple-gray-400 mt-1 whitespace-pre-line leading-tight">{label}</p>
                    </div>
                    {i < 4 && <div className="w-5 h-px bg-apple-gray-200 mt-[-14px]" />}
                  </div>
                ))}
              </div>
            </div>

            {submitError && (
              <div className="p-4 rounded-apple bg-apple-red-bg border border-apple-red/30">
                <p className="text-sm text-apple-red font-medium">Submit failed</p>
                <p className="text-xs text-apple-gray-600 mt-1">{submitError}</p>
                <p className="text-[11px] text-apple-gray-400 mt-2">Make sure the backend is running: <code className="font-mono">uvicorn frontend_api.main:app --port 8100</code></p>
              </div>
            )}

            {loading && (
              <div className="space-y-4">
                <div className="flex flex-col items-center py-4 gap-3">
                  <div className="w-8 h-8 border-2 border-apple-blue border-t-transparent rounded-full animate-spin" />
                  <p className="text-sm text-apple-gray-500">Running Council evaluation (3 Experts + Critiques + Arbitration)…</p>
                </div>

                {/* Live audit log */}
                <div className="rounded-apple border border-apple-gray-100 overflow-hidden">
                  <button
                    className="w-full flex items-center justify-between px-4 py-2.5 bg-apple-gray-50 hover:bg-apple-gray-100 transition-colors"
                    onClick={() => setLogOpen(o => !o)}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] font-bold uppercase tracking-wider text-apple-gray-400">Live Pipeline Log</span>
                      {liveLog.length > 0 && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-apple-blue text-white font-semibold animate-pulse">
                          {liveLog.length} events
                        </span>
                      )}
                    </div>
                    <span className="text-apple-gray-400 text-xs">{logOpen ? '▲' : '▼'}</span>
                  </button>

                  {logOpen && (
                    <div className="bg-[#1c1c1e] max-h-48 overflow-y-auto font-mono">
                      {liveLog.length === 0 ? (
                        <div className="flex items-center gap-2 px-4 py-3 text-[11px] text-[#636366]">
                          <div className="w-2 h-2 rounded-full bg-apple-blue animate-pulse" />
                          Waiting for pipeline events…
                        </div>
                      ) : (
                        liveLog.map((ev, i) => (
                          <div key={ev.event_id}
                            className={`flex gap-3 px-4 py-1.5 text-[11px] leading-relaxed
                              ${i % 2 === 0 ? '' : 'bg-white/[0.02]'}`}>
                            <span className="text-[#636366] shrink-0">{ev.created_at.slice(11, 19)}</span>
                            <span className={`shrink-0 w-10 font-bold ${
                              ev.severity === 'ERROR' ? 'text-apple-red' :
                              ev.severity === 'WARN'  ? 'text-apple-orange' : 'text-apple-green'
                            }`}>{ev.severity.slice(0,4)}</span>
                            <span className="text-[#98989d] shrink-0 w-24 truncate">
                              {ev.actor.replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase())}
                            </span>
                            <span className="text-[#e5e5ea] flex-1 min-w-0">{ev.message}</span>
                          </div>
                        ))
                      )}
                      <div ref={logEndRef} />
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Navigation */}
        {!loading && (
          <div className="flex justify-between pt-2 border-t border-apple-gray-100">
            {step > 1
              ? <button className="btn-secondary" onClick={() => { hapticSelect(); setStep(1) }}>Back</button>
              : <div />
            }
            {step === 1
              ? (
                <button
                  className={`btn-primary ${!canProceed ? 'opacity-40 pointer-events-none' : ''}`}
                  onClick={() => { hapticButton(); setStep(2) }}
                  disabled={!canProceed}
                >
                  Review →
                </button>
              )
              : (
                <button className="btn-primary" onClick={() => { hapticButton(); void handleSubmit() }}>
                  Submit for Evaluation →
                </button>
              )
            }
          </div>
        )}
      </div>
    </div>
  )
}

export default NewEvaluation
