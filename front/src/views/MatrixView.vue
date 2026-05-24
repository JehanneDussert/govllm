<!--
  SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
  SPDX-License-Identifier: EUPL-1.2
-->

// Imports
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '@/api/client'
import type {
  MatrixResponse,
  MatrixCell,
  MatrixUseCase,
  ModelLifecycleStatus,
  LifecycleTransition,
  LifecycleZone,
  SasResult,
  SasLmsysResult,
} from '@/api/client'
import { useJudgeStore } from '@/stores/judge'
import { useIntervalFn } from '@vueuse/core'
import { modelShortName as shortName } from '@/utils/model'
import { scoreClass } from '@/utils/score'

// Stores
const judgeStore = useJudgeStore()

// Constants
const SPARK_COLORS = ['#00e5ff', '#a78bfa']

// Reactive state
const matrix = ref<MatrixResponse | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const lastUpdated = ref<string | null>(null)

// Lifecycle
const lifecycleStatus = ref<ModelLifecycleStatus[]>([])
const drawerModel = ref<string | null>(null)
const drawerHistory = ref<LifecycleTransition[]>([])
const drawerLoading = ref(false)
const sasRunning = ref(false)
const sasResult = ref<SasResult | null>(null)
const lmsysRunning = ref(false)
const lmsysResult = ref<SasLmsysResult | null>(null)

const ZONE_LABEL: Record<LifecycleZone, string> = {
  test: 'TEST',
  validation: 'VALIDATION',
  production: 'PROD',
  quarantine: 'QUARANTINE',
}

function zoneClass(zone: LifecycleZone) {
  return `zone-${zone}`
}

function modelZone(model: string): LifecycleZone {
  return lifecycleStatus.value.find((s) => s.model === model)?.zone ?? 'test'
}

async function loadLifecycle() {
  try {
    const res = await api.lifecycleStatus()
    lifecycleStatus.value = res.data
  } catch {
    // lifecycle endpoint optional — silently ignore if DB not migrated yet
  }
}

async function openDrawer(model: string) {
  drawerModel.value = model
  drawerLoading.value = true
  sasResult.value = null
  try {
    const res = await api.lifecycleHistory(model)
    drawerHistory.value = res.data.transitions
  } finally {
    drawerLoading.value = false
  }
}

function closeDrawer() {
  drawerModel.value = null
  drawerHistory.value = []
  sasResult.value = null
  lmsysResult.value = null
}

async function validate(model: string) {
  await api.lifecycleValidate(model, 'Human validation via Matrix UI')
  await loadLifecycle()
  await openDrawer(model)
}

async function quarantine(model: string) {
  await api.lifecycleQuarantine(model, 'Manual quarantine via Matrix UI')
  await loadLifecycle()
  await openDrawer(model)
}

async function runSas(model: string) {
  sasRunning.value = true
  lmsysResult.value = null
  try {
    const res = await api.lifecycleSas(model)
    sasResult.value = res.data
    await loadLifecycle()
    await openDrawer(model)
  } finally {
    sasRunning.value = false
  }
}

async function runLmsysSas(model: string) {
  lmsysRunning.value = true
  sasResult.value = null
  try {
    const res = await api.lifecycleSasLmsys(model)
    lmsysResult.value = res.data
    await loadLifecycle()
    await openDrawer(model)
  } finally {
    lmsysRunning.value = false
  }
}

const models = computed(() => {
  if (!matrix.value) return []
  const first = Object.values(matrix.value)[0]
  if (!first) return []
  return Object.keys(first.models)
})

async function refresh() {
  loading.value = true
  error.value = null
  try {
    if (!judgeStore.config) await judgeStore.fetchConfig()
    const res = await api.getMatrix()
    matrix.value = res.data
    lastUpdated.value = new Date().toLocaleTimeString()
  } catch {
    error.value = 'Failed to fetch matrix — is evaluation running?'
  } finally {
    loading.value = false
  }
}

const gridStyle = computed(() => ({
  gridTemplateColumns: `180px repeat(${models.value.length}, 1fr)`,
}))

function cellClass(cell: MatrixCell | null | undefined) {
  if (!cell || cell.avg_score === null) return 'cell-empty'
  if (cell.avg_score >= 0.7) return 'cell-good'
  if (cell.avg_score >= 0.4) return 'cell-medium'
  return 'cell-bad'
}

