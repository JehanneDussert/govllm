// SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
// SPDX-License-Identifier: EUPL-1.2

// TODO: split & extract types

import axios from 'axios'

const GATEWAY_URL = import.meta.env.VITE_GATEWAY_URL ?? 'http://localhost:8001'
const OBSERVABILITY_URL = import.meta.env.VITE_OBSERVABILITY_URL ?? 'http://localhost:8002'
const EVALUATION_URL = import.meta.env.VITE_EVALUATION_URL ?? 'http://localhost:8003'

export const gateway = axios.create({ baseURL: GATEWAY_URL })
export const observability = axios.create({ baseURL: OBSERVABILITY_URL })
export const evaluation = axios.create({ baseURL: EVALUATION_URL })

// ── Types ─────────────────────────────────────────────────────

export interface Message {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatResponse {
  content: string
  model: string
  latency_ms: number
}
 
export interface MetricsResponse {
  models: ModelMetrics[]
  window: string
}
 
export interface ModelMetrics {
  model: string
  request_count: number
  error_rate: number
  latency: { p50_ms: number; p95_ms: number; p99_ms: number }
  avg_tokens_per_request: number
}
 
export interface TracesResponse {
  traces: TraceItem[]
  total: number
}
 
export interface TraceItem {
  trace_id: string
  model: string
  judge_model: string | null
  input_preview: string
  output_preview: string
  latency_ms: number
  eval_score: number | null
  timestamp: string
}
 
export interface BenchmarkResponse {
  models: ModelBenchmarkStats[]
  winner: string | null
  window: string
}
 
export interface ModelBenchmarkStats {
  model: string
  sample_size: number
  avg_latency_ms: number
  avg_eval_score: number | null
  error_rate: number
  avg_tokens: number
}
 
export interface JudgeCriterion {
  id: string
  label: string
  description: string
  enabled: boolean
  weight: number
}
 
export interface UseCase {
  id: string
  label: string
  description: string
  default_profile_id: string | null
  preferred_model: string | null
  expected_language: string | null
  min_score_threshold: number | null
  judge_system_prompt: string | null
}
 
export interface ArenaCriterionScore {
  criterion_id: string
  score: number
  flag: boolean
  reason: string | null
}
 
export interface ArenaJudge {
  judge_id: string
  model_name: string
  model_family: string
  assigned_criteria: string[]
  global_score: number | null
  latency_ms: number | null
  scores: ArenaCriterionScore[]
}
 
export interface ArenaRunRequest {
  prompt: string
  answer: string
  profile_id: string
  use_case_id?: string | null
  judge_models?: string[] | null
}
 
export interface ArenaRunResponse {
  session_id: string
  prompt: string
  profile_id: string
  sigma: number | null
  high_variance: boolean
  judges: ArenaJudge[]
  criteria_labels: Record<string, string>
}

export interface ArenaSession {
  session_id: string
  prompt: string
  profile_id: string
  use_case_id: string | null
  sigma: number | null
  high_variance: boolean
  user_vote: string | null
  created_at: string
  judges: ArenaJudge[]
}

export interface ArenaVoteRequest {
  session_id: string
  chosen_model: string
}
 
export interface ModelRoutingScore {
  model: string
  avg_score: number | null
  sample_size: number
  trend: 'up' | 'down' | 'stable' | null
  criteria_scores: Record<string, number | null>
  meets_threshold: boolean | null  // null = no threshold set or no data
}
 
export interface RoutingResult {
  recommended: string
  use_case_id: string
  profile_id: string | null
  min_threshold: number | null
  models: ModelRoutingScore[]
  active_criteria: { id: string; label: string }[]
}
 
export interface CriterionConfig {
  enabled: boolean
  weight: number
  calibration_notes?: string
}
 
export interface GovernanceProfile {
  id: string
  label: string
  description: string
  criteria_config: Record<string, CriterionConfig>
}
 
export interface JudgePanelMember {
  model: string
  persona_prompt: string
  assigned_criteria: string[]
}

export interface JudgePanel {
  profile_id: string
  judges: JudgePanelMember[]
}

export interface JudgeConfig {
  criteria: JudgeCriterion[]
  use_cases: UseCase[]
  profiles: GovernanceProfile[]
  panels: JudgePanel[]
  active_profile_id: string | null
  active_use_case_id: string | null
  judge_model: string
  arena_judge_models: string[]
  routing_strategy: string
  latency_threshold_ms: number | null
  score_threshold: number | null
  error_rate_threshold: number | null
  policy_rules: string
}
 
export interface CriterionScore {
  criterion_id: string
  score: number
  flag: boolean
  reason: string
}
 
export interface EvalResult {
  trace_id: string
  model: string
  use_case_id: string | null
  composite_score: number
  criteria_scores: CriterionScore[]
  evaluated_at: string
}
 
export interface MatrixCell {
  avg_score: number | null
  sample_size: number
  trend: 'up' | 'down' | 'stable' | null
  scores: number[]
}
 
export interface MatrixUseCase {
  label: string
  models: Record<string, MatrixCell>
}
 
export type MatrixResponse = Record<string, MatrixUseCase>

export interface VariancePoint {
  session_id: string
  created_at: string
  sigma: number
  profile_id: string
  prompt_preview: string
}

export interface VarianceHistory {
  points: VariancePoint[]
  profile_id: string | null
  window_days: number
}

export interface BiasMatrixCell {
  judge_family: string
  evaluated_model: string
  mean_score: number
  sample_size: number
  is_self_preference: boolean
}

export interface BiasMatrix {
  cells: BiasMatrixCell[]
  criterion_id: string | null
  profile_id: string | null
  judge_families: string[]
  evaluated_models: string[]
}

export interface IncoherenceScore {
  model_name: string
  model_family: string
  total_scores: number
  incoherent_count: number
  incoherence_rate: number
}

export interface IncoherenceReport {
  judges: IncoherenceScore[]
  score_threshold: number
  reason_min_len: number
}

export type LifecycleZone = 'test' | 'validation' | 'production' | 'quarantine'

export interface ModelLifecycleStatus {
  model: string
  zone: LifecycleZone
  score: number | null
  profile_id: string | null
  operator: string
  note: string | null
  since: string
}

export interface LifecycleTransition {
  id: string
  model: string
  zone: LifecycleZone
  score: number | null
  criterion_id: string | null
  profile_id: string | null
  operator: string
  note: string | null
  created_at: string
}

export interface LifecycleHistory {
  model: string | null
  transitions: LifecycleTransition[]
}

export interface SasResult {
  model: string
  avg_score: number | null
  sample_size: number
  threshold: number
  decision: string
  new_zone: LifecycleZone
  profile_id: string | null
}

export interface SasLmsysResult extends SasResult {
  prompts_tested: number
  criteria_breakdown: Record<string, number>
}

export interface GroundTruthCase {
  id: string
  criterion: string
  prompt: string
  response: string
  source: string | null
  expected_answers: Record<string, boolean>
  created_at: string
}

export interface GroundTruthCaseCreate {
  criterion: string
  prompt: string
  response: string
  source?: string | null
  expected_answers: Record<string, boolean>
}

export interface JudgeChecklistResult {
  judge_model: string
  judge_family: string
  answers: Record<string, boolean>
  score: number
  agreement: number
  reason: string | null
  latency_ms: number | null
}

export interface GroundTruthRunResult {
  case_id: string
  criterion: string
  expected_answers: Record<string, boolean>
  judges: JudgeChecklistResult[]
}

export interface ValidityEntry {
  judge_model: string
  judge_family: string
  criterion: string
  question_id: string
  agreement_rate: number
  sample_size: number
}

export interface ValidityReport {
  entries: ValidityEntry[]
  criteria: string[]
  judge_models: string[]
}

export interface IncoherenceItem {
  result_id: string
  case_id: string
  prompt_preview: string
  criterion: string
  judge_model: string
  judge_family: string
  answers: Record<string, boolean>
  expected_answers: Record<string, boolean>
  reason: string | null
  incoherence_validated: boolean | null
  question_order: string
}

export interface OrderSensitivityEntry {
  judge_model: string
  criterion: string
  flip_rate: number
  mean_delta_agreement: number
  n_cases: number
  flipped_case_ids: string[]
}


// ── API calls ─────────────────────────────────────────────────

export const api = {
  generateAnswer: (question: string, model: string) =>
    gateway.post<ChatResponse>('/chat', {
      messages: [{ role: 'user', content: question }],
      model,
      stream: false,
    }),

  metrics: (window = '1h') =>
    observability.get<MetricsResponse>(`/metrics?window=${window}`),

  traces: (limit = 200, model?: string) =>
    observability.get<TracesResponse>(`/traces?limit=${limit}${model ? `&model=${model}` : ''}`),

  abResults: () =>
    evaluation.get<BenchmarkResponse>('/benchmark/results'),

  health: () => Promise.all([
    gateway.get('/health').then(() => true).catch(() => false),
    observability.get('/health').then(() => true).catch(() => false),
    evaluation.get('/health').then(() => true).catch(() => false),
  ]),

  // Judge config
  getJudgeConfig: () =>
    evaluation.get<JudgeConfig>('/config/judge'),

  saveJudgeConfig: (config: JudgeConfig) =>
    evaluation.put<JudgeConfig>('/config/judge', config),

  // Matrix
  getMatrix: () =>
    evaluation.get<MatrixResponse>('/matrix'),

  // Arena
  arenaRun: (req: ArenaRunRequest) =>
    evaluation.post<ArenaRunResponse>('/arena/run', req),

  arenaRunStream: async (
    req: ArenaRunRequest,
    onEvent: (event: Record<string, unknown>) => void,
    signal?: AbortSignal,
  ): Promise<void> => {
    const url = (import.meta.env.VITE_EVALUATION_URL ?? 'http://localhost:8003') + '/arena/run/stream'
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
      signal,
    })
    if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`)
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try { onEvent(JSON.parse(line.slice(6))) } catch {}
        }
      }
    }
  },

  arenaVote: (req: ArenaVoteRequest) =>
    evaluation.post('/arena/vote', req),
  arenaSessions: (profileId?: string, highVariance?: boolean) => {
    const params = new URLSearchParams()
    if (profileId) params.set('profile_id', profileId)
    if (highVariance) params.set('high_variance', 'true')
    const qs = params.toString()
    return evaluation.get<ArenaSession[]>('/arena/sessions' + (qs ? `?${qs}` : ''))
  },
  arenaVariance: (profileId?: string, windowDays?: number) => {
    const params = new URLSearchParams()
    if (profileId) params.set('profile_id', profileId)
    if (windowDays) params.set('window_days', String(windowDays))
    const qs = params.toString()
    return evaluation.get<VarianceHistory>('/arena/variance' + (qs ? `?${qs}` : ''))
  },
  arenaBiasMatrix: (profileId?: string, criterionId?: string) => {
    const params = new URLSearchParams()
    if (profileId) params.set('profile_id', profileId)
    if (criterionId) params.set('criterion_id', criterionId)
    const qs = params.toString()
    return evaluation.get<BiasMatrix>('/arena/bias-matrix' + (qs ? `?${qs}` : ''))
  },
  arenaIncoherence: (profileId?: string) => {
    const qs = profileId ? `?profile_id=${profileId}` : ''
    return evaluation.get<IncoherenceReport>('/arena/incoherence' + qs)
  },

  // Available models
  availableModels: () =>
    evaluation.get<{ models: string[] }>('/config/models/available'),

  // Lifecycle
  lifecycleStatus: () =>
    evaluation.get<ModelLifecycleStatus[]>('/lifecycle/status'),
  lifecycleHistory: (model?: string) =>
    evaluation.get<LifecycleHistory>('/lifecycle/history' + (model ? `?model=${encodeURIComponent(model)}` : '')),
  lifecycleValidate: (model: string, note?: string) =>
    evaluation.post<LifecycleTransition>(`/lifecycle/validate/${encodeURIComponent(model)}` + (note ? `?note=${encodeURIComponent(note)}` : '')),
  lifecycleQuarantine: (model: string, note?: string) =>
    evaluation.post<LifecycleTransition>(`/lifecycle/quarantine/${encodeURIComponent(model)}` + (note ? `?note=${encodeURIComponent(note)}` : '')),
  lifecycleSas: (model: string, profileId?: string) =>
    evaluation.post<SasResult>('/lifecycle/sas', { model, profile_id: profileId ?? null }),
  lifecycleSasLmsys: (model: string, profileId?: string, nPrompts = 10) =>
    evaluation.post<SasLmsysResult>(`/lifecycle/sas/lmsys?n_prompts=${nPrompts}`, { model, profile_id: profileId ?? null }),

  // Ground truth corpus
  groundtruthCorpus: (criterion?: string) =>
    evaluation.get<GroundTruthCase[]>('/groundtruth/corpus' + (criterion ? `?criterion=${encodeURIComponent(criterion)}` : '')),
  addGroundTruthCase: (req: GroundTruthCaseCreate) =>
    evaluation.post<GroundTruthCase>('/groundtruth/corpus', req),
  runGroundtruth: (caseId: string) =>
    evaluation.post<GroundTruthRunResult>(`/groundtruth/run/${encodeURIComponent(caseId)}`),
  groundtruthBestJudges: () =>
    evaluation.get<Record<string, string>>('/groundtruth/validity/best-judges'),
  groundtruthValidity: () =>
    evaluation.get<ValidityReport>('/groundtruth/validity'),
  groundtruthOrderSensitivity: () =>
    evaluation.get<OrderSensitivityEntry[]>('/groundtruth/order-sensitivity'),
  groundtruthIncoherence: () =>
    evaluation.get<IncoherenceItem[]>('/groundtruth/incoherence'),
  validateIncoherence: (resultId: string, validated: boolean | null) =>
    evaluation.patch<{ result_id: string; incoherence_validated: boolean | null }>(
      `/groundtruth/results/${encodeURIComponent(resultId)}/validate`,
      { validated },
    ),

  // Routing
  getRouting: () =>
    evaluation.get<RoutingResult>('/matrix/routing'),

  // Profile activation
  activateProfile: (profileId: string) =>
    evaluation.post<JudgeConfig>(`/config/judge/profile/${profileId}`),

  // Use case activation (auto-applies default profile)
  activateUseCase: (useCaseId: string) =>
    evaluation.post<JudgeConfig>(`/config/judge/use-case/${useCaseId}`),

  // Eval scoring
  triggerEval: (payload: { trace_id: string; model: string; question: string; answer: string }) =>
    evaluation.post('/eval/score', payload),

  getEvalResult: (traceId: string) =>
    evaluation.get<EvalResult | null>(`/eval/result/${traceId}`),
}