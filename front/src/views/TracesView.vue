<!--
  SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
  SPDX-License-Identifier: EUPL-1.2
-->

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '@/api/client'
import type { TraceItem } from '@/api/client'
import { modelShortName as shortName } from '@/utils/model'
import { scoreClass } from '@/utils/score'

const BENCHMARK_MODELS = [
  'ollama/phi4-mini',
  'ollama/gemma3:4b',
  'ollama/mistral:7b',
  'ollama/qwen3:1.7b',
]

const PAGE_SIZE = 20

const allTraces = ref<TraceItem[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const modelFilter = ref('')
const judgeFilter = ref('')
const page = ref(0)
const selected = ref<TraceItem | null>(null)

async function refresh() {
  loading.value = true
  error.value = null
  selected.value = null
  page.value = 0
  try {
    const res = await api.traces(200, modelFilter.value || undefined)
    allTraces.value = res.data.traces
  } catch {
    error.value = 'Failed to fetch traces — is observability running?'
  } finally {
    loading.value = false
  }
}

const filtered = computed(() => {
  if (!judgeFilter.value) return allTraces.value
  return allTraces.value.filter(t => t.judge_model === judgeFilter.value)
})

const totalPages = computed(() => Math.ceil(filtered.value.length / PAGE_SIZE))

const pageTraces = computed(() =>
  filtered.value.slice(page.value * PAGE_SIZE, (page.value + 1) * PAGE_SIZE)
)

function prevPage() {
  if (page.value > 0) page.value--
}
function nextPage() {
  if (page.value < totalPages.value - 1) page.value++
}

function onModelFilterChange() {
  page.value = 0
  refresh()
}
function onJudgeFilterChange() {
  page.value = 0
}

function formatTime(ts: string) {
  return new Date(ts).toLocaleTimeString('fr-FR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

const MODEL_TAG_CLASSES = ['tag-cyan', 'tag-purple', 'tag-green', 'tag-orange']

function modelClass(model: string) {
  const idx = BENCHMARK_MODELS.indexOf(model)
  return MODEL_TAG_CLASSES[idx >= 0 ? idx : 0]
}

function latencyClass(ms: number) {
  if (ms < 3000) return 'green'
  if (ms < 8000) return 'yellow'
  return 'red'
}

function extractText(raw: string): string {
  if (!raw) return '—'
  try {
    const userMatch =
      raw.match(/'role':\s*'user',\s*'content':\s*'([^']+)'/i) ||
      raw.match(/"role":\s*"user",\s*"content":\s*"([^"]+)"/i)
    if (userMatch) return userMatch?.[1] ?? ''
    const contentMatch =
      raw.match(/'content':\s*'([^']{3,120})'/i) || raw.match(/"content":\s*"([^"]{3,120})"/i)
    if (contentMatch) return contentMatch?.[1] ?? ''
  } catch {}
  return raw.slice(0, 120)
}

