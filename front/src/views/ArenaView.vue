<!--
  SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
  SPDX-License-Identifier: EUPL-1.2
-->

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, HeatmapChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, VisualMapComponent, DataZoomComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { useJudgeStore } from '@/stores/judge'
import { api } from '@/api/client'
import type {
  ArenaCriterionScore, IncoherenceScore, VarianceHistory, BiasMatrix,
  GroundTruthCase, GroundTruthRunResult, ValidityReport,
} from '@/api/client'
import { modelShortName } from '@/utils/model'

use([CanvasRenderer, LineChart, HeatmapChart, GridComponent, TooltipComponent, VisualMapComponent, DataZoomComponent])

interface JudgeShell {
  judge_id?: string
  model_name: string
  model_family: string
  assigned_criteria: string[]
  global_score?: number | null
  latency_ms?: number | null
  scores: ArenaCriterionScore[]
  done: boolean
}

type ArenaTab = 'run' | 'variance' | 'bias' | 'corpus'
type InputMode = 'manual' | 'auto'
const activeTab = ref<ArenaTab>('run')
const inputMode = ref<InputMode>('manual')

const judgeStore = useJudgeStore()
const prompt = ref('')
const answer = ref('')
const question = ref('')
const generatorModel = ref('')
const generating = ref(false)
const availableModels = ref<string[]>([])
const judgeShells = ref<JudgeShell[]>([])
const sigma = ref<number | null>(null)
const sessionId = ref<string | null>(null)
const criteriaLabels = ref<Record<string, string>>({})
const loading = ref(false)
const sessionDone = ref(false)
const error = ref<string | null>(null)
const votedFor = ref<string | null>(null)
const incoherenceRates = ref<Record<string, IncoherenceScore>>({})
const varianceData = ref<VarianceHistory | null>(null)
const biasData = ref<BiasMatrix | null>(null)
const varianceLoading = ref(false)
const biasLoading = ref(false)

// ── Corpus (ground truth) state ──────────────────────────────────────────────
const corpusCases = ref<GroundTruthCase[]>([])
const corpusCriterion = ref<string>('')
const selectedCaseId = ref<string>('')
const corpusLoading = ref(false)
const corpusRunning = ref(false)
const corpusResult = ref<GroundTruthRunResult | null>(null)
const validityData = ref<ValidityReport | null>(null)
const validityLoading = ref(false)
const showValidity = ref(false)

const SUPPORTED_CRITERIA = ['transparency', 'data_privacy', 'non_manipulation', 'prompt_injection', 'human_oversight']

const filteredCases = computed(() =>
  corpusCriterion.value
    ? corpusCases.value.filter(c => c.criterion === corpusCriterion.value)
    : corpusCases.value
)
const selectedCase = computed(() =>
  corpusCases.value.find(c => c.id === selectedCaseId.value) ?? null
)

let streamAbortController: AbortController | null = null

async function selectProfile(id: string) {
  if (!judgeStore.config || judgeStore.config.active_profile_id === id) return
  judgeStore.config.active_profile_id = id
  try { await api.activateProfile(id) } catch {}
}

async function selectUseCase(id: string) {
  if (!judgeStore.config || judgeStore.config.active_use_case_id === id) return
  const uc = judgeStore.config.use_cases.find(u => u.id === id)
  judgeStore.config.active_use_case_id = id
  if (uc?.default_profile_id) judgeStore.config.active_profile_id = uc.default_profile_id
  try { await api.activateUseCase(id) } catch {}
}

const JUDGE_COLORS: Record<string, string> = {
  qwen:     '#185fa5',
  gemma:    '#1d9e75',
  llama:    '#888780',
  deepseek: '#ba7517',
  unknown:  '#888780',
}

const DOMAIN_LABELS: Record<string, string> = {
  qwen:     'compliance',
  gemma:    'ethics',
  llama:    'quality',
  deepseek: 'security',
  unknown:  'general',
}

const SIGMA_LEVELS = [
  { max: 0.03, label: 'consensus',             color: '#1d9e75' },
  { max: 0.08, label: 'moderate disagreement', color: '#ba7517' },
  { max: 1,    label: 'human review needed',   color: '#e24b4a' },
]

function judgeColor(family: string) {
  return JUDGE_COLORS[family] ?? JUDGE_COLORS.unknown
}

function domainLabel(family: string) {
  return DOMAIN_LABELS[family] ?? 'general'
}

function sigmaLevel(s: number | null) {
  if (s === null) return SIGMA_LEVELS[0]
  return SIGMA_LEVELS.find(l => s <= l.max) ?? SIGMA_LEVELS[2]
}

function sigmaWidth(s: number | null) {
  if (s === null) return 0
  return Math.min(Math.round((s / 0.15) * 100), 100)
}

function ringDashOffset(score: number | null | undefined) {
  const circ = 2 * Math.PI * 26
  return circ - (score ?? 0) * circ
}

function labelFor(id: string) {
  return criteriaLabels.value[id]
    ?? judgeStore.config?.criteria.find(c => c.id === id)?.label
    ?? id
}

function isWinner(shell: JudgeShell) {
  const done = judgeShells.value.filter(s => s.done)
  if (!done.length) return false
  const max = Math.max(...done.map(s => s.global_score ?? -1))
  return (shell.global_score ?? -1) === max && max > 0
}

function rank(shell: JudgeShell) {
  const done = judgeShells.value.filter(s => s.done)
  const sorted = [...done].sort((a, b) => (b.global_score ?? -1) - (a.global_score ?? -1))
  const idx = sorted.findIndex(s => s.model_name === shell.model_name)
  return idx === -1 ? 0 : idx + 1
}

function rankLabel(r: number) {
  if (r === 1) return '👑'
  if (r === 2) return '2nd'
  if (r === 3) return '3rd'
  return `${r}th`
}

