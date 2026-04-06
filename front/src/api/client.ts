// SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
// SPDX-License-Identifier: EUPL-1.2
import axios from 'axios'

const GATEWAY_URL = import.meta.env.VITE_GATEWAY_URL ?? 'http://localhost:8001'
const OBSERVABILITY_URL = import.meta.env.VITE_OBSERVABILITY_URL ?? 'http://localhost:8002'
const EVALUATION_URL = import.meta.env.VITE_EVALUATION_URL ?? 'http://localhost:8003'

export const gateway = axios.create({ baseURL: GATEWAY_URL })
export const observability = axios.create({ baseURL: OBSERVABILITY_URL })
export const evaluation = axios.create({ baseURL: EVALUATION_URL })

export const BENCHMARK_MODELS = import.meta.env.VITE_BENCHMARK_MODELS
  ? JSON.parse(import.meta.env.VITE_BENCHMARK_MODELS)
  : ['ollama/qwen2.5:1.5b', 'ollama/llama3.2:3b']

// Types
export interface Message {
  role: 'user' | 'assistant'
  content: string
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
}

export interface ModelRoutingScore {
  model: string
  avg_score: number | null
  sample_size: number
  trend: 'up' | 'down' | 'stable' | null
  criteria_scores: Record<string, number | null>
}

export interface RoutingResult {
  recommended: string
  use_case_id: string
  profile_id: string | null
  models: ModelRoutingScore[]
  active_criteria: { id: string; label: string }[]
}

export interface GovernanceProfile {
  id: string
  label: string
  description: string
  criteria_weights: Record<string, number>
  criteria_enabled: string[]
}

export interface JudgeConfig {
  criteria: JudgeCriterion[]
  use_cases: UseCase[]
  profiles: GovernanceProfile[]
  active_profile_id: string | null
  active_use_case_id: string | null
  judge_model: string
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

// API calls

export const api = {
  metrics: (window = '1h') => observability.get<MetricsResponse>(`/metrics?window=${window}`),

  traces: (limit = 50, model?: string) =>
    observability.get<TracesResponse>(`/traces?limit=${limit}${model ? `&model=${model}` : ''}`),

  benchmarkResults: (limit = 50) => evaluation.get<BenchmarkResponse>('/benchmark/results'),

  health: () =>
    Promise.all([
      gateway
        .get('/health')
        .then(() => true)
        .catch(() => false),
      observability
        .get('/health')
        .then(() => true)
        .catch(() => false),
      evaluation
        .get('/health')
        .then(() => true)
        .catch(() => false),
    ]),

  // Judge config
  getJudgeConfig: () => evaluation.get<JudgeConfig>('/config/judge'),

  saveJudgeConfig: (config: JudgeConfig) => evaluation.put<JudgeConfig>('/config/judge', config),

  // Matrix
  getMatrix: () => evaluation.get<MatrixResponse>('/matrix'),

  // Routing
  getRouting: () => evaluation.get<RoutingResult>('/matrix/routing'),

  // Profile activation
  activateProfile: (profileId: string) =>
    evaluation.post<JudgeConfig>(`/config/judge/profile/${profileId}`),

  // Eval scoring
  triggerEval: (payload: { trace_id: string; model: string; question: string; answer: string }) =>
    evaluation.post('/eval/score', payload),

  getEvalResult: (traceId: string) => evaluation.get<EvalResult | null>(`/eval/result/${traceId}`),
}
