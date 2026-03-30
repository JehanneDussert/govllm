<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '@/api/client'
import type { BenchmarkResponse } from '@/api/client'
import { useIntervalFn } from '@vueuse/core'

const data = ref<BenchmarkResponse | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const lastUpdated = ref<string | null>(null)

async function refresh() {
  loading.value = true
  error.value = null
  try {
    const res = await api.benchmarkResults()
    data.value = res.data
    lastUpdated.value = new Date().toLocaleTimeString()
  } catch {
    error.value = 'Failed to fetch benchmark results — is evaluation running?'
  } finally {
    loading.value = false
  }
}

function shortName(model: string) {
  return model.split('/').pop() ?? model
}

function latencyClass(ms: number) {
  if (ms < 3000) return 'green'
  if (ms < 8000) return 'yellow'
  return 'red'
}

function errorClass(rate: number) {
  if (rate === 0) return 'green'
  if (rate < 0.05) return 'yellow'
  return 'red'
}

function scoreClass(score: number | null) {
  if (score === null) return ''
  if (score >= 0.7) return 'green'
  if (score >= 0.4) return 'yellow'
  return 'red'
}

const maxLatency = computed(() =>
  Math.max(...(data.value?.models.map(m => m.avg_latency_ms) ?? [1]))
)

function latencyBarWidth(ms: number) {
  return Math.round((ms / (maxLatency.value || 1)) * 100)
}

const MODEL_COLORS = ['#00e5ff', '#a78bfa', '#3fb950', '#f0883e']

function modelColor(i: number) {
  return MODEL_COLORS[i % MODEL_COLORS.length]
}

const sortedModels = computed(() => {
  if (!data.value) return []
  return [...data.value.models].sort((a, b) => {
    if (a.avg_eval_score !== null && b.avg_eval_score !== null)
      return b.avg_eval_score - a.avg_eval_score
    return a.avg_latency_ms - b.avg_latency_ms
  })
})

const winnerReason = computed(() => {
  if (!data.value?.winner || !sortedModels.value.length) return ''
  const winner = sortedModels.value.find(m => m.model === data.value!.winner)
  const second = sortedModels.value.find(m => m.model !== data.value!.winner)
  if (!winner || !second) return ''
  if (winner.avg_eval_score !== null && second.avg_eval_score !== null) {
    return `best eval score (${winner.avg_eval_score.toFixed(3)} vs ${second.avg_eval_score.toFixed(3)})`
  }
  return `lowest latency (${winner.avg_latency_ms.toFixed(1)}ms)`
})

onMounted(refresh)
useIntervalFn(refresh, 30000)
</script>