async function generateAnswer() {
  if (!question.value.trim() || !generatorModel.value || !judgeStore.config) return
  generating.value = true
  error.value = null
  answer.value = ''
  try {
    const res = await api.generateAnswer(question.value, generatorModel.value)
    prompt.value = question.value
    answer.value = res.data.content
  } catch {
    error.value = 'Generation failed — is the gateway running?'
  } finally {
    generating.value = false
  }
}

async function runArena() {
  if (!prompt.value.trim() || !answer.value.trim() || !judgeStore.config) return
  streamAbortController?.abort()
  streamAbortController = new AbortController()

  // In auto mode, exclude the generator from the judge panel to prevent auto-evaluation bias
  const judgeModels = inputMode.value === 'auto' && generatorModel.value
    ? availableModels.value.filter(m => m !== generatorModel.value)
    : undefined

  loading.value = true
  error.value = null
  judgeShells.value = []
  sigma.value = null
  sessionId.value = null
  criteriaLabels.value = {}
  votedFor.value = null
  sessionDone.value = false

  try {
    await api.arenaRunStream(
      {
        prompt: prompt.value,
        answer: answer.value,
        profile_id: judgeStore.config.active_profile_id ?? 'quality_baseline',
        use_case_id: judgeStore.config.active_use_case_id ?? 'general',
        judge_models: judgeModels ?? null,
      },
      (event) => {
        if (event.type === 'init') {
          judgeShells.value = (event.judges as JudgeShell[]).map(j => ({
            model_name: j.model_name,
            model_family: j.model_family,
            assigned_criteria: j.assigned_criteria,
            scores: [],
            done: false,
          }))
        } else if (event.type === 'judge_done') {
          const j = event.judge as JudgeShell
          const idx = judgeShells.value.findIndex(s => s.model_name === j.model_name)
          if (idx !== -1) {
            judgeShells.value[idx] = { ...j, done: true }
          }
        } else if (event.type === 'complete') {
          sigma.value = event.sigma as number | null
          sessionId.value = event.session_id as string
          criteriaLabels.value = event.criteria_labels as Record<string, string>
          sessionDone.value = true
          loading.value = false
        } else if (event.type === 'error') {
          error.value = (event.detail as string) ?? 'Arena error'
          loading.value = false
        }
      },
      streamAbortController.signal,
    )
  } catch (e: unknown) {
    if ((e as { name?: string })?.name !== 'AbortError') {
      error.value = 'Arena run failed — is evaluation running?'
    }
    loading.value = false
  }
}

async function vote(modelName: string) {
  if (!sessionId.value || votedFor.value) return
  votedFor.value = modelName
  try {
    await api.arenaVote({ session_id: sessionId.value, chosen_model: modelName })
  } catch {}
}

async function loadVariance() {
  varianceLoading.value = true
  try {
    const res = await api.arenaVariance(judgeStore.config?.active_profile_id ?? undefined)
    varianceData.value = res.data
  } catch {} finally { varianceLoading.value = false }
}

async function loadBias() {
  biasLoading.value = true
  try {
    const res = await api.arenaBiasMatrix(judgeStore.config?.active_profile_id ?? undefined)
    biasData.value = res.data
  } catch {} finally { biasLoading.value = false }
}

async function loadCorpus() {
  corpusLoading.value = true
  try {
    const res = await api.groundtruthCorpus()
    corpusCases.value = res.data
    if (res.data.length && !corpusCriterion.value) {
      corpusCriterion.value = res.data[0].criterion
      selectedCaseId.value = res.data[0].id
    }
  } catch {} finally { corpusLoading.value = false }
}

async function runCorpus() {
  if (!selectedCaseId.value) return
  corpusRunning.value = true
  corpusResult.value = null
  try {
    const res = await api.runGroundtruth(selectedCaseId.value)
    corpusResult.value = res.data
  } catch {} finally { corpusRunning.value = false }
}

async function loadValidity() {
  validityLoading.value = true
  try {
    const res = await api.groundtruthValidity()
    validityData.value = res.data
    showValidity.value = true
  } catch {} finally { validityLoading.value = false }
}

watch(selectedCaseId, () => { corpusResult.value = null })
watch(corpusCriterion, () => {
  const first = filteredCases.value[0]
  if (first) selectedCaseId.value = first.id
  corpusResult.value = null
})

async function switchTab(tab: ArenaTab) {
  activeTab.value = tab
  if (tab === 'variance' && !varianceData.value) await loadVariance()
  if (tab === 'bias' && !biasData.value) await loadBias()
  if (tab === 'corpus' && !corpusCases.value.length) await loadCorpus()
}

const varianceOption = computed(() => {
  const points = varianceData.value?.points ?? []
  if (!points.length) return {}
  return {
    backgroundColor: 'transparent',
    grid: { left: 56, right: 24, top: 20, bottom: 40 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1c2128', borderColor: '#30363d',
      textStyle: { color: '#c9d1d9', fontSize: 11 },
      formatter: (params: any[]) => {
        const p = params[0]
        const date = new Date(p.value[0]).toLocaleDateString()
        return `${date}<br/>σ = ${(p.value[1] as number).toFixed(4)}`
      },
    },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: '#30363d' } },
      axisLabel: { color: '#7d8590', fontSize: 10 },
    },
    yAxis: {
      type: 'value', name: 'σ inter-judge', min: 0,
      nameTextStyle: { color: '#7d8590', fontSize: 10 },
      axisLine: { lineStyle: { color: '#30363d' } },
      axisLabel: { color: '#7d8590', fontSize: 10 },
      splitLine: { lineStyle: { color: '#21262d' } },
    },
    series: [{
      type: 'line',
      data: points.map(p => [p.created_at, p.sigma]),
      lineStyle: { color: '#00e5ff', width: 2 },
      itemStyle: { color: '#00e5ff' },
      areaStyle: { color: 'rgba(0,229,255,0.07)' },
      smooth: true, symbolSize: 5,
    }],
  }
})

