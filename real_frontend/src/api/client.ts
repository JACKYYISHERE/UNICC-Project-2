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

export async function submitCouncilEvaluation(
  body: CouncilEvaluateRequest
): Promise<CouncilReportResponse> {
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
  source: string
  backend?: 'claude' | 'vllm'
  vllm_base_url?: string
  vllm_model?: string
  github_token?: string
}

export interface RepoAnalyzeResponse {
  system_description: string
  source: string
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

/** 健康检查，用于判断后端是否可用 */
export async function healthCheck(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE_URL}/health`, { method: 'GET' })
    return res.ok
  } catch {
    return false
  }
}
