<script setup lang="ts">
  import { ref, onMounted } from 'vue'
  import { api, DEFAULT_MODELS } from '@/api/client'
  import type { TracesResponse, TraceItem } from '@/api/client'

  const data = ref<TracesResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const modelFilter = ref('')
  const limitFilter = ref(50)
  const selected = ref<TraceItem | null>(null)

  async function refresh() {
    loading.value = true
    error.value = null
    try {
      const res = await api.traces(limitFilter.value, modelFilter.value || undefined)
      data.value = res.data
    } catch {
      error.value = 'Failed to fetch traces'
    } finally {
      loading.value = false
    }
  }

  function shortName(model: string) {
    return model.split('/').pop() ?? model
  }

  function formatTime(ts: string) {
    return new Date(ts).toLocaleTimeString('fr-FR', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }

  function modelClass(model: string) {
    const MODEL_COLORS = ['tag-cyan', 'tag-purple', 'tag-green', 'tag-orange']
    const KNOWN = DEFAULT_MODELS
    const idx = KNOWN.indexOf(model)

    return MODEL_COLORS[idx >= 0 ? idx : 0]
  }

  function latencyClass(ms: number) {
    if (ms < 3000) return 'green'
    if (ms < 8000) return 'yellow'

    return 'red'
  }

  function scoreClass(score: number) {
    if (score >= 0.7) return 'green'
    if (score >= 0.4) return 'yellow'

    return 'red'
  }

  onMounted(refresh)
</script>

<template>
  <div class="traces-view">
    <div class="page-header">
      <h1 class="page-title">Traces</h1>
      <div class="filters">
        <select v-model="modelFilter" class="filter-select" @change="refresh">
          <option value="">all models</option>
          <option value="ollama/qwen2.5:1.5b">qwen2.5 1.5b</option>
          <option value="ollama/gemma3:1b">gemma3 1b</option>
          <option value="ollama/llama3.2:3b">llama3.2 3b</option>
          <option value="ollama/deepseek-r1:1.5b">deepseek-r1 1.5b</option>
        </select>
        <select v-model="limitFilter" class="filter-select" @change="refresh">
          <option :value="20">20</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
        </select>
        <button class="refresh-btn" @click="refresh" :class="{ spinning: loading }">↻</button>
      </div>
    </div>

    <div v-if="loading && !data" class="loading-state">
      <div class="loading-dots"><span /><span /><span /></div>
    </div>

    <div v-else-if="error" class="error-state">{{ error }}</div>

    <div v-else-if="data" class="traces-content">
      <div class="table-meta">
        <span class="total">{{ data.total }} traces</span>
      </div>

      <div class="traces-table">
        <div class="table-head">
          <div class="col col-time">TIME</div>
          <div class="col col-model">MODEL</div>
          <div class="col col-latency">LATENCY</div>
          <div class="col col-score">SCORE</div>
          <div class="col col-input">INPUT</div>
          <div class="col col-output">OUTPUT</div>
        </div>

        <div
          v-for="trace in data.traces"
          :key="trace.trace_id"
          class="table-row"
          @click="selected = selected?.trace_id === trace.trace_id ? null : trace"
          :class="{ expanded: selected?.trace_id === trace.trace_id }"
        >
          {{ console.log(trace) }}
          <div class="col col-time">{{ formatTime(trace.timestamp) }}</div>
          <div class="col col-model">
            <span class="model-tag" :class="modelClass(trace.model)">
              {{ shortName(trace.model) }}
            </span>
          </div>
          <div class="col col-latency">
            <span :class="latencyClass(trace.latency_ms * 1000)">
              {{ trace.latency_ms.toFixed(2) }}s
            </span>
          </div>
          <div class="col col-score">
            <span v-if="trace.eval_score !== null" :class="scoreClass(trace.eval_score)">
              {{ trace.eval_score.toFixed(2) }}
            </span>
            <span v-else class="no-score">—</span>
          </div>
          <div class="col col-input col-truncate">{{ trace.input_preview }}</div>
          <div class="col col-output col-truncate">{{ trace.output_preview }}</div>

          <!-- Expanded row -->
          <div v-if="selected?.trace_id === trace.trace_id" class="expanded-content">
            <div class="expanded-section">
              <div class="expanded-label">INPUT</div>
              <div class="expanded-text">{{ trace.input_preview }}</div>
            </div>
            <div class="expanded-section">
              <div class="expanded-label">OUTPUT</div>
              <div class="expanded-text">{{ trace.output_preview }}</div>
            </div>
            <div class="expanded-meta">
              <span>id: {{ trace.trace_id }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
  .traces-view {
    padding: 28px;
    display: flex;
    flex-direction: column;
    gap: 20px;
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

  .filters {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .filter-select {
    background: var(--bg-3);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 11px;
    padding: 5px 10px;
    cursor: pointer;
    outline: none;
  }

  .filter-select:focus {
    border-color: var(--accent);
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

  .table-meta {
    font-size: 11px;
    color: var(--text-dim);
    margin: 24px 0 24px 0;
  }

  /* Table */
  .traces-table {
    background: var(--bg-2);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
  }

  .table-head {
    display: grid;
    grid-template-columns: 80px 90px 80px 60px 1fr 1fr;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-3);
  }

  .table-head .col {
    font-size: 10px;
    letter-spacing: 1px;
    color: var(--text-dim);
  }

  .table-row {
    display: grid;
    grid-template-columns: 80px 90px 80px 60px 1fr 1fr;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
    cursor: pointer;
    transition: background 0.1s;
    align-items: center;
  }

  .table-row:last-child {
    border-bottom: none;
  }
  .table-row:hover {
    background: var(--bg-3);
  }
  .table-row.expanded {
    background: var(--bg-3);
    grid-template-columns: 80px 90px 80px 60px 1fr 1fr;
  }

  .col {
    font-size: 12px;
    color: var(--text-muted);
    overflow: hidden;
  }
  .col-truncate {
    white-space: nowrap;
    text-overflow: ellipsis;
    overflow: hidden;
    padding-right: 12px;
  }

  .model-tag {
    display: inline-block;
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 20px;
    border: 1px solid;
  }

  .tag-cyan {
    color: var(--accent);
    border-color: rgba(0, 229, 255, 0.3);
    background: rgba(0, 229, 255, 0.06);
  }
  .tag-purple {
    color: #a78bfa;
    border-color: rgba(167, 139, 250, 0.3);
    background: rgba(167, 139, 250, 0.06);
  }
  .tag-green {
    color: var(--green);
    border-color: rgba(63, 185, 80, 0.3);
    background: rgba(63, 185, 80, 0.06);
  }
  .tag-orange {
    color: #f0883e;
    border-color: rgba(240, 136, 62, 0.3);
    background: rgba(240, 136, 62, 0.06);
  }

  .green {
    color: var(--green);
  }
  .yellow {
    color: var(--yellow);
  }
  .red {
    color: var(--red);
  }
  .no-score {
    color: var(--text-dim);
  }

  /* Expanded */
  .expanded-content {
    grid-column: 1 / -1;
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 16px 0 8px;
    border-top: 1px solid var(--border);
    margin-top: 8px;
  }

  .expanded-section {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .expanded-label {
    font-size: 10px;
    letter-spacing: 1px;
    color: var(--text-dim);
  }
  .expanded-text {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 12px;
    font-size: 12px;
    color: var(--text);
    line-height: 1.5;
    white-space: pre-wrap;
  }

  .expanded-meta {
    font-size: 10px;
    color: var(--text-dim);
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