const biasOption = computed(() => {
  if (!biasData.value || !biasData.value.cells.length) return {}
  const { cells, judge_families, evaluated_models } = biasData.value
  const shortModels = evaluated_models.map(m => modelShortName(m))
  const data = cells.map(c => [
    evaluated_models.indexOf(c.evaluated_model),
    judge_families.indexOf(c.judge_family),
    c.mean_score,
    c.sample_size,
    c.is_self_preference,
  ])
  return {
    backgroundColor: 'transparent',
    grid: { left: 80, right: 110, top: 20, bottom: 50 },
    tooltip: {
      position: 'top',
      backgroundColor: '#1c2128', borderColor: '#30363d',
      textStyle: { color: '#c9d1d9', fontSize: 11 },
      formatter: (p: any) => {
        const d = p.data as number[]
        return `<b>${judge_families[d[1]]}</b> → ${shortModels[d[0]]}<br/>` +
          `Score: ${d[2].toFixed(3)} (n=${d[3]})` +
          (d[4] ? '<br/><span style="color:#f0883e">⚑ self-preference</span>' : '')
      },
    },
    xAxis: {
      type: 'category', data: shortModels,
      axisLabel: { color: '#7d8590', fontSize: 9, rotate: 15 },
      splitArea: { show: true, areaStyle: { color: ['#0d1117', '#161b22'] } },
    },
    yAxis: {
      type: 'category', data: judge_families,
      axisLabel: { color: '#7d8590', fontSize: 10 },
      splitArea: { show: true, areaStyle: { color: ['#0d1117', '#161b22'] } },
    },
    visualMap: {
      min: 0, max: 1, calculable: true, orient: 'vertical',
      right: 8, top: 'middle',
      inRange: { color: ['#161b22', '#0d5c6e', '#00e5ff'] },
      textStyle: { color: '#7d8590', fontSize: 9 },
    },
    series: [{
      type: 'heatmap', data,
      label: {
        show: true,
        formatter: (p: any) => (p.data as number[])[2].toFixed(2),
        fontSize: 10, color: '#c9d1d9',
      },
    }],
  }
})

onMounted(async () => {
  await judgeStore.fetchConfig()
  api.arenaIncoherence().then(res => {
    incoherenceRates.value = Object.fromEntries(res.data.judges.map(j => [j.model_name, j]))
  }).catch(() => {})
  api.availableModels().then(res => {
    availableModels.value = res.data.models
    if (res.data.models.length && !generatorModel.value) generatorModel.value = res.data.models[0] ?? ''
  }).catch(() => {})
})
onUnmounted(() => streamAbortController?.abort())
</script>

