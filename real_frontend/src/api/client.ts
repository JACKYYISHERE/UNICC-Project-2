/**
 * Frontend API client
 * Default backend target: frontend_api suite at http://localhost:8100
 */

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8100'

export interface Expert1AttackRequest {
  agent_id: string
  system_name: string
  system_description: string
  purpose?: string
  deployment_context?: string
  data_access?: string[]
  risk_indicators?: string[]
  /** Mode A: 文档分析（仅打分） | Mode B: 完整主动攻击 */
  mode?: 'A' | 'B'
  mock_level?: 'low' | 'medium' | 'high'
  backend?: 'claude' | 'mock'
}

export interface Expert1AttackResponse {
  expert: string
  agent_id: string
  session_id: string
  recommendation?: string
  risk_tier?: string
  phase_summaries?: { probe?: unknown; boundary?: unknown; attack?: unknown }
  test_coverage?: { attack_techniques_tested?: unknown[] }
  dimension_scores?: Record<string, number>
  key_findings?: string[]
  [key: string]: unknown
}

export interface CouncilEvaluateRequest {
  agent_id: string
  system_name: string
  system_description: string
  purpose?: string
  deployment_context?: string
  data_access?: string[]
  risk_indicators?: string[]
  backend?: 'claude' | 'vllm'
  vllm_base_url?: string
  vllm_model?: string
  /** If set, Expert 1 runs in Live Attack mode against this URL (e.g. http://localhost:5001) */
  live_target_url?: string
}

export interface CouncilReportResponse {
  incident_id: string
  agent_id: string
  system_name?: string
  system_description?: string
  session_id: string
  timestamp: string
  expert_reports: Record<string, any>
  critiques: Record<string, any>
  council_decision: Record<string, any> | null
  council_note: string
}

export interface EvaluationListItem {
  incident_id: string
  agent_id: string
  system_name: string
  created_at: string
  decision: 'APPROVE' | 'REVIEW' | 'REJECT'
  risk_tier?: string | null
  consensus?: 'FULL' | 'PARTIAL' | 'SPLIT' | null
  summary_core?: string
  file_path?: string
  rec_security?: string | null
  rec_governance?: string | null
  rec_un_mission?: string | null
}

export async function submitExpert1Attack(
  body: Expert1AttackRequest
): Promise<Expert1AttackResponse> {
  const res = await fetch(`${BASE_URL}/evaluate/expert1-attack`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(res.status === 502 || res.status === 503 ? `服务暂不可用: ${text}` : text)
  }
  return res.json()
}

export interface CouncilSubmitResponse {
  incident_id: string
  status: 'running'
  message: string
  poll_url: string
  result_url: string
}

export interface EvaluationStatusResponse {
  incident_id: string
  status: 'running' | 'complete' | 'failed' | 'unknown'
  elapsed_seconds: number | null
  error: string | null
  result_url: string | null
}

/** Fire-and-forget: POST returns immediately with incident_id. */
export async function submitCouncilEvaluation(
  body: CouncilEvaluateRequest
): Promise<CouncilSubmitResponse> {
  const res = await fetch(`${BASE_URL}/evaluate/council`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text)
  }
  return res.json()
}

/** Poll the background evaluation status. */
export async function getEvaluationStatus(
  incidentId: string
): Promise<EvaluationStatusResponse> {
  const res = await fetch(`${BASE_URL}/evaluations/${incidentId}/status`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

/**
 * Submit + poll until complete, then return the full report.
 * Calls onProgress(elapsed_seconds) every 5 s while running.
 * Throws if evaluation fails or exceeds maxWaitMs (default 15 min).
 */
export async function submitAndWait(
  body: CouncilEvaluateRequest,
  onProgress?: (elapsed: number) => void,
  maxWaitMs = 15 * 60 * 1000,
): Promise<CouncilReportResponse> {
  const submit = await submitCouncilEvaluation(body)
  const incidentId = submit.incident_id
  const deadline = Date.now() + maxWaitMs

  while (Date.now() < deadline) {
    await new Promise(r => setTimeout(r, 5000))
    const status = await getEvaluationStatus(incidentId)
    if (onProgress && status.elapsed_seconds != null) {
      onProgress(status.elapsed_seconds)
    }
    if (status.status === 'complete') {
      return getEvaluationByIncident(incidentId)
    }
    if (status.status === 'failed') {
      throw new Error(status.error ?? 'Evaluation failed on the server')
    }
  }
  // Deadline exceeded — try /evaluations/latest as fallback
  try {
    return await fetch(
      `${BASE_URL}/evaluations/latest?agent_id=${encodeURIComponent(body.agent_id)}`
    ).then(r => r.json())
  } catch {
    throw new Error(`Evaluation timed out after ${maxWaitMs / 60000} minutes`)
  }
}

export async function listEvaluations(limit = 20, offset = 0): Promise<EvaluationListItem[]> {
  const res = await fetch(`${BASE_URL}/evaluations?limit=${limit}&offset=${offset}`)
  if (!res.ok) throw new Error(await res.text())
  const data = await res.json()
  return data.items ?? []
}

export async function getEvaluationByIncident(incidentId: string): Promise<CouncilReportResponse> {
  const res = await fetch(`${BASE_URL}/evaluations/${incidentId}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export interface RepoAnalyzeRequest {
  source?: string
  text?: string
  backend?: 'claude' | 'vllm'
  vllm_base_url?: string
  vllm_model?: string
  github_token?: string
}

export interface RepoAnalyzeResponse {
  system_name: string
  agent_id: string
  system_description: string
  capabilities: string
  data_sources: string
  human_oversight: string
  category: string
  deploy_zone: string
  source: string
}

export async function downloadEvaluationPdf(incidentId: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/evaluations/${incidentId}/pdf`)
  if (!res.ok) throw new Error(await res.text())
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `UNICC-Report-${incidentId}.pdf`
  a.click()
  URL.revokeObjectURL(url)
}

export async function analyzeRepo(
  body: RepoAnalyzeRequest
): Promise<RepoAnalyzeResponse> {
  const res = await fetch(`${BASE_URL}/analyze/repo`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text)
  }
  return res.json()
}

export interface AuditEvent {
  event_id: string
  incident_id: string | null
  stage: string
  status: string
  actor: string
  severity: string
  message: string
  created_at: string
  payload?: Record<string, unknown>
}

export interface AuditSpan {
  span_id: string
  span_name: string
  actor: string
  status: string
  started_at: string
  ended_at: string | null
  duration_ms: number | null
}

export interface EvaluationAudit {
  incident_id: string
  events: AuditEvent[]
  spans: AuditSpan[]
}

export async function getRecentAudit(limit = 30): Promise<AuditEvent[]> {
  const res = await fetch(`${BASE_URL}/audit/recent?limit=${limit}`)
  if (!res.ok) throw new Error(await res.text())
  const data = await res.json()
  return data.events ?? []
}

export interface KnowledgeStatExpert {
  key: string
  label: string
  description: string
  doc_count: number
  status: string
}

export interface KnowledgeStats {
  experts: KnowledgeStatExpert[]
  cases_indexed: number
}

export async function getKnowledgeStats(): Promise<KnowledgeStats> {
  const res = await fetch(`${BASE_URL}/knowledge/stats`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function getEvaluationAudit(incidentId: string): Promise<EvaluationAudit> {
  const res = await fetch(`${BASE_URL}/evaluations/${incidentId}/audit`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

/** 健康检查，用于判断后端是否可用 */
export async function healthCheck(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE_URL}/health`, { method: 'GET' })
    return res.ok
  } catch {
    return false
  }
}