function extractOutput(raw: string): string {
  if (!raw) return '—'
  try {
    const contentMatch =
      raw.match(/'content':\s*["']([^"']{3,200})/i) || raw.match(/"content":\s*["']([^"']{3,200})/i)
    if (contentMatch && contentMatch[1]) return contentMatch[1].slice(0, 200)
  } catch {}
  return raw.slice(0, 200)
}

onMounted(refresh)
</script>

<template>
  <div class="traces-view">
    <div class="page-header">
      <h1 class="page-title">Traces</h1>
      <div class="filters">
        <select v-model="modelFilter" class="filter-select" @change="onModelFilterChange">
          <option value="">all models</option>
          <option v-for="m in BENCHMARK_MODELS" :key="m" :value="m">
            {{ shortName(m) }}
          </option>
        </select>
        <select v-model="judgeFilter" class="filter-select" @change="onJudgeFilterChange">
          <option value="">all judges</option>
          <option v-for="m in BENCHMARK_MODELS" :key="m" :value="m">
            {{ shortName(m) }}
          </option>
        </select>
        <button class="refresh-btn" @click="refresh" :class="{ spinning: loading }">↻</button>
      </div>
    </div>

    <div v-if="loading && !allTraces.length" class="loading-state">
      <div class="loading-dots"><span /><span /><span /></div>
    </div>

    <div v-else-if="error" class="error-state">{{ error }}</div>

    <div v-else-if="allTraces.length" class="traces-content">
      <div class="table-meta">
        {{ filtered.length }} traces
        <span v-if="totalPages > 1"> · page {{ page + 1 }}/{{ totalPages }}</span>
      </div>

      <div class="traces-table">
        <div class="table-head">
          <div class="col col-time">TIME</div>
          <div class="col col-model">MODEL</div>
          <div class="col col-judge">JUDGE</div>
          <div class="col col-latency">LATENCY</div>
          <div class="col col-score">SCORE</div>
          <div class="col col-input">INPUT</div>
          <div class="col col-output">OUTPUT</div>
        </div>

        <div
          v-for="trace in pageTraces"
          :key="trace.trace_id"
          class="table-row"
          :class="{ expanded: selected?.trace_id === trace.trace_id }"
          @click="selected = selected?.trace_id === trace.trace_id ? null : trace"
        >
          <div class="col col-time">{{ formatTime(trace.timestamp) }}</div>

          <div class="col col-model">
            <span class="model-tag" :class="modelClass(trace.model)">
              {{ shortName(trace.model) }}
            </span>
          </div>

          <div class="col col-judge">
            <span v-if="trace.judge_model" class="model-tag" :class="modelClass(trace.judge_model)">
              {{ shortName(trace.judge_model) }}
            </span>
            <span v-else class="no-score">—</span>
          </div>

          <div class="col col-latency">
            <span class="latency-val" :class="latencyClass(trace.latency_ms * 1000)">
              {{ trace.latency_ms.toFixed(2) }}s
            </span>
          </div>

          <div class="col col-score">
            <span
              v-if="trace.eval_score !== null && trace.eval_score !== undefined"
              class="score-val"
              :class="scoreClass(trace.eval_score)"
            >
              {{ trace.eval_score.toFixed(2) }}
            </span>
            <span v-else class="no-score">—</span>
          </div>

          <div class="col col-input col-truncate">{{ extractText(trace.input_preview) }}</div>
          <div class="col col-output col-truncate">{{ extractOutput(trace.output_preview) }}</div>

          <template v-if="selected?.trace_id === trace.trace_id">
            <div class="expanded-content">
              <div class="expanded-row">
                <div class="expanded-block">
                  <div class="expanded-label">INPUT</div>
                  <div class="expanded-text">{{ extractText(trace.input_preview) }}</div>
                </div>
                <div class="expanded-block">
                  <div class="expanded-label">OUTPUT</div>
                  <div class="expanded-text">{{ extractOutput(trace.output_preview) }}</div>
                </div>
              </div>
              <div class="expanded-meta">
                <span>{{ trace.trace_id }}</span>
                <span v-if="trace.judge_model">· judge {{ shortName(trace.judge_model) }}</span>
                <span v-if="trace.eval_score !== null">· score {{ trace.eval_score?.toFixed(3) }}</span>
                <span>· {{ trace.latency_ms.toFixed(2) }}s</span>
              </div>
            </div>
          </template>
        </div>
      </div>

      <div v-if="totalPages > 1" class="pagination">
        <button class="page-btn" :disabled="page === 0" @click="prevPage">← prev</button>
        <span class="page-info">{{ page + 1 }} / {{ totalPages }}</span>
        <button class="page-btn" :disabled="page === totalPages - 1" @click="nextPage">next →</button>
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
}

.traces-table {
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.table-head {
  display: grid;
  grid-template-columns: 72px 96px 96px 76px 56px 1fr 1fr;
  padding: 8px 16px;
  background: var(--bg-3);
  border-bottom: 1px solid var(--border);
}
.table-head .col {
  font-size: 10px;
  letter-spacing: 1px;
  color: var(--text-dim);
}

.table-row {
  display: grid;
  grid-template-columns: 72px 96px 96px 76px 56px 1fr 1fr;
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
  color: var(--text-dim);
  font-size: 11px;
}

.model-tag {
  display: inline-block;
  font-size: 10px;
  font-family: var(--font-mono);
  padding: 2px 8px;
  border-radius: 20px;
  border: 1px solid;
  white-space: nowrap;
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

.latency-val,
.score-val {
  font-family: var(--font-mono);
  font-size: 12px;
}
.green { color: var(--green); }
.yellow { color: var(--yellow); }
.red { color: var(--red); }
.no-score { color: var(--text-dim); }

.expanded-content {
  grid-column: 1 / -1;
  padding: 14px 0 6px;
  border-top: 1px solid var(--border);
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.expanded-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.expanded-block {
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
  word-break: break-word;
}
.expanded-meta {
  font-size: 10px;
  color: var(--text-dim);
  display: flex;
  gap: 8px;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}
.page-btn {
  background: var(--bg-3);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 11px;
  padding: 5px 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.page-btn:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}
.page-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
.page-info {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-dim);
}

.loading-state,
.error-state {
  display: flex;
  justify-content: center;
  padding: 60px 0;
  color: var(--text-dim);
}
</style>
