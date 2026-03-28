<script setup lang="ts">
  import { ref, computed, onMounted } from 'vue'
  import { api } from '@/api/client'
  import type { ABTestResponse } from '@/api/client'
  import { useIntervalFn } from '@vueuse/core'

  const data = ref<ABTestResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const lastUpdated = ref<string | null>(null)

  async function refresh() {
    loading.value = true
    error.value = null
    try {
      const res = await api.abResults()
      data.value = res.data
      lastUpdated.value = new Date().toLocaleTimeString()
    } catch {
      error.value = 'Failed to fetch A/B results'
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

  function scoreClass(score: number) {
    if (score >= 0.7) return 'green'
    if (score >= 0.4) return 'yellow'
    return 'red'
  }

  function latencyBarWidth(ms: number) {
    if (!data.value) return 0
    const max = Math.max(data.value.model_a.avg_latency_ms, data.value.model_b.avg_latency_ms)
    if (max === 0) return 0
    return Math.round((ms / max) * 100)
  }

  const winnerReason = computed(() => {
    if (!data.value?.winner) return ''
    const winner =
      data.value.winner === data.value.model_a.model ? data.value.model_a : data.value.model_b
    const loser =
      data.value.winner === data.value.model_a.model ? data.value.model_b : data.value.model_a

    if (winner.avg_eval_score && loser.avg_eval_score) {
      return `better eval score (${winner.avg_eval_score.toFixed(3)} vs ${loser.avg_eval_score.toFixed(3)})`
    }
    return `lower latency (${winner.avg_latency_ms.toFixed(1)}ms vs ${loser.avg_latency_ms.toFixed(1)}ms)`
  })

  onMounted(refresh)
  useIntervalFn(refresh, 30000)
</script>

<template>
  <div class="ab-view">
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

    <div v-else-if="data" class="ab-content">
      <!-- Winner banner -->
      <div v-if="data.winner" class="winner-banner">
        <span class="winner-label">WINNER</span>
        <span class="winner-model">{{ shortName(data.winner) }}</span>
        <span class="winner-reason">{{ winnerReason }}</span>
      </div>
      <div v-else class="no-winner-banner">
        <span>Not enough data to determine a winner — need at least 3 samples per model</span>
      </div>

      <!-- Model comparison -->
      <div class="model-comparison">
        <div
          v-for="(model, key) in { a: data.model_a, b: data.model_b }"
          :key="key"
          class="model-panel"
          :class="{
            winner: data.winner === model.model,
            loser: data.winner && data.winner !== model.model,
          }"
        >
          <div class="panel-header">
            <div class="panel-model">
              <span class="model-letter">{{ key.toUpperCase() }}</span>
              <span class="model-name" :class="key === 'a' ? 'cyan' : 'purple'">
                {{ shortName(model.model) }}
              </span>
            </div>
            <div v-if="data.winner === model.model" class="winner-badge">✓ winner</div>
          </div>

          <div class="panel-stats">
            <div class="panel-stat">
              <div class="ps-label">SAMPLES</div>
              <div class="ps-value">{{ model.sample_size }}</div>
            </div>
            <div class="panel-stat">
              <div class="ps-label">AVG LATENCY</div>
              <div class="ps-value" :class="latencyClass(model.avg_latency_ms)">
                {{ model.avg_latency_ms.toFixed(1) }}ms
              </div>
            </div>
            <div class="panel-stat">
              <div class="ps-label">ERROR RATE</div>
              <div class="ps-value" :class="errorClass(model.error_rate)">
                {{ (model.error_rate * 100).toFixed(1) }}%
              </div>
            </div>
            <div class="panel-stat">
              <div class="ps-label">EVAL SCORE</div>
              <div
                class="ps-value"
                :class="model.avg_eval_score ? scoreClass(model.avg_eval_score) : ''"
              >
                {{ model.avg_eval_score?.toFixed(3) ?? '—' }}
              </div>
            </div>
            <div class="panel-stat">
              <div class="ps-label">AVG TOKENS</div>
              <div class="ps-value">{{ model.avg_tokens.toFixed(0) || '—' }}</div>
            </div>
          </div>

          <!-- Latency bar -->
          <div class="latency-bar-section">
            <div class="bar-label">latency vs other</div>
            <div class="bar-track">
              <div
                class="bar-fill"
                :class="key === 'a' ? 'fill-cyan' : 'fill-purple'"
                :style="{ width: latencyBarWidth(model.avg_latency_ms) + '%' }"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- Summary -->
      <div class="summary-section">
        <div class="section-title">WINDOW</div>
        <div class="summary-text">{{ data.window }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
  .ab-view {
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

  /* Winner banner */
  .winner-banner {
    display: flex;
    align-items: center;
    gap: 12px;
    background: rgba(63, 185, 80, 0.08);
    border: 1px solid rgba(63, 185, 80, 0.3);
    border-radius: 8px;
    padding: 14px 20px;
    margin-bottom: 12px;
  }

  .winner-label {
    font-size: 10px;
    letter-spacing: 1.5px;
    color: var(--green);
  }

  .winner-model {
    font-family: var(--font-display);
    font-size: 16px;
    font-weight: 700;
    color: var(--green);
  }

  .winner-reason {
    font-size: 12px;
    color: var(--text-muted);
  }

  .no-winner-banner {
    background: var(--bg-2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 20px;
    font-size: 12px;
    color: var(--text-dim);
    margin-bottom: 12px;
  }

  /* Model panels */
  .model-comparison {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }

  .model-panel {
    background: var(--bg-2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 20px;
    transition: border-color 0.2s;
  }

  .model-panel.winner {
    border-color: rgba(63, 185, 80, 0.4);
  }

  .model-panel.loser {
    opacity: 0.7;
  }

  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .panel-model {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .model-letter {
    width: 24px;
    height: 24px;
    background: var(--bg-3);
    border: 1px solid var(--border);
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    color: var(--text-dim);
  }

  .model-name {
    font-family: var(--font-display);
    font-size: 16px;
    font-weight: 600;
  }

  .model-name.cyan {
    color: var(--accent);
  }

  .model-name.purple {
    color: #a78bfa;
  }

  .winner-badge {
    font-size: 10px;
    color: var(--green);
    background: rgba(63, 185, 80, 0.1);
    border: 1px solid rgba(63, 185, 80, 0.3);
    border-radius: 20px;
    padding: 2px 10px;
  }

  .panel-stats {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }

  .panel-stat {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .ps-label {
    font-size: 10px;
    letter-spacing: 0.8px;
    color: var(--text-dim);
  }

  .ps-value {
    font-size: 20px;
    color: var(--text);
  }

  .ps-value.green {
    color: var(--green);
  }

  .ps-value.yellow {
    color: var(--yellow);
  }

  .ps-value.red {
    color: var(--red);
  }

  /* Latency bar */
  .latency-bar-section {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .bar-label {
    font-size: 10px;
    color: var(--text-dim);
  }

  .bar-track {
    height: 4px;
    background: var(--bg-3);
    border-radius: 2px;
    overflow: hidden;
  }

  .bar-fill {
    height: 100%;
    border-radius: 2px;
    transition: width 0.6s ease;
  }

  .fill-cyan {
    background: var(--accent);
  }

  .fill-purple {
    background: #a78bfa;
  }

  /* Summary */
  .summary-section {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-top: 12px;
  }

  .section-title {
    font-size: 10px;
    letter-spacing: 1.5px;
    color: var(--text-dim);
  }

  .summary-text {
    font-size: 12px;
    color: var(--text-muted);
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
