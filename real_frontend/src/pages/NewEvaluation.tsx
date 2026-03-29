import { type FC, useState, useRef } from 'react'
import { hapticButton, hapticSelect } from '../utils/haptic'
import { submitCouncilEvaluation, analyzeRepo, type CouncilReportResponse } from '../api/client'
import { parseAgentDoc } from '../utils/parseAgentDoc'

interface Props {
  /** 提交成功后调用，传入真实 Council 报告 */
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

const defaultCouncilBackend = (): 'claude' | 'vllm' => {
  const v = import.meta.env.VITE_COUNCIL_BACKEND
  return v === 'vllm' ? 'vllm' : 'claude'
}

const NewEvaluation: FC<Props> = ({ onSubmit }) => {
  const [step, setStep] = useState<1 | 2 | 3>(1)
  const [loading, setLoading] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [form, setForm] = useState({
    system_name: '', agent_id: '', category: '', deploy_zone: '',
    description: '', capabilities: '', data_sources: '', human_oversight: '',
    mode: 'B' as 'A' | 'B',
    llm_backend: defaultCouncilBackend(),
    vllm_base_url:
      (import.meta.env.VITE_VLLM_BASE_URL as string | undefined) ?? 'http://127.0.0.1:8000',
    vllm_model:
      (import.meta.env.VITE_VLLM_MODEL as string | undefined) ??
      'meta-llama/Meta-Llama-3-70B-Instruct',
  })
  const [inputMode, setInputMode] = useState<'paste' | 'file' | 'repo'>('paste')
  const [fileError, setFileError] = useState<string | null>(null)
  const [fileLoading, setFileLoading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [repoSource, setRepoSource] = useState('')
  const [repoAnalyzing, setRepoAnalyzing] = useState(false)
  const [repoError, setRepoError] = useState<string | null>(null)

  const handleSubmit = async () => {
    setSubmitError(null)
    setLoading(true)
    try {
      const payload: Parameters<typeof submitCouncilEvaluation>[0] = {
        agent_id: form.agent_id,
        system_name: form.system_name || form.agent_id,
        system_description: [form.description, form.capabilities].filter(Boolean).join('\n\n'),
        purpose: form.category || undefined,
        deployment_context: form.deploy_zone || undefined,
        data_access: form.data_sources ? [form.data_sources] : [],
        risk_indicators: form.human_oversight ? [form.human_oversight] : [],
        backend: form.llm_backend,
      }
      if (form.llm_backend === 'vllm') {
        const url = form.vllm_base_url.trim()
        const model = form.vllm_model.trim()
        if (url) payload.vllm_base_url = url
        if (model) payload.vllm_model = model
      }
      const report = await submitCouncilEvaluation(payload)
      onSubmit(report)
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  const canProceed1 = form.system_name && form.agent_id && form.category && form.deploy_zone
  const canProceed2 = form.description && form.capabilities

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    setFileError(null)
    setFileLoading(true)
    hapticSelect()
    try {
      const text = await parseAgentDoc(f)
      setForm(prev => ({ ...prev, description: text }))
    } catch (err) {
      setFileError(err instanceof Error ? err.message : String(err))
    } finally {
      setFileLoading(false)
      e.target.value = ''
    }
  }

  const handleRepoAnalyze = async () => {
    if (!repoSource.trim()) return
    setRepoError(null)
    setRepoAnalyzing(true)
    hapticButton()
    try {
      const result = await analyzeRepo({
        source: repoSource.trim(),
        backend: form.llm_backend,
        vllm_base_url: form.vllm_base_url,
        vllm_model: form.vllm_model,
      })
      setForm(f => ({ ...f, description: result.system_description }))
      setInputMode('paste')
    } catch (err) {
      setRepoError(err instanceof Error ? err.message : String(err))
    } finally {
      setRepoAnalyzing(false)
    }
  }

  return (
    <div className="p-8 max-w-3xl mx-auto animate-fade-in">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-apple-gray-900 mb-1">New Evaluation</h1>
        <p className="text-sm text-apple-gray-400">Submit an AI system for safety assessment by the UNICC Council</p>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-2 mb-8">
        {(['System Info', 'Capabilities', 'Review & Submit'] as const).map((label, i) => {
          const s = (i + 1) as 1 | 2 | 3
          const done = step > s
          const active = step === s
          return (
            <div key={label} className="flex items-center gap-2">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold transition-all
                ${done ? 'bg-apple-green text-white' : active ? 'bg-apple-blue text-white' : 'bg-apple-gray-200 text-apple-gray-500'}`}>
                {done ? '✓' : s}
              </div>
              <span className={`text-xs font-medium ${active ? 'text-apple-gray-900' : 'text-apple-gray-400'}`}>{label}</span>
              {i < 2 && <div className="w-8 h-px bg-apple-gray-200 mx-1" />}
            </div>
          )
        })}
      </div>

      <div className="card p-7 space-y-6">
        {/* Step 1 */}
        {step === 1 && (
          <div className="space-y-5 animate-slide-up">
            <div>
              <p className="section-label">System Identification</p>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-apple-gray-600 mb-1.5">System Name *</label>
                  <input className="input-field" placeholder="e.g. RefugeeAssist v2" value={form.system_name} onChange={set('system_name')} />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-apple-gray-600 mb-1.5">Agent ID *</label>
                  <input className="input-field" placeholder="e.g. refugee-assist-v2" value={form.agent_id} onChange={set('agent_id')} />
                </div>
              </div>
            </div>
            <div>
              <p className="section-label">Council LLM backend</p>
              <p className="text-[11px] text-apple-gray-400 mb-2">
                Full pipeline (3 experts + critiques) uses this backend. Optional env defaults:{' '}
                <code className="text-[10px] bg-apple-gray-100 px-1 rounded">VITE_COUNCIL_BACKEND</code>,{' '}
                <code className="text-[10px] bg-apple-gray-100 px-1 rounded">VITE_VLLM_BASE_URL</code>,{' '}
                <code className="text-[10px] bg-apple-gray-100 px-1 rounded">VITE_VLLM_MODEL</code>.
              </p>
              <div className="flex flex-col gap-3 mt-2">
                <label className={`flex items-start gap-3 p-3 rounded-apple border-2 cursor-pointer transition-colors ${form.llm_backend === 'claude' ? 'border-apple-blue bg-apple-blue-light' : 'border-apple-gray-100 hover:border-apple-gray-200'}`}>
                  <input
                    type="radio"
                    name="llm_backend"
                    checked={form.llm_backend === 'claude'}
                    onChange={() => { hapticSelect(); setForm(f => ({ ...f, llm_backend: 'claude' })) }}
                    className="mt-1 w-4 h-4 text-apple-blue"
                  />
                  <div>
                    <span className="text-sm font-semibold text-apple-gray-900">Claude (Anthropic API)</span>
                    <p className="text-xs text-apple-gray-500 mt-0.5">Server needs ANTHROPIC_API_KEY. No vLLM required.</p>
                  </div>
                </label>
                <label className={`flex items-start gap-3 p-3 rounded-apple border-2 cursor-pointer transition-colors ${form.llm_backend === 'vllm' ? 'border-apple-blue bg-apple-blue-light' : 'border-apple-gray-100 hover:border-apple-gray-200'}`}>
                  <input
                    type="radio"
                    name="llm_backend"
                    checked={form.llm_backend === 'vllm'}
                    onChange={() => { hapticSelect(); setForm(f => ({ ...f, llm_backend: 'vllm' })) }}
                    className="mt-1 w-4 h-4 text-apple-blue"
                  />
                  <div className="min-w-0 flex-1">
                    <span className="text-sm font-semibold text-apple-gray-900">vLLM / SLM (OpenAI-compatible)</span>
                    <p className="text-xs text-apple-gray-500 mt-0.5 mb-3">Experts and critiques call your inference server. Ensure the URL is reachable from the machine running frontend_api.</p>
                    {form.llm_backend === 'vllm' && (
                      <div className="space-y-3 pt-1">
                        <div>
                          <label className="block text-[11px] font-semibold text-apple-gray-600 mb-1">vLLM base URL</label>
                          <input
                            className="input-field font-mono text-xs"
                            placeholder="http://127.0.0.1:8000"
                            value={form.vllm_base_url}
                            onChange={e => setForm(f => ({ ...f, vllm_base_url: e.target.value }))}
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] font-semibold text-apple-gray-600 mb-1">Model name</label>
                          <input
                            className="input-field font-mono text-xs"
                            placeholder="meta-llama/Meta-Llama-3-70B-Instruct"
                            value={form.vllm_model}
                            onChange={e => setForm(f => ({ ...f, vllm_model: e.target.value }))}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                </label>
              </div>
            </div>

            <div>
              <p className="section-label">Expert 1 style (reference only)</p>
              <p className="text-[11px] text-apple-gray-400 mb-2">Council run uses Expert 1 document-analysis path from the orchestrator. Modes below are for future Expert1-only API use.</p>
              <div className="flex flex-col gap-3 mt-2">
                <label className={`flex items-start gap-3 p-3 rounded-apple border-2 cursor-pointer transition-colors ${form.mode === 'A' ? 'border-apple-blue bg-apple-blue-light' : 'border-apple-gray-100 hover:border-apple-gray-200'}`}>
                  <input type="radio" name="mode" value="A" checked={form.mode === 'A'} onChange={() => { hapticSelect(); setForm(f => ({ ...f, mode: 'A' })) }} className="mt-1 w-4 h-4 text-apple-blue" />
                  <div>
                    <span className="text-sm font-semibold text-apple-gray-900">Mode A</span>
                    <p className="text-xs text-apple-gray-500 mt-0.5">文档分析 — 仅根据系统描述打分，不执行 live 攻击（更快）</p>
                  </div>
                </label>
                <label className={`flex items-start gap-3 p-3 rounded-apple border-2 cursor-pointer transition-colors ${form.mode === 'B' ? 'border-apple-blue bg-apple-blue-light' : 'border-apple-gray-100 hover:border-apple-gray-200'}`}>
                  <input type="radio" name="mode" value="B" checked={form.mode === 'B'} onChange={() => { hapticSelect(); setForm(f => ({ ...f, mode: 'B' })) }} className="mt-1 w-4 h-4 text-apple-blue" />
                  <div>
                    <span className="text-sm font-semibold text-apple-gray-900">Mode B</span>
                    <p className="text-xs text-apple-gray-500 mt-0.5">完整主动攻击 — PROBE → BOUNDARY → ATTACK（含 live 攻击，更全面）</p>
                  </div>
                </label>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-apple-gray-600 mb-1.5">Category *</label>
                <select className="input-field" value={form.category} onChange={set('category')}>
                  <option value="">Select category</option>
                  {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-apple-gray-600 mb-1.5">Deployment Zone *</label>
                <select className="input-field" value={form.deploy_zone} onChange={set('deploy_zone')}>
                  <option value="">Select zone</option>
                  {DEPLOY_ZONES.map(z => <option key={z}>{z}</option>)}
                </select>
              </div>
            </div>

            <div className="p-4 rounded-apple bg-apple-blue-light border border-blue-100">
              <div className="flex gap-2.5">
                <span className="text-blue-500 text-base mt-0.5">ℹ</span>
                <p className="text-xs text-apple-blue leading-relaxed">
                  Systems deployed in <strong>Active or Post-Conflict Zones</strong> automatically qualify as High-Risk under EU AI Act Annex III and will receive additional security scrutiny.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Step 2 */}
        {step === 2 && (
          <div className="space-y-5 animate-slide-up">
            <div>
              <p className="section-label">Agent Description Input</p>
              <div className="flex gap-4 mb-3 flex-wrap">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="radio" name="inputMode" checked={inputMode === 'paste'} onChange={() => { hapticSelect(); setInputMode('paste'); setFileError(null); setRepoError(null) }} className="text-apple-blue" />
                  <span className="text-sm">Paste text</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="radio" name="inputMode" checked={inputMode === 'file'} onChange={() => { hapticSelect(); setInputMode('file'); setFileError(null); setRepoError(null) }} className="text-apple-blue" />
                  <span className="text-sm">Upload file</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="radio" name="inputMode" checked={inputMode === 'repo'} onChange={() => { hapticSelect(); setInputMode('repo'); setFileError(null); setRepoError(null) }} className="text-apple-blue" />
                  <span className="text-sm">GitHub / Local repo</span>
                </label>
                {inputMode === 'file' && (
                  <>
                    <input ref={fileInputRef} type="file" accept=".pdf,.json,.md,.markdown" className="hidden" onChange={handleFileChange} />
                    <button type="button" className="btn-secondary text-xs" onClick={() => fileInputRef.current?.click()} disabled={fileLoading}>
                      {fileLoading ? 'Parsing…' : 'PDF / JSON / Markdown'}
                    </button>
                  </>
                )}
              </div>
              {fileError && <p className="text-xs text-apple-red mb-2">{fileError}</p>}
              {inputMode === 'repo' && (
                <div className="mb-4 space-y-2">
                  <div className="flex gap-2">
                    <input
                      className="input-field font-mono text-xs flex-1"
                      placeholder="https://github.com/owner/repo  or  /absolute/local/path"
                      value={repoSource}
                      onChange={e => setRepoSource(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') handleRepoAnalyze() }}
                    />
                    <button
                      type="button"
                      className={`btn-primary text-xs whitespace-nowrap ${repoAnalyzing || !repoSource.trim() ? 'opacity-40 pointer-events-none' : ''}`}
                      onClick={handleRepoAnalyze}
                      disabled={repoAnalyzing || !repoSource.trim()}
                    >
                      {repoAnalyzing ? 'Analyzing…' : 'Analyze →'}
                    </button>
                  </div>
                  {repoAnalyzing && (
                    <div className="flex items-center gap-2 text-xs text-apple-gray-500">
                      <div className="w-3 h-3 border border-apple-blue border-t-transparent rounded-full animate-spin" />
                      Fetching files and generating description via {form.llm_backend === 'vllm' ? 'vLLM' : 'Claude'}…
                    </div>
                  )}
                  {repoError && <p className="text-xs text-apple-red">{repoError}</p>}
                  <p className="text-[11px] text-apple-gray-400">
                    Uses the LLM backend selected in Step 1. After analysis the description will appear below for review.
                  </p>
                </div>
              )}
            </div>
            <div>
              <label className="block text-xs font-semibold text-apple-gray-600 mb-1.5">System Description *</label>
              <textarea
                className="input-field resize-none h-28"
                placeholder="Describe what this AI system does... Or upload a PDF, JSON, or Markdown file above."
                value={form.description}
                onChange={set('description')}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-apple-gray-600 mb-1.5">Key Capabilities *</label>
              <textarea
                className="input-field resize-none h-20"
                placeholder="List the main capabilities: e.g. automated allocation, biometric matching, natural language processing..."
                value={form.capabilities}
                onChange={set('capabilities')}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-apple-gray-600 mb-1.5">Data Sources</label>
                <textarea
                  className="input-field resize-none h-20"
                  placeholder="Describe data inputs: databases, APIs, user-provided data..."
                  value={form.data_sources}
                  onChange={set('data_sources')}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-apple-gray-600 mb-1.5">Human Oversight</label>
                <textarea
                  className="input-field resize-none h-20"
                  placeholder="Describe any human review processes, appeal mechanisms, override capabilities..."
                  value={form.human_oversight}
                  onChange={set('human_oversight')}
                />
              </div>
            </div>
          </div>
        )}

        {/* Step 3 */}
        {step === 3 && (
          <div className="space-y-5 animate-slide-up">
            <p className="section-label">Review Submission</p>
            <div className="space-y-3">
              {[
                ['System Name', form.system_name],
                ['Agent ID', form.agent_id],
                ['Category', form.category],
                ['Deployment Zone', form.deploy_zone],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between py-2.5 border-b border-apple-gray-100">
                  <span className="text-xs text-apple-gray-400">{k}</span>
                  <span className="text-sm font-semibold text-apple-gray-900">{v}</span>
                </div>
              ))}
            </div>
            <div className="p-4 rounded-apple bg-apple-gray-50 border border-apple-gray-100">
              <p className="text-xs font-semibold text-apple-gray-600 mb-2">Description</p>
              <p className="text-sm text-apple-gray-700 leading-relaxed">{form.description}</p>
            </div>

            <div className="p-4 rounded-apple bg-apple-gray-50 border border-apple-gray-100">
              <p className="text-xs font-semibold text-apple-gray-600 mb-2">LLM Backend</p>
              {form.llm_backend === 'claude' ? (
                <p className="text-sm text-apple-gray-700">Claude (Anthropic API) — server needs <code className="text-[11px] bg-apple-gray-100 px-1 rounded">ANTHROPIC_API_KEY</code></p>
              ) : (
                <div className="space-y-1">
                  <p className="text-sm text-apple-gray-700">vLLM / SLM (OpenAI-compatible)</p>
                  <p className="text-xs text-apple-gray-500 font-mono">{form.vllm_base_url || 'http://127.0.0.1:8000'}</p>
                  <p className="text-xs text-apple-gray-500 font-mono">{form.vllm_model || 'meta-llama/Meta-Llama-3-70B-Instruct'}</p>
                </div>
              )}
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
                <p className="text-sm text-apple-red font-medium">提交失败</p>
                <p className="text-xs text-apple-gray-600 mt-1">{submitError}</p>
                <p className="text-[11px] text-apple-gray-400 mt-2">请确认后端 API 已启动（uvicorn frontend_api.main:app --port 8100）并重试。</p>
              </div>
            )}
            {loading && (
              <div className="flex flex-col items-center py-6 gap-3">
                <div className="w-8 h-8 border-2 border-apple-blue border-t-transparent rounded-full animate-spin" />
                <p className="text-sm text-apple-gray-500">正在执行 Council 全链路评估（3 Experts + Critiques + Arbitration）…</p>
              </div>
            )}
          </div>
        )}

        {/* Navigation */}
        {!loading && (
          <div className="flex justify-between pt-2 border-t border-apple-gray-100">
            {step > 1
              ? <button className="btn-secondary" onClick={() => { hapticSelect(); setStep(s => (s - 1) as 1 | 2 | 3) }}>Back</button>
              : <div />
            }
            {step < 3
              ? (
                <button
                  className={`btn-primary ${(step === 1 ? !canProceed1 : !canProceed2) ? 'opacity-40 pointer-events-none' : ''}`}
                  onClick={() => { hapticButton(); setStep(s => (s + 1) as 1 | 2 | 3) }}
                >
                  Continue
                </button>
              )
              : (
                <button className="btn-primary" onClick={() => { hapticButton(); handleSubmit() }}>
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