function trendIcon(trend: string | null) {
  if (trend === 'up') return '↑'
  if (trend === 'down') return '↓'
  if (trend === 'stable') return '→'
  return ''
}

function sparklinePoints(scores: number[]) {
  if (!scores.length) return ''
  const w = 60,
    h = 20,
    pad = 2
  const min = Math.min(...scores)
  const max = Math.max(...scores)
  const range = max - min || 1
  return scores
    .map((s, i) => {
      const x = pad + (i / (scores.length - 1 || 1)) * (w - pad * 2)
      const y = h - pad - ((s - min) / range) * (h - pad * 2)
      return `${x},${y}`
    })
    .join(' ')
}

function sparklineColor(modelIndex: number) {
  return SPARK_COLORS[modelIndex] ?? '#7d8590'
}

const matrixWithWinner = computed(() => {
  if (!matrix.value) return {}
  const result: Record<string, MatrixUseCase & { winner: string | null; winnerScore: number | null; winnerIndex: number }> = {}
  for (const [id, data] of Object.entries(matrix.value)) {
    let winner = null
    let winnerScore: number | null = null
    let winnerIndex = -1
    models.value.forEach((model: string, i: number) => {
      const cell = data.models[model]
      if (cell?.avg_score !== null && cell?.avg_score !== undefined) {
        if (winnerScore === null || cell.avg_score > winnerScore) {
          winner = model
          winnerScore = cell.avg_score
          winnerIndex = i
        }
      }
    })
    result[id] = { ...data, winner, winnerScore, winnerIndex }
  }
  return result
})

onMounted(() => {
  refresh()
  loadLifecycle()
})
useIntervalFn(refresh, 60000)
</script>