<template>
  <div class="benchmark-view">
    <div class="page-header">
      <h1 class="page-title">Benchmark</h1>
      <div class="header-right">
        <span class="last-updated" v-if="lastUpdated">updated {{ lastUpdated }}</span>
        <button class="refresh-btn" @click="refresh" :class="{ spinning: loading }">↻</button>
      </div>
    </div>

    <div v-if="loading && !data" class="loading-state">
      <div class="loading-dots"><span /><span /><span /></div>
    </div>

    <div v-else-if="error" class="error-state">{{ error }}</div>

    <div v-else-if="data" class="benchmark-content">
      <!-- Winner banner -->
      <div v-if="data.winner" class="winner-banner">
        <span class="winner-label">WINNER</span>
        <span class="winner-model">{{ shortName(data.winner) }}</span>
        <span class="winner-reason">{{ winnerReason }}</span>
      </div>
      <div v-else class="no-winner-banner">
        Not enough data to determine a winner — need at least 3 samples per model.
      </div>

      <!-- Model cards -->
      <div class="model-grid">
        <div
          v-for="(model, i) in sortedModels"
          :key="model.model"
          class="model-card"
          :class="{
            'card-winner': data.winner === model.model,
            'card-loser': data.winner && data.winner !== model.model,
          }"
        >
          <div class="card-header">
            <div class="card-name" :style="{ color: modelColor(i) }">
              {{ shortName(model.model) }}
            </div>
            <div v-if="data.winner === model.model" class="winner-badge">✓ winner</div>
            <div v-else-if="i === 0 && !data.winner" class="rank-badge">#1</div>
            <div v-else class="rank-badge muted">#{{ i + 1 }}</div>
          </div>

          <div class="card-stats">
            <div class="stat">
              <div class="stat-label">SAMPLES</div>
              <div class="stat-value">{{ model.sample_size }}</div>
            </div>
            <div class="stat">
              <div class="stat-label">AVG LATENCY</div>
              <div class="stat-value" :class="latencyClass(model.avg_latency_ms)">
                {{ model.avg_latency_ms.toFixed(1) }}ms
              </div>
            </div>
            <div class="stat">
              <div class="stat-label">ERROR RATE</div>
              <div class="stat-value" :class="errorClass(model.error_rate)">
                {{ (model.error_rate * 100).toFixed(1) }}%
              </div>
            </div>
            <div class="stat">
              <div class="stat-label">EVAL SCORE</div>
              <div class="stat-value" :class="scoreClass(model.avg_eval_score)">
                {{ model.avg_eval_score?.toFixed(3) ?? '—' }}
              </div>
            </div>
            <div class="stat">
              <div class="stat-label">AVG TOKENS</div>
              <div class="stat-value">{{ model.avg_tokens ? model.avg_tokens.toFixed(0) : '—' }}</div>
            </div>
          </div>

          <div class="latency-bar-section">
            <div class="bar-label">latency vs others</div>
            <div class="bar-track">
              <div
                class="bar-fill"
                :style="{
                  width: latencyBarWidth(model.avg_latency_ms) + '%',
                  background: modelColor(i),
                }"
              />
            </div>
          </div>
        </div>
      </div>

      <div class="summary">
        <span class="summary-label">WINDOW</span>
        <span class="summary-value">{{ data.window }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.benchmark-view { padding: 28px; display: flex; flex-direction: column; gap: 24px; }
.page-header { display: flex; align-items: center; justify-content: space-between; }
.page-title { font-family: var(--font-display); font-size: 18px; font-weight: 700; }
.header-right { display: flex; align-items: center; gap: 12px; }
.last-updated { font-size: 11px; color: var(--text-dim); }
.refresh-btn {
  background: none; border: 1px solid var(--border); border-radius: 5px;
  color: var(--text-muted); font-size: 14px; width: 28px; height: 28px;
  cursor: pointer; transition: all 0.15s; display: flex; align-items: center; justify-content: center;
}
.refresh-btn:hover { color: var(--accent); border-color: var(--accent); }
.refresh-btn.spinning { animation: spin 1s linear infinite; }

.winner-banner {
  display: flex; align-items: center; gap: 12px;
  background: rgba(63,185,80,0.08); border: 1px solid rgba(63,185,80,0.3);
  border-radius: 8px; padding: 14px 20px;
  margin-bottom: 24px;
}
.winner-label { font-size: 10px; letter-spacing: 1.5px; color: var(--green); }
.winner-model { font-family: var(--font-display); font-size: 16px; font-weight: 700; color: var(--green); }
.winner-reason { font-size: 12px; color: var(--text-muted); }
.no-winner-banner {
  background: var(--bg-2); border: 1px solid var(--border);
  border-radius: 8px; padding: 14px 20px; font-size: 12px; color: var(--text-dim);
  margin-bottom: 24px;
}

.model-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}

.model-card {
  background: var(--bg-2); border: 1px solid var(--border);
  border-radius: 8px; padding: 20px;
  display: flex; flex-direction: column; gap: 16px;
  transition: border-color 0.2s;
}
.model-card.card-winner { border-color: rgba(63,185,80,0.4); }
.model-card.card-loser { opacity: 0.75; }

.card-header { display: flex; align-items: center; justify-content: space-between; }
.card-name { font-family: var(--font-display); font-size: 15px; font-weight: 600; }
.winner-badge {
  font-size: 10px; color: var(--green);
  background: rgba(63,185,80,0.1); border: 1px solid rgba(63,185,80,0.3);
  border-radius: 20px; padding: 2px 10px;
}
.rank-badge { font-size: 11px; color: var(--text-dim); }
.rank-badge.muted { opacity: 0.5; }

.card-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.stat { display: flex; flex-direction: column; gap: 3px; }
.stat-label { font-size: 10px; letter-spacing: .8px; color: var(--text-dim); }
.stat-value { font-size: 18px; color: var(--text); }
.stat-value.green { color: var(--green); }
.stat-value.yellow { color: var(--yellow); }
.stat-value.red { color: var(--red); }

.latency-bar-section { display: flex; flex-direction: column; gap: 5px; }
.bar-label { font-size: 10px; color: var(--text-dim); }
.bar-track { height: 4px; background: var(--bg-3); border-radius: 2px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 2px; transition: width 0.6s ease; }

.summary { display: flex; align-items: center; gap: 8px; }
.summary-label { font-size: 10px; letter-spacing: 1.5px; color: var(--text-dim); }
.summary-value { font-size: 12px; color: var(--text-muted); }

.loading-state, .error-state {
  display: flex; justify-content: center; padding: 60px 0; color: var(--text-dim);
}
.loading-dots { display: flex; gap: 6px; }
.loading-dots span {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--accent); animation: bounce 1.2s ease infinite;
}
.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes spin { to { transform: rotate(360deg); } }
@keyframes bounce {
  0%, 100% { transform: translateY(0); opacity: 0.4; }
  50% { transform: translateY(-6px); opacity: 1; }
}
</style>