<template>
  <div class="arena-view">

    <div class="page-header">
      <div>
        <h1 class="page-title">Judge Arena</h1>
        <p class="page-sub">Each judge specialises on a regulatory domain — compare how they score the same response</p>
      </div>
      <div class="header-selectors" v-if="judgeStore.config">
        <div class="selector-group">
          <label class="selector-label">Profile</label>
          <select
            class="selector"
            :value="judgeStore.config.active_profile_id ?? ''"
            :disabled="loading"
            @change="selectProfile(($event.target as HTMLSelectElement).value)"
          >
            <option v-for="p in judgeStore.config.profiles" :key="p.id" :value="p.id">
              {{ p.label }}
            </option>
          </select>
        </div>
        <div class="selector-group">
          <label class="selector-label">Use case</label>
          <select
            class="selector"
            :value="judgeStore.config.active_use_case_id ?? ''"
            :disabled="loading"
            @change="selectUseCase(($event.target as HTMLSelectElement).value)"
          >
            <option v-for="uc in judgeStore.config.use_cases" :key="uc.id" :value="uc.id">
              {{ uc.label }}
            </option>
          </select>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="arena-tabs">
      <button class="arena-tab" :class="{ active: activeTab === 'run' }" @click="switchTab('run')">Run</button>
      <button class="arena-tab" :class="{ active: activeTab === 'variance' }" @click="switchTab('variance')">Variance explorer</button>
      <button class="arena-tab" :class="{ active: activeTab === 'bias' }" @click="switchTab('bias')">Bias matrix</button>
      <button class="arena-tab" :class="{ active: activeTab === 'corpus' }" @click="switchTab('corpus')">Corpus validation</button>
    </div>

    <!-- ── Tab: Run ──────────────────────────────────────────── -->
    <template v-if="activeTab === 'run'">

    <!-- Prompt input -->
    <div class="prompt-box">

      <!-- Mode toggle -->
      <div class="mode-toggle">
        <button class="mode-btn" :class="{ active: inputMode === 'manual' }" @click="inputMode = 'manual'" :disabled="loading">Manual</button>
        <button class="mode-btn" :class="{ active: inputMode === 'auto' }" @click="inputMode = 'auto'" :disabled="loading">Auto-generate</button>
      </div>

      <!-- Manual mode -->
      <template v-if="inputMode === 'manual'">
        <textarea v-model="prompt" class="prompt-input" placeholder="Question / prompt…" rows="2" :disabled="loading" />
        <textarea v-model="answer" class="prompt-input" placeholder="Answer to evaluate across all judges…" rows="3" :disabled="loading" />
      </template>

      <!-- Auto-generate mode -->
      <template v-else>
        <textarea v-model="question" class="prompt-input" placeholder="Enter a question — a model will generate the answer…" rows="2" :disabled="loading || generating" />
        <div class="auto-controls">
          <select v-model="generatorModel" class="auto-model-select" :disabled="loading || generating">
            <option v-for="m in availableModels" :key="m" :value="m">{{ modelShortName(m) }}</option>
          </select>
          <button
            class="generate-btn"
            @click="generateAnswer"
            :disabled="loading || generating || !question.trim() || !generatorModel"
          >
            <span v-if="generating" class="loading-dots"><span/><span/><span/></span>
            <span v-else>⚡ Generate</span>
          </button>
        </div>
        <div v-if="generatorModel" class="auto-hint">
          <span class="auto-hint-model">{{ modelShortName(generatorModel) }}</span> generates the answer and is automatically excluded from the judge panel for this run.
        </div>
        <textarea
          v-model="answer"
          class="prompt-input"
          :class="{ 'answer-generated': answer && !generating }"
          placeholder="Generated answer will appear here — you can edit before submitting…"
          rows="4"
          :disabled="loading"
        />
      </template>

      <div class="prompt-footer">
        <span class="prompt-hint">
          <template v-if="inputMode === 'auto' && generatorModel && answer">
            Judges: all models except {{ modelShortName(generatorModel) }}
          </template>
          <template v-else>All judges will evaluate simultaneously</template>
        </span>
        <button class="run-btn" @click="runArena" :disabled="loading || !prompt.trim() || !answer.trim()">
          <span v-if="loading" class="loading-dots"><span/><span/><span/></span>
          <span v-else>⚔ Run arena</span>
        </button>
      </div>
    </div>

    <div v-if="error" class="error-state">{{ error }}</div>

    <!-- Judge cards — appear immediately after init event -->
    <template v-if="judgeShells.length > 0">

      <div class="cards-grid">
        <div
          v-for="(shell, i) in judgeShells"
          :key="shell.model_name"
          class="judge-card"
          :class="{ winner: shell.done && isWinner(shell), loading: !shell.done }"
          :style="{ animationDelay: i * 0.08 + 's' }"
        >
          <!-- Header -->
          <div class="card-header">
            <div class="card-identity">
              <div class="avatar" :style="{ background: judgeColor(shell.model_family) + '22', color: judgeColor(shell.model_family) }">
                {{ shell.model_family[0]?.toUpperCase() }}
              </div>
              <div>
                <div class="card-name">
                  {{ modelShortName(shell.model_name) }}
                  <span v-if="shell.done && isWinner(shell)" class="crown">👑</span>
                </div>
                <div class="card-domain">{{ domainLabel(shell.model_family).toUpperCase() }}</div>
              </div>
            </div>
            <div v-if="shell.done" class="card-rank" :class="{ 'rank-first': rank(shell) === 1 }">
              {{ rankLabel(rank(shell)) }}
            </div>
            <div v-else class="card-rank card-rank-loading">…</div>
          </div>

          <!-- Ring -->
          <div class="ring-wrapper">
            <svg width="72" height="72" viewBox="0 0 72 72">
              <circle cx="36" cy="36" r="26" fill="none" stroke="var(--bg-3)" stroke-width="5"/>
              <!-- Score arc -->
              <circle
                cx="36" cy="36" r="26" fill="none"
                :stroke="judgeColor(shell.model_family)"
                stroke-width="5"
                stroke-linecap="round"
                :stroke-dasharray="163.4"
                :stroke-dashoffset="ringDashOffset(shell.global_score)"
                transform="rotate(-90 36 36)"
                class="ring-arc"
              />
              <text x="36" y="41" text-anchor="middle" font-size="14" font-weight="500" :fill="judgeColor(shell.model_family)">
                <template v-if="shell.done">
                  {{ shell.global_score != null ? (shell.global_score * 100).toFixed(0) + '%' : '—' }}
                </template>
                <template v-else>…</template>
              </text>
            </svg>
          </div>

          <!-- Criteria dots -->
          <div class="criteria-dots">
            <!-- Loading placeholders -->
            <template v-if="!shell.done">
              <div
                v-for="cid in shell.assigned_criteria.slice(0, 4)"
                :key="cid"
                class="dot-row"
              >
                <span class="dot-label">{{ labelFor(cid) }}</span>
                <div class="dots">
                  <div
                    v-for="n in 5" :key="n"
                    class="dot dot-placeholder"
                    :style="{ background: judgeColor(shell.model_family) + '44', animationDelay: (n - 1) * 0.12 + 's' }"
                  />
                </div>
              </div>
            </template>
            <!-- Real scores with hover tooltip -->
            <template v-else>
              <div
                v-for="score in shell.scores.slice(0, 4)"
                :key="score.criterion_id"
                class="dot-row"
              >
                <span class="dot-label">{{ labelFor(score.criterion_id) }}</span>
                <div class="dots">
                  <div
                    v-for="n in 5" :key="n"
                    class="dot"
                    :style="{ background: n <= Math.round(score.score * 5) ? judgeColor(shell.model_family) : judgeColor(shell.model_family) + '33' }"
                  />
                </div>
                <div class="score-tooltip">
                  <div class="tooltip-score" :class="{ flagged: score.flag }">
                    {{ (score.score * 100).toFixed(0) }}%
                    <span v-if="score.flag" class="tooltip-flag">⚑</span>
                  </div>
                  <div v-if="score.reason" class="tooltip-reason">{{ score.reason }}</div>
                </div>
              </div>
            </template>
          </div>

          <!-- Incoherence badge -->
          <div
            v-if="shell.done && (incoherenceRates[shell.model_name]?.incoherence_rate ?? 0) > 0"
            class="incoherence-badge"
            :title="`${incoherenceRates[shell.model_name]?.incoherent_count ?? 0} / ${incoherenceRates[shell.model_name]?.total_scores ?? 0} incoherent scores`"
          >
            ⚡ {{ ((incoherenceRates[shell.model_name]?.incoherence_rate ?? 0) * 100).toFixed(0) }}% incoh.
          </div>

          <!-- Vote -->
          <div class="vote-btn-container">
            <button
              class="vote-btn"
              :class="{
                'voted': votedFor === shell.model_name,
                'voted-other': votedFor && votedFor !== shell.model_name,
                'winner-btn': shell.done && isWinner(shell),
              }"
              @click="vote(shell.model_name)"
              :disabled="!sessionDone || !!votedFor"
              :style="shell.done && isWinner(shell) ? { borderColor: judgeColor(shell.model_family) + '66', color: judgeColor(shell.model_family) } : {}"
            >
              {{ votedFor === shell.model_name ? '✓ voted' : 'vote' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Sigma bar — only after all judges done -->
      <div v-if="sessionDone" class="sigma-section">
        <div class="sigma-top">
          <div>
            <div class="sigma-label">σ INTER-JUDGE</div>
            <div class="sigma-value" :style="{ color: sigmaLevel(sigma)?.color }">
              {{ sigma?.toFixed(3) ?? '—' }}
            </div>
          </div>
          <div class="sigma-right">
            <div class="sigma-bar-track">
              <div
                class="sigma-bar-fill"
                :style="{ width: sigmaWidth(sigma) + '%', background: sigmaLevel(sigma)?.color }"
              />
            </div>
            <div class="sigma-scale">
              <span style="color:#1d9e75">consensus</span>
              <span>moderate disagreement</span>
              <span style="color:#e24b4a">⚠ human review needed</span>
            </div>
          </div>
        </div>
        <div class="sigma-explanation" v-if="sigma !== null">
          <template v-if="sigma <= 0.03">
            All judges agree — this response is evaluated consistently across regulatory criteria.
          </template>
          <template v-else-if="sigma <= 0.08">
            The judges show moderate disagreement — this is a regulatory grey zone worth human review.
          </template>
          <template v-else>
            Strong inter-judge disagreement detected — this response raises unresolved regulatory questions requiring human arbitration.
          </template>
        </div>
      </div>

    </template>

    </template> <!-- end tab: run -->

    <!-- ── Tab: Variance explorer ───────────────────────────── -->
    <template v-if="activeTab === 'variance'">
      <div class="chart-section">
        <div class="chart-header">
          <div class="chart-title">σ INTER-JUDGE OVER TIME</div>
          <div class="chart-desc">Mean per-criterion variance across all judges per session. Low σ = consensus. High σ = regulatory grey zone requiring human review.</div>
        </div>
        <div v-if="varianceLoading" class="chart-loading"><div class="loading-dots"><span/><span/><span/></div></div>
        <div v-else-if="!varianceData || !varianceData.points.length" class="chart-empty">No sessions recorded yet — run the Arena to generate data.</div>
        <VChart v-else class="echart" :option="varianceOption" autoresize />
      </div>
    </template>

    <!-- ── Tab: Bias matrix ──────────────────────────────────── -->
    <template v-if="activeTab === 'bias'">
      <div class="chart-section">
        <div class="chart-header">
          <div class="chart-title">BIAS MATRIX — judge family × evaluated model</div>
          <div class="chart-desc">Mean score given by each judge family to each evaluated model. Diagonal cells (same family) indicate self-preference (SPR). Significant off-diagonal asymmetry = epistemic discrimination.</div>
        </div>
        <div v-if="biasLoading" class="chart-loading"><div class="loading-dots"><span/><span/><span/></div></div>
        <div v-else-if="!biasData || !biasData.cells.length" class="chart-empty">No cross-judge data yet — run the Arena with multiple judge families to generate the bias matrix.</div>
        <VChart v-else class="echart echart-bias" :option="biasOption" autoresize />
      </div>
    </template>

    <!-- ── Tab: Corpus validation ──────────────────────────── -->
    <template v-if="activeTab === 'corpus'">
      <div class="corpus-section">

        <div class="chart-header">
          <div class="chart-title">CORPUS VALIDATION — validity (reliability ≠ validity)</div>
          <div class="chart-desc">
            Run configured judges against expert-annotated cases in checklist mode.
            Each sub-question has a binary expected answer (True = compliant).
            Agreement rate measures judge validity, not just reliability.
          </div>
        </div>

        <!-- Loading -->
        <div v-if="corpusLoading" class="chart-loading"><div class="loading-dots"><span/><span/><span/></div></div>

        <!-- Empty corpus -->
        <div v-else-if="!corpusCases.length" class="chart-empty">
          No cases in corpus yet. Add cases via<br/>
          <code>POST /groundtruth/corpus</code><br/>
          with <code>{ criterion, prompt, response, expected_answers: { q1: bool, … } }</code>
        </div>

        <!-- Case selector + run -->
        <template v-else>
          <div class="corpus-controls">
            <div class="corpus-filter">
              <label class="selector-label">Criterion</label>
              <select class="selector" v-model="corpusCriterion">
                <option value="">All</option>
                <option v-for="c in SUPPORTED_CRITERIA" :key="c" :value="c">{{ c }}</option>
              </select>
            </div>
            <div class="corpus-filter">
              <label class="selector-label">Case</label>
              <select class="selector corpus-case-select" v-model="selectedCaseId" :disabled="!filteredCases.length">
                <option v-for="c in filteredCases" :key="c.id" :value="c.id">
                  {{ c.source ? `[${c.source}] ` : '' }}{{ c.prompt.slice(0, 60) }}…
                </option>
              </select>
            </div>
            <button class="run-btn corpus-run-btn" @click="runCorpus" :disabled="!selectedCaseId || corpusRunning">
              <span v-if="corpusRunning" class="loading-dots"><span/><span/><span/></span>
              <span v-else>▶ Run checklist</span>
            </button>
          </div>

          <!-- Case preview -->
          <div v-if="selectedCase" class="corpus-case-preview">
            <div class="corpus-case-row">
              <span class="corpus-field-label">PROMPT</span>
              <span class="corpus-field-value">{{ selectedCase.prompt }}</span>
            </div>
            <div class="corpus-case-row">
              <span class="corpus-field-label">RESPONSE</span>
              <span class="corpus-field-value">{{ selectedCase.response }}</span>
            </div>
            <div v-if="selectedCase.source" class="corpus-case-row">
              <span class="corpus-field-label">SOURCE</span>
              <span class="corpus-field-value source-tag">{{ selectedCase.source }}</span>
            </div>
          </div>

          <!-- Results table -->
          <div v-if="corpusResult" class="corpus-results">
            <div class="corpus-results-title">RESULTS — {{ corpusResult.criterion }}</div>

            <table class="corpus-table">
              <thead>
                <tr>
                  <th class="col-judge">Judge</th>
                  <th v-for="(_, qid) in corpusResult.expected_answers" :key="qid" class="col-q">{{ qid }}</th>
                  <th class="col-score">Score</th>
                  <th class="col-agree">Agreement</th>
                </tr>
              </thead>
              <tbody>
                <!-- Expected row -->
                <tr class="expected-row">
                  <td class="col-judge judge-label">Expected</td>
                  <td v-for="(val, qid) in corpusResult.expected_answers" :key="qid" class="col-q">
                    <span class="answer-chip" :class="val ? 'ok' : 'fail'">{{ val ? '✓' : '✗' }}</span>
                  </td>
                  <td class="col-score">—</td>
                  <td class="col-agree">—</td>
                </tr>
                <!-- Judge rows -->
                <tr v-for="j in corpusResult.judges" :key="j.judge_model">
                  <td class="col-judge judge-label">
                    <span class="judge-family-dot" :style="{ background: judgeColor(j.judge_family) }"/>
                    {{ modelShortName(j.judge_model) }}
                    <span v-if="j.reason" class="judge-reason" :title="j.reason">ⓘ</span>
                  </td>
                  <td v-for="(expected, qid) in corpusResult.expected_answers" :key="qid" class="col-q">
                    <span
                      class="answer-chip"
                      :class="[j.answers[qid] ? 'ok' : 'fail', j.answers[qid] === expected ? 'match' : 'mismatch']"
                    >{{ j.answers[qid] ? '✓' : '✗' }}</span>
                  </td>
                  <td class="col-score">{{ (j.score * 100).toFixed(0) }}%</td>
                  <td class="col-agree" :class="j.agreement >= 0.75 ? 'agree-good' : j.agreement >= 0.5 ? 'agree-mid' : 'agree-bad'">
                    {{ (j.agreement * 100).toFixed(0) }}%
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Validity report -->
          <div class="validity-section">
            <button class="validity-toggle" @click="showValidity ? showValidity = false : loadValidity()" :disabled="validityLoading">
              <span v-if="validityLoading" class="loading-dots"><span/><span/><span/></span>
              <span v-else>{{ showValidity ? '↑ Hide' : '↓ Load' }} validity report</span>
            </button>

            <div v-if="showValidity && validityData && validityData.entries.length" class="validity-report">
              <div class="corpus-results-title">VALIDITY REPORT — agreement rate per judge × criterion × sub-question</div>
              <table class="corpus-table">
                <thead>
                  <tr>
                    <th>Judge</th>
                    <th>Criterion</th>
                    <th>Q</th>
                    <th>Agreement</th>
                    <th>n</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="e in validityData.entries" :key="`${e.judge_model}-${e.criterion}-${e.question_id}`">
                    <td class="judge-label">{{ modelShortName(e.judge_model) }}</td>
                    <td>{{ e.criterion }}</td>
                    <td>{{ e.question_id }}</td>
                    <td :class="e.agreement_rate >= 0.75 ? 'agree-good' : e.agreement_rate >= 0.5 ? 'agree-mid' : 'agree-bad'">
                      {{ (e.agreement_rate * 100).toFixed(0) }}%
                    </td>
                    <td class="col-n">{{ e.sample_size }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else-if="showValidity && validityData && !validityData.entries.length" class="chart-empty">
              No validity data yet — run checklist evaluations first.
            </div>
          </div>
        </template>
      </div>
    </template>

  </div>
</template>

<style scoped>
.arena-view { padding: 28px; display: flex; flex-direction: column; gap: 20px; }

.page-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.page-title { font-family: var(--font-display); font-size: 18px; font-weight: 700; margin: 0; }
.page-sub { font-size: 12px; color: var(--text-dim); margin: 4px 0 0; }

.header-selectors { display: flex; gap: 10px; align-items: flex-end; flex-shrink: 0; }
.selector-group { display: flex; flex-direction: column; gap: 3px; }
.selector-label { font-size: 9px; letter-spacing: 0.6px; color: var(--text-dim); text-transform: uppercase; }
.selector {
  font-size: 11px; padding: 4px 8px; border-radius: 6px;
  border: 1px solid var(--border); background: var(--bg-2); color: var(--text);
  cursor: pointer; outline: none; font-family: inherit;
  transition: border-color 0.15s;
}
.selector:hover:not(:disabled) { border-color: var(--accent); }
.selector:focus { border-color: var(--accent); }
.selector:disabled { opacity: 0.4; cursor: not-allowed; }

/* Prompt */
.prompt-box { background: var(--bg-2); border: 1px solid var(--border); border-radius: 8px; padding: 16px; display: flex; flex-direction: column; gap: 10px; }
.prompt-input { width: 100%; font-size: 13px; padding: 8px 10px; border: 1px solid var(--border); border-radius: 6px; resize: vertical; font-family: inherit; background: var(--bg-3); color: var(--text); outline: none; box-sizing: border-box; }
.prompt-input:focus { border-color: var(--accent); }
.prompt-input.answer-generated { border-color: rgba(0,229,255,0.3); background: rgba(0,229,255,0.03); }
.prompt-footer { display: flex; align-items: center; justify-content: space-between; }
.prompt-hint { font-size: 11px; color: var(--text-dim); }
.run-btn { font-size: 12px; padding: 6px 20px; border-radius: 20px; cursor: pointer; font-weight: 500; background: var(--accent); color: var(--bg); border: none; transition: opacity 0.15s; }
.run-btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* Mode toggle */
.mode-toggle { display: flex; gap: 2px; background: var(--bg-3); border: 1px solid var(--border); border-radius: 6px; padding: 3px; width: fit-content; }
.mode-btn { background: none; border: none; border-radius: 4px; color: var(--text-dim); font-family: var(--font-mono); font-size: 11px; padding: 4px 14px; cursor: pointer; transition: all 0.15s; }
.mode-btn:hover:not(:disabled) { color: var(--text); }
.mode-btn.active { background: var(--bg-4); color: var(--accent); }
.mode-btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* Auto-generate controls */
.auto-controls { display: flex; gap: 8px; align-items: center; }
.auto-model-select { flex: 1; background: var(--bg-3); border: 1px solid var(--border); border-radius: 6px; color: var(--text); font-family: var(--font-mono); font-size: 12px; padding: 7px 10px; outline: none; }
.auto-model-select:focus { border-color: var(--accent); }
.generate-btn { font-size: 12px; padding: 7px 18px; border-radius: 6px; cursor: pointer; font-weight: 500; background: var(--bg-3); color: var(--accent); border: 1px solid rgba(0,229,255,0.35); white-space: nowrap; transition: all 0.15s; }
.generate-btn:hover:not(:disabled) { background: var(--accent-dim); }
.generate-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.auto-hint { font-size: 11px; color: var(--text-dim); }
.auto-hint-model { color: var(--accent); font-weight: 500; }

/* Cards */
.cards-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }

.judge-card {
  background: var(--bg-2); border: 1px solid var(--border); border-radius: 10px;
  padding: 14px; display: flex; flex-direction: column; gap: 10px;
  animation: revealCard 0.4s ease both;
  position: relative; overflow: hidden;
}
.judge-card.winner { border-color: rgba(29,158,117,0.45); }

/* Shimmer sweep on loading cards */
.judge-card.loading::after {
  content: '';
  position: absolute;
  top: 0; left: -100%; width: 100%; height: 100%;
  background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.04) 50%, transparent 100%);
  animation: shimmer 1.6s ease infinite;
  pointer-events: none;
}