<template>
  <div class="matrix-view">
    <div class="page-header">
      <h1 class="page-title">Model × Use Case Matrix</h1>
      <div class="header-right">
        <span class="last-updated" v-if="lastUpdated">updated {{ lastUpdated }}</span>
        <button class="refresh-btn" @click="refresh" :class="{ spinning: loading }">↻</button>
      </div>
    </div>

    <p class="page-desc">
      Average scores per model and use case — determines which model to route per task.
    </p>

    <div v-if="loading && !matrix" class="loading-state">
      <div class="loading-dots"><span /><span /><span /></div>
    </div>

    <div v-else-if="error" class="error-state">{{ error }}</div>

    <div v-else-if="matrix" class="matrix-content">
      <!-- Legend -->
      <div class="legend">
        <div class="legend-item" v-for="(model, i) in models" :key="model">
          <span class="legend-dot" :class="`color-${i}`" />
          <span>{{ shortName(model) }}</span>
        </div>
        <div class="legend-sep" />
        <div class="legend-item"><span class="trend-icon up">↑</span> improving</div>
        <div class="legend-item"><span class="trend-icon down">↓</span> degrading</div>
        <div class="legend-item"><span class="trend-icon stable">→</span> stable</div>
      </div>

      <!-- Matrix -->
      <div class="matrix-table">
        <!-- Header -->
        <div class="matrix-header" :style="gridStyle">
          <div class="cell cell-label">USE CASE</div>
          <div
            class="cell cell-model"
            v-for="model in models"
            :key="model"
            @click="openDrawer(model)"
            style="cursor: pointer"
          >
            <span>{{ shortName(model) }}</span>
            <span class="zone-badge" :class="zoneClass(modelZone(model))">
              {{ ZONE_LABEL[modelZone(model)] }}
            </span>
          </div>
        </div>

        <!-- Rows -->
        <div
          v-for="(data, useCaseId) in matrix"
          :key="useCaseId"
          class="matrix-row"
          :style="gridStyle"
        >
          <div class="cell cell-label">
            <span class="uc-label">{{ data.label }}</span>
            <span class="uc-id">{{ useCaseId }}</span>
          </div>

          <div
            class="cell cell-score"
            v-for="(model, i) in models"
            :key="model"
            :class="cellClass(data.models[model])"
          >
            <template
              v-if="
                data.models[model]?.avg_score !== null &&
                data.models[model]?.avg_score !== undefined
              "
            >
              <div class="score-main">
                <span class="score-num" :class="scoreClass(data.models[model].avg_score!)">
                  {{ data.models[model].avg_score!.toFixed(2) }}
                </span>
                <span class="trend-icon" :class="data.models[model].trend ?? ''">
                  {{ trendIcon(data.models[model].trend) }}
                </span>
              </div>
              <div class="score-sub">{{ data.models[model].sample_size }} samples</div>
              <!-- Sparkline -->
              <svg class="sparkline" viewBox="0 0 60 20" preserveAspectRatio="none">
                <polyline
                  :points="sparklinePoints(data.models[model].scores)"
                  fill="none"
                  :stroke="sparklineColor(i)"
                  stroke-width="1.5"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
              <!-- Hover tooltip -->
              <div class="cell-tooltip">
                <div class="tooltip-header">
                  <span :class="['tooltip-score', scoreClass(data.models[model].avg_score!)]">
                    {{ data.models[model].avg_score!.toFixed(3) }}
                  </span>
                  <span class="tooltip-trend" :class="data.models[model].trend ?? ''">
                    {{ trendIcon(data.models[model].trend) }}
                  </span>
                </div>
                <div class="tooltip-meta">
                  {{ data.models[model].sample_size }} samples · {{ shortName(model) }}
                </div>
                <div class="tooltip-scores" v-if="data.models[model].scores.length">
                  <span class="tooltip-scores-label">last scores</span>
                  <div class="tooltip-score-pills">
                    <span
                      v-for="(s, idx) in data.models[model].scores.slice(-5)"
                      :key="idx"
                      class="score-pill"
                      :class="scoreClass(s)"
                      >{{ s.toFixed(2) }}</span
                    >
                  </div>
                </div>
              </div>
            </template>
            <template v-else>
              <span class="no-data">—</span>
              <span class="no-data-sub">no data</span>
            </template>
          </div>
        </div>
      </div>

      <!-- Best model per use case -->
      <div class="recommendations">
        <div class="section-title">ROUTING RECOMMENDATIONS</div>
        <div class="reco-grid">
          <div v-for="(data, useCaseId) in matrixWithWinner" :key="useCaseId" class="reco-card">
            <div class="reco-usecase">{{ data.label }}</div>
            <div v-if="data.winner" class="reco-winner">
              <span class="reco-arrow">→</span>
              <span class="reco-model" :class="'model-color-' + data.winnerIndex">
                {{ shortName(data.winner) }}
              </span>
              <span class="reco-score">{{ data.winnerScore?.toFixed(2) }}</span>
            </div>
            <div v-else class="reco-nodata">insufficient data</div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Lifecycle drawer -->
  <Transition name="drawer">
    <div v-if="drawerModel" class="drawer-overlay" @click.self="closeDrawer">
      <div class="drawer">
        <div class="drawer-header">
          <div class="drawer-title">
            <span class="drawer-model">{{ shortName(drawerModel) }}</span>
            <span class="zone-badge" :class="zoneClass(modelZone(drawerModel))">
              {{ ZONE_LABEL[modelZone(drawerModel)] }}
            </span>
          </div>
          <button class="drawer-close" @click="closeDrawer">✕</button>
        </div>

        <!-- SAS result banner -->
        <div v-if="sasResult" class="sas-result" :class="`sas-${sasResult.decision}`">
          <div class="sas-decision">
            {{
              sasResult.decision === 'promote'
                ? '↑ Promoted'
                : sasResult.decision === 'quarantine'
                  ? '⚠ Quarantined'
                  : '— No data'
            }}
          </div>
          <div class="sas-meta" v-if="sasResult.avg_score !== null">
            avg {{ sasResult.avg_score.toFixed(3) }} · threshold {{ sasResult.threshold }} ·
            {{ sasResult.sample_size }} samples
          </div>
          <div class="sas-meta" v-else>No evaluation data in Redis yet</div>
        </div>

        <!-- LMSYS SAS result -->
        <div v-if="lmsysResult" class="sas-result" :class="`sas-${lmsysResult.decision}`">
          <div class="sas-decision">
            LMSYS —
            {{
              lmsysResult.decision === 'promote'
                ? '↑ Promoted'
                : lmsysResult.decision === 'quarantine'
                  ? '⚠ Quarantined'
                  : '— No data'
            }}
          </div>
          <div class="sas-meta" v-if="lmsysResult.avg_score !== null">
            avg {{ lmsysResult.avg_score.toFixed(3) }} · {{ lmsysResult.prompts_tested }} prompts
            tested
          </div>
          <div class="sas-meta" v-else>Model call failed or no results</div>
          <div class="lmsys-breakdown" v-if="Object.keys(lmsysResult.criteria_breakdown).length">
            <div
              v-for="(score, cid) in lmsysResult.criteria_breakdown"
              :key="cid"
              class="breakdown-row"
            >
              <span class="breakdown-cid">{{ String(cid).replace('_', ' ') }}</span>
              <span class="breakdown-score" :class="scoreClass(score)">{{ score.toFixed(2) }}</span>
            </div>
          </div>
        </div>

        <!-- Actions -->
        <div class="drawer-actions">
          <button class="action-btn btn-validate" @click="validate(drawerModel!)">
            ✓ Validate → Prod
          </button>
          <button class="action-btn btn-quarantine" @click="quarantine(drawerModel!)">
            ⚠ Quarantine
          </button>
          <button
            class="action-btn btn-sas"
            @click="runSas(drawerModel!)"
            :disabled="sasRunning || lmsysRunning"
          >
            {{ sasRunning ? 'Running…' : '▶ SAS' }}
          </button>
          <button
            class="action-btn btn-lmsys"
            @click="runLmsysSas(drawerModel!)"
            :disabled="sasRunning || lmsysRunning"
          >
            {{ lmsysRunning ? 'Running…' : '▶ LMSYS' }}
          </button>
        </div>

        <!-- Timeline -->
        <div class="drawer-section-title">TRANSITION HISTORY</div>
        <div v-if="drawerLoading" class="drawer-loading">
          <div class="loading-dots"><span /><span /><span /></div>
        </div>
        <div v-else-if="!drawerHistory.length" class="drawer-empty">
          No transitions recorded yet.
        </div>
        <div v-else class="timeline">
          <div v-for="t in drawerHistory" :key="t.id" class="timeline-item">
            <span class="zone-badge" :class="zoneClass(t.zone as LifecycleZone)">
              {{ ZONE_LABEL[t.zone as LifecycleZone] }}
            </span>
            <div class="timeline-meta">
              <span class="tl-operator">{{ t.operator }}</span>
              <span class="tl-date">{{ new Date(t.created_at).toLocaleString() }}</span>
              <span class="tl-score" v-if="t.score !== null">score {{ t.score.toFixed(3) }}</span>
            </div>
            <div class="tl-note" v-if="t.note">{{ t.note }}</div>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.matrix-view {
  padding: 28px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.page-title {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 700;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.last-updated {
  font-size: 11px;
  color: var(--text-dim);
}

.refresh-btn {
  background: none;
  border: 1px solid var(--border);
  border-radius: 5px;
  color: var(--text-muted);
  font-size: 14px;
  width: 28px;
  height: 28px;
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
}
.refresh-btn:hover {
  color: var(--accent);
  border-color: var(--accent);
}
.refresh-btn.spinning {
  animation: spin 1s linear infinite;
}

.page-desc {
  font-size: 12px;
  color: var(--text-dim);
  margin-top: -12px;
}

/* Legend */
.legend {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 24px;
}
.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.legend-dot.color-0 {
  background: var(--accent);
}
.legend-dot.color-1 {
  background: #a78bfa;
}
.legend-dot.color-2 {
  background: var(--green);
}
.legend-dot.color-3 {
  background: #f0883e;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 5px;
}
.legend-sep {
  width: 1px;
  height: 16px;
  background: var(--border);
}
.trend-icon {
  font-size: 12px;
}
.trend-icon.up {
  color: var(--green);
}
.trend-icon.down {
  color: var(--red);
}
.trend-icon.stable {
  color: var(--text-dim);
}

/* Matrix table */
.matrix-table {
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.matrix-header {
  display: grid;
  background: var(--bg-3);
  border-bottom: 1px solid var(--border);
}

.matrix-row {
  display: grid;
  border-bottom: 1px solid var(--border);
  transition: background 0.1s;
}
.matrix-row:last-child {
  border-bottom: none;
}
.matrix-row:hover {
  background: var(--bg-3);
}

.cell {
  padding: 14px 16px;
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 4px;
  position: relative;
}
.cell:last-child {
  border-right: none;
}

/* Hover tooltip */
.cell-tooltip {
  display: none;
  position: absolute;
  bottom: calc(100% + 6px);
  left: 50%;
  transform: translateX(-50%);
  background: var(--bg-3);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  min-width: 160px;
  max-width: 220px;
  z-index: 100;
  pointer-events: none;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
}
.cell-score:hover .cell-tooltip {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.tooltip-header {
  display: flex;
  align-items: center;
  gap: 6px;
}
.tooltip-score {
  font-size: 18px;
  font-weight: 600;
}
.tooltip-score.green {
  color: var(--green);
}
.tooltip-score.yellow {
  color: var(--yellow);
}
.tooltip-score.red {
  color: var(--red);
}
.tooltip-trend {
  font-size: 14px;
}
.tooltip-trend.up {
  color: var(--green);
}
.tooltip-trend.down {
  color: var(--red);
}
.tooltip-trend.stable {
  color: var(--text-dim);
}

.tooltip-meta {
  font-size: 10px;
  color: var(--text-dim);
}

.tooltip-scores {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.tooltip-scores-label {
  font-size: 9px;
  letter-spacing: 1px;
  color: var(--text-dim);
  text-transform: uppercase;
}
.tooltip-score-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.score-pill {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 20px;
  background: var(--bg-2);
  border: 1px solid var(--border);
}
.score-pill.green {
  color: var(--green);
  border-color: rgba(63, 185, 80, 0.3);
}
.score-pill.yellow {
  color: var(--yellow);
  border-color: rgba(210, 153, 34, 0.3);
}
.score-pill.red {
  color: var(--red);
  border-color: rgba(248, 81, 73, 0.3);
}

.cell-label {
  font-size: 10px;
  letter-spacing: 0.8px;
  color: var(--text-dim);
  justify-content: center;
}

.cell-model {
  font-size: 11px;
  color: var(--text-muted);
  align-items: center;
}

.uc-label {
  font-size: 12px;
  color: var(--text);
}
.uc-id {
  font-size: 10px;
  color: var(--text-dim);
}

.score-main {
  display: flex;
  align-items: center;
  gap: 6px;
}
.score-num {
  font-size: 20px;
  font-weight: 500;
}
.score-num.green {
  color: var(--green);
}
.score-num.yellow {
  color: var(--yellow);
}
.score-num.red {
  color: var(--red);
}

.score-sub {
  font-size: 10px;
  color: var(--text-dim);
}

.sparkline {
  width: 60px;
  height: 20px;
  margin-top: 4px;
}

.no-data {
  font-size: 18px;
  color: var(--text-dim);
}
.no-data-sub {
  font-size: 10px;
  color: var(--text-dim);
}

.cell-good {
  background: rgba(63, 185, 80, 0.03);
}
.cell-bad {
  background: rgba(248, 81, 73, 0.03);
}
.cell-empty {
  opacity: 0.5;
}

/* Recommendations */
.recommendations {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 32px 0 24px 0;
}
.section-title {
  font-size: 10px;
  letter-spacing: 1.5px;
  color: var(--text-dim);
}

.reco-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}

.reco-card {
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.reco-usecase {
  font-size: 11px;
  color: var(--text-muted);
}

.reco-winner {
  display: flex;
  align-items: center;
  gap: 8px;
}
.reco-arrow {
  color: var(--text-dim);
  font-size: 12px;
}
.reco-model {
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 600;
}
.reco-model.model-color-0 {
  color: var(--accent);
}
.reco-model.model-color-1 {
  color: #a78bfa;
}
.reco-model.model-color-2 {
  color: var(--green);
}
.reco-model.model-color-3 {
  color: #f0883e;
}
.reco-score {
  font-size: 11px;
  color: var(--text-dim);
  background: var(--bg-3);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 1px 8px;
}

.reco-nodata {
  font-size: 11px;
  color: var(--text-dim);
  font-style: italic;
}

/* States */
.loading-state,
.error-state {
  display: flex;
  justify-content: center;
  padding: 60px 0;
  color: var(--text-dim);
}

/* Zone badges */
.zone-badge {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.8px;
  padding: 2px 6px;
  border-radius: 20px;
  border: 1px solid;
  white-space: nowrap;
}
.zone-test {
  color: #7d8590;
  border-color: #7d8590;
  background: rgba(125, 133, 144, 0.08);
}
.zone-validation {
  color: #f0883e;
  border-color: #f0883e;
  background: rgba(240, 136, 62, 0.08);
}
.zone-production {
  color: var(--green);
  border-color: var(--green);
  background: rgba(63, 185, 80, 0.08);
}
.zone-quarantine {
  color: var(--red);
  border-color: var(--red);
  background: rgba(248, 81, 73, 0.08);
}

/* Drawer */
.drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  z-index: 200;
  display: flex;
  justify-content: flex-end;
}
.drawer {
  width: 360px;
  height: 100%;
  background: var(--bg-2);
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 0;
  overflow-y: auto;
}
.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 20px 16px;
  border-bottom: 1px solid var(--border);
}
.drawer-title {
  display: flex;
  align-items: center;
  gap: 10px;
}
.drawer-model {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 600;
}
.drawer-close {
  background: none;
  border: none;
  color: var(--text-dim);
  font-size: 14px;
  cursor: pointer;
  padding: 4px 8px;
}
.drawer-close:hover {
  color: var(--text);
}

.drawer-actions {
  display: flex;
  gap: 8px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}
.action-btn {
  flex: 1;
  padding: 7px 4px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid;
  transition: opacity 0.15s;
}
.action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.btn-validate {
  background: rgba(63, 185, 80, 0.1);
  color: var(--green);
  border-color: var(--green);
}
.btn-quarantine {
  background: rgba(248, 81, 73, 0.1);
  color: var(--red);
  border-color: var(--red);
}
.btn-sas {
  background: rgba(0, 229, 255, 0.1);
  color: var(--accent);
  border-color: var(--accent);
}
.btn-lmsys {
  background: rgba(167, 139, 250, 0.1);
  color: #a78bfa;
  border-color: #a78bfa;
}

.lmsys-breakdown {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.breakdown-row {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
}
.breakdown-cid {
  color: var(--text-dim);
}
.breakdown-score {
  font-weight: 600;
}
.breakdown-score.green {
  color: var(--green);
}
.breakdown-score.yellow {
  color: var(--yellow);
}
.breakdown-score.red {
  color: var(--red);
}

.sas-result {
  margin: 12px 20px 0;
  padding: 10px 14px;
  border-radius: 8px;
  border: 1px solid var(--border);
}
.sas-promote {
  border-color: var(--green);
  background: rgba(63, 185, 80, 0.07);
}
.sas-quarantine {
  border-color: var(--red);
  background: rgba(248, 81, 73, 0.07);
}
.sas-no_data {
  border-color: var(--border);
}
.sas-decision {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 4px;
}
.sas-meta {
  font-size: 11px;
  color: var(--text-dim);
}

.drawer-section-title {
  font-size: 9px;
  letter-spacing: 1.5px;
  color: var(--text-dim);
  padding: 16px 20px 8px;
}
.drawer-loading,
.drawer-empty {
  padding: 20px;
  color: var(--text-dim);
  font-size: 12px;
  font-style: italic;
}

.timeline {
  display: flex;
  flex-direction: column;
  padding: 0 20px 20px;
  gap: 12px;
}
.timeline-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-left: 12px;
  border-left: 2px solid var(--border);
}
.timeline-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.tl-operator {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 600;
}
.tl-date {
  font-size: 10px;
  color: var(--text-dim);
}
.tl-score {
  font-size: 10px;
  color: var(--text-dim);
  background: var(--bg-3);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 1px 6px;
}
.tl-note {
  font-size: 11px;
  color: var(--text-dim);
  font-style: italic;
}

/* Drawer slide transition */
.drawer-enter-active,
.drawer-leave-active {
  transition: opacity 0.2s;
}
.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}
.drawer-enter-active .drawer,
.drawer-leave-active .drawer {
  transition: transform 0.25s ease;
}
.drawer-enter-from .drawer,
.drawer-leave-to .drawer {
  transform: translateX(100%);
}
</style>
