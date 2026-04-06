<!--
  SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
  SPDX-License-Identifier: EUPL-1.2
-->

// Imports
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '@/api/client'
import type { MatrixResponse } from '@/api/client'
import { useJudgeStore } from '@/stores/judge'
import { useIntervalFn } from '@vueuse/core'

// Stores
const judgeStore = useJudgeStore()

// Constants
const SPARK_COLORS = ['#00e5ff', '#a78bfa']

// Reactive state
const matrix = ref<MatrixResponse | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const lastUpdated = ref<string | null>(null)

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

function shortName(model: string) {
  return model.split('/').pop() ?? model
}

function scoreClass(score: number) {
  if (score >= 0.7) return 'green'
  if (score >= 0.4) return 'yellow'
  return 'red'
}

function cellClass(cell: any) {
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
  const result: Record<string, any> = {}
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

onMounted(refresh)
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
      <!-- Légende -->
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

      <!-- Matrice -->
      <div class="matrix-table">
        <!-- Header -->
        <div class="matrix-header" :style="gridStyle">
          <div class="cell cell-label">USE CASE</div>
          <div class="cell cell-model" v-for="model in models" :key="model">
            {{ shortName(model) }}
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
}
.cell:last-child {
  border-right: none;
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
.loading-dots {
  display: flex;
  gap: 6px;
}
.loading-dots span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  animation: bounce 1.2s ease infinite;
}
.loading-dots span:nth-child(2) {
  animation-delay: 0.2s;
}
.loading-dots span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
@keyframes bounce {
  0%,
  100% {
    transform: translateY(0);
    opacity: 0.4;
  }
  50% {
    transform: translateY(-6px);
    opacity: 1;
  }
}
</style>