@keyframes shimmer { to { left: 100%; } }
@keyframes revealCard { from { opacity:0; transform:translateY(6px) } to { opacity:1; transform:translateY(0) } }

.card-header { display: flex; align-items: flex-start; justify-content: space-between; }
.card-identity { display: flex; align-items: center; gap: 8px; }
.avatar { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 500; flex-shrink: 0; }
.card-name { font-size: 12px; font-weight: 500; color: var(--text); }
.card-domain { font-size: 9px; color: var(--text-dim); letter-spacing: 0.5px; margin-top: 1px; }
.card-rank { font-size: 12px; color: var(--text-dim); }
.card-rank.rank-first { font-size: 14px; }
.card-rank-loading { opacity: 0.3; }
.crown { animation: crownBounce 1.8s ease-in-out infinite; display: inline-block; }
@keyframes crownBounce { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-3px)} }

/* Ring */
.ring-wrapper { display: flex; justify-content: center; }
.ring-arc { transition: stroke-dashoffset 1s ease; }

@keyframes ring-spin {
  from { transform: rotate(-90deg); }
  to   { transform: rotate(270deg); }
}

/* Criteria dots */
.criteria-dots { display: flex; flex-direction: column; gap: 5px; }
.dot-row { display: flex; justify-content: space-between; align-items: center; font-size: 9px; position: relative; }
.dot-row:hover .score-tooltip { opacity: 1; }
.dot-label { color: var(--text-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 80px; }
.dots { display: flex; gap: 3px; }
.dot { width: 7px; height: 7px; border-radius: 2px; }

/* Criterion score tooltip */
.score-tooltip {
  position: absolute; right: 0; bottom: calc(100% + 5px);
  background: var(--bg-4); border: 1px solid var(--border); border-radius: 6px;
  padding: 7px 10px; width: 190px;
  opacity: 0; pointer-events: none; transition: opacity 0.15s;
  z-index: 20; line-height: 1.5;
}
.tooltip-score { font-size: 12px; font-weight: 600; color: var(--text); }
.tooltip-score.flagged { color: var(--red); }
.tooltip-flag { color: var(--red); margin-left: 3px; }
.tooltip-reason { font-size: 10px; color: var(--text-dim); margin-top: 3px; white-space: normal; }

/* Incoherence badge */
.incoherence-badge { font-size: 9px; color: var(--yellow); border: 1px solid rgba(210,153,34,0.35); border-radius: 4px; padding: 2px 6px; align-self: flex-start; cursor: default; }

.dot-placeholder { animation: pulse-dot 1.3s ease infinite; }
@keyframes pulse-dot {
  0%, 100% { opacity: 0.15; }
  50%       { opacity: 0.5; }
}

/* Vote */
.vote-btn-container { display: flex; align-items: end; height: 100%; }
.vote-btn {
  width: 100%; font-size: 11px; padding: 5px; border-radius: 20px; cursor: pointer;
  border: 1px solid var(--border); background: transparent; color: var(--text-dim);
  transition: all 0.15s;
}
.vote-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.vote-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.vote-btn.voted { border-color: var(--green); color: var(--green); background: rgba(63,185,80,0.08); }
.vote-btn.voted-other { opacity: 0.35; }
.vote-btn.winner-btn { background: rgba(29,158,117,0.08); }

/* Sigma */
.sigma-section { background: var(--bg-2); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
.sigma-top { display: flex; align-items: center; gap: 20px; }
.sigma-label { font-size: 10px; letter-spacing: 1px; color: var(--text-dim); }
.sigma-value { font-size: 26px; font-weight: 500; }
.sigma-right { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.sigma-bar-track { height: 5px; background: var(--bg-3); border-radius: 3px; overflow: hidden; }
.sigma-bar-fill { height: 100%; border-radius: 3px; transition: width 1s ease, background 0.3s ease; }
.sigma-scale { display: flex; justify-content: space-between; font-size: 9px; color: var(--text-dim); }
.sigma-explanation { font-size: 12px; color: var(--text-muted); border-top: 1px solid var(--border); padding-top: 10px; line-height: 1.5; }

/* Arena tabs */
.arena-tabs { display: flex; gap: 2px; background: var(--bg-2); border: 1px solid var(--border); border-radius: 8px; padding: 4px; width: fit-content; }
.arena-tab { background: none; border: none; border-radius: 6px; color: var(--text-dim); font-family: var(--font-mono); font-size: 11px; padding: 6px 16px; cursor: pointer; transition: all 0.15s; }
.arena-tab:hover { color: var(--text); background: var(--bg-3); }
.arena-tab.active { background: var(--bg-3); color: var(--accent); border: 1px solid var(--border); }

/* Charts */
.chart-section { background: var(--bg-2); border: 1px solid var(--border); border-radius: 10px; padding: 20px; display: flex; flex-direction: column; gap: 14px; }
.chart-header { display: flex; flex-direction: column; gap: 4px; }
.chart-title { font-size: 10px; letter-spacing: 1.5px; color: var(--text-dim); }
.chart-desc { font-size: 11px; color: var(--text-muted); line-height: 1.5; }
.echart { height: 320px; width: 100%; }
.echart-bias { height: 280px; }
.chart-loading { display: flex; justify-content: center; padding: 60px 0; }
.chart-empty { font-size: 12px; color: var(--text-dim); text-align: center; padding: 48px 0; }

/* States */
.error-state { font-size: 12px; color: var(--red); padding: 12px; background: var(--bg-2); border-radius: 6px; }
.loading-dots { display: flex; gap: 4px; align-items: center; }
.loading-dots span { width: 5px; height: 5px; border-radius: 50%; background: var(--bg); animation: arena-bounce 1.2s ease infinite; }
.loading-dots span:nth-child(2) { animation-delay: 0.15s; }
.loading-dots span:nth-child(3) { animation-delay: 0.3s; }
@keyframes arena-bounce { 0%,100%{transform:translateY(0);opacity:0.4} 50%{transform:translateY(-4px);opacity:1} }

/* Corpus validation tab */
.corpus-section { background: var(--bg-2); border: 1px solid var(--border); border-radius: 10px; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.corpus-controls { display: flex; align-items: flex-end; gap: 12px; flex-wrap: wrap; }
.corpus-filter { display: flex; flex-direction: column; gap: 3px; }
.corpus-case-select { max-width: 320px; }
.corpus-run-btn { border-radius: 6px; padding: 6px 18px; flex-shrink: 0; }

.corpus-case-preview { background: var(--bg-3); border: 1px solid var(--border); border-radius: 8px; padding: 14px; display: flex; flex-direction: column; gap: 8px; }
.corpus-case-row { display: flex; gap: 10px; }
.corpus-field-label { font-size: 9px; letter-spacing: 1px; color: var(--text-dim); flex-shrink: 0; padding-top: 1px; min-width: 60px; }
.corpus-field-value { font-size: 12px; color: var(--text-muted); line-height: 1.5; }
.source-tag { color: var(--accent); font-size: 11px; }

/* Results table */
.corpus-results { display: flex; flex-direction: column; gap: 10px; }
.corpus-results-title { font-size: 10px; letter-spacing: 1.5px; color: var(--text-dim); }
.corpus-table { width: 100%; border-collapse: collapse; font-family: var(--font-mono); font-size: 11px; }
.corpus-table th { padding: 6px 10px; color: var(--text-dim); border-bottom: 1px solid var(--border); text-align: left; font-weight: 500; font-size: 10px; letter-spacing: 0.5px; }
.corpus-table td { padding: 6px 10px; border-bottom: 1px solid var(--border); color: var(--text-muted); }
.col-judge { width: 140px; }
.col-q { width: 50px; text-align: center; }
.col-score, .col-agree { width: 70px; text-align: right; }
.col-n { width: 40px; text-align: right; color: var(--text-dim); }

.expected-row td { background: var(--bg-3); }
.judge-label { color: var(--text); font-size: 11px; display: flex; align-items: center; gap: 5px; }
.judge-family-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; display: inline-block; }
.judge-reason { font-size: 9px; color: var(--text-dim); cursor: default; }

.answer-chip { display: inline-block; font-size: 11px; font-weight: 600; padding: 1px 5px; border-radius: 3px; }
.answer-chip.ok { color: #1d9e75; }
.answer-chip.fail { color: #e24b4a; }
.answer-chip.match { background: rgba(29,158,117,0.12); }
.answer-chip.mismatch { background: rgba(226,75,74,0.12); }

.agree-good { color: #1d9e75; font-weight: 600; }
.agree-mid  { color: #ba7517; }
.agree-bad  { color: #e24b4a; }

/* Validity report */
.validity-section { border-top: 1px solid var(--border); padding-top: 12px; display: flex; flex-direction: column; gap: 10px; }
.validity-toggle { background: none; border: 1px dashed var(--border); border-radius: 6px; color: var(--text-dim); font-family: var(--font-mono); font-size: 11px; padding: 7px 14px; cursor: pointer; transition: all 0.15s; width: fit-content; }
.validity-toggle:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.validity-report { display: flex; flex-direction: column; gap: 8px; }
</style>
