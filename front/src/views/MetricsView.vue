<!--
  SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
  SPDX-License-Identifier: EUPL-1.2
-->

<script setup lang="ts">
// Imports
import { ref, computed, onMounted } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { api } from '@/api/client'
import type { MetricsResponse } from '@/api/client'
import { useIntervalFn } from '@vueuse/core'
import { modelShortName as shortName } from '@/utils/model'

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent, LegendComponent])

// Constants
const windows = ['1h', '6h', '24h', '7d']
const MODEL_COLORS = ['#00e5ff', '#a78bfa', '#3fb950', '#f0883e']
const COLORS = { axis: '#484f58', grid: '#21262d' }

// Reactive states
const data = ref<MetricsResponse | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const window = ref('24h')
const lastUpdated = ref<string | null>(null)

async function refresh() {
  loading.value = true
  error.value = null
  try {
    const res = await api.metrics(window.value)
    data.value = res.data
    lastUpdated.value = new Date().toLocaleTimeString()
  } catch {
    error.value = 'Failed to fetch metrics — is observability running?'
  } finally {
    loading.value = false
  }
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

const modelColor = (model: string) => {
  const idx = (data.value?.models ?? []).findIndex((m) => m.model === model)
  return MODEL_COLORS[idx % MODEL_COLORS.length] ?? '#00e5ff'
}

const latencyChartOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: {
    trigger: 'axis',
    backgroundColor: '#161b22',
    borderColor: '#30363d',
    textStyle: { color: '#e6edf3', fontFamily: 'DM Mono', fontSize: 12 },
    formatter: (params: { color: string; seriesName: string; value: number }[]) =>
      params
        .map((p) => `<span style="color:${p.color}">●</span> ${p.seriesName}: ${p.value}ms`)
        .join('<br/>'),
  },
  legend: {
    data: data.value?.models.map((m) => shortName(m.model)) ?? [],
    textStyle: { color: '#7d8590', fontFamily: 'DM Mono', fontSize: 11 },
    bottom: 0,
  },
  grid: { top: 16, right: 16, bottom: 40, left: 60 },
  xAxis: {
    type: 'category',
    data: ['p50', 'p95', 'p99'],
    axisLine: { lineStyle: { color: COLORS.grid } },
    axisLabel: { color: COLORS.axis, fontFamily: 'DM Mono', fontSize: 11 },
  },
  yAxis: {
    type: 'value',
    name: 'ms',
    nameTextStyle: { color: COLORS.axis, fontSize: 10 },
    axisLine: { show: false },
    splitLine: { lineStyle: { color: COLORS.grid } },
    axisLabel: { color: COLORS.axis, fontFamily: 'DM Mono', fontSize: 11 },
  },
  series:
    data.value?.models.map((m) => ({
      name: shortName(m.model),
      type: 'bar',
      barMaxWidth: 40,
      data: [m.latency.p50_ms, m.latency.p95_ms, m.latency.p99_ms],
      itemStyle: { color: modelColor(m.model), borderRadius: [3, 3, 0, 0] },
    })) ?? [],
}))

const errorChartOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: {
    trigger: 'axis',
    backgroundColor: '#161b22',
    borderColor: '#30363d',
    textStyle: { color: '#e6edf3', fontFamily: 'DM Mono', fontSize: 12 },
  },
  grid: { top: 16, right: 16, bottom: 40, left: 60 },
  xAxis: {
    type: 'category',
    data: data.value?.models.map((m) => shortName(m.model)) ?? [],
    axisLine: { lineStyle: { color: COLORS.grid } },
    axisLabel: { color: COLORS.axis, fontFamily: 'DM Mono', fontSize: 11 },
  },
  yAxis: {
    type: 'value',
    name: '%',
    nameTextStyle: { color: COLORS.axis, fontSize: 10 },
    axisLine: { show: false },
    splitLine: { lineStyle: { color: COLORS.grid } },
    axisLabel: {
      color: COLORS.axis,
      fontFamily: 'DM Mono',
      fontSize: 11,
      formatter: (v: number) => `${(v * 100).toFixed(0)}%`,
    },
  },
  series: [
    {
      type: 'bar',
      barMaxWidth: 60,
      data:
        data.value?.models.map((m) => ({
          value: m.error_rate,
          itemStyle: {
            color: m.error_rate === 0 ? '#3fb950' : m.error_rate < 0.05 ? '#d29922' : '#f85149',
            borderRadius: [3, 3, 0, 0],
          },
        })) ?? [],
    },
  ],
}))

onMounted(refresh)
useIntervalFn(refresh, 30000)
</script>

<template>
  <div class="metrics-view">
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">Metrics</h1>
        <div class="window-selector">
          <button
            v-for="w in windows"
            :key="w"
            class="window-btn"
            :class="{ active: window === w }"
            @click="
              () => {
                window = w
                refresh()
              }
            "
          >
            {{ w }}
          </button>
        </div>
      </div>
      <div class="header-right">
        <span class="last-updated" v-if="lastUpdated">updated {{ lastUpdated }}</span>
        <button class="refresh-btn" @click="refresh" :class="{ spinning: loading }">↻</button>
      </div>
    </div>

    <div v-if="loading && !data" class="loading-state">
      <div class="loading-dots"><span /><span /><span /></div>
      <p>Fetching metrics...</p>
    </div>

    <div v-else-if="error" class="error-state">
      <p>{{ error }}</p>
    </div>

    <div v-else-if="data" class="metrics-content">
      <!-- Model cards -->
      <div class="model-cards">
        <div v-for="model in data.models" :key="model.model" class="model-card">
          <div class="card-header">
            <span class="model-name">{{ shortName(model.model) }}</span>
            <span class="request-count">{{ model.request_count }} req</span>
          </div>
          <div class="card-stats">
            <div class="stat">
              <span class="stat-label">error rate</span>
              <span class="stat-val" :class="errorClass(model.error_rate)">
                {{ (model.error_rate * 100).toFixed(1) }}%
              </span>
            </div>
            <div class="stat">
              <span class="stat-label">p50</span>
              <span class="stat-val" :class="latencyClass(model.latency.p50_ms)">
                {{ model.latency.p50_ms }}ms
              </span>
            </div>
            <div class="stat">
              <span class="stat-label">p95</span>
              <span class="stat-val" :class="latencyClass(model.latency.p95_ms)">
                {{ model.latency.p95_ms }}ms
              </span>
            </div>
            <div class="stat">
              <span class="stat-label">p99</span>
              <span class="stat-val" :class="latencyClass(model.latency.p99_ms)">
                {{ model.latency.p99_ms }}ms
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Latency chart -->
      <div class="chart-section">
        <div class="section-title">LATENCY DISTRIBUTION</div>
        <div class="chart-container">
          <v-chart :option="latencyChartOption" autoresize class="chart" />
        </div>
      </div>

      <!-- Error rate chart -->
      <div class="chart-section">
        <div class="section-title">ERROR RATE</div>
        <div class="chart-container chart-container--sm">
          <v-chart :option="errorChartOption" autoresize class="chart" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.metrics-view {
  padding: 28px;
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.page-title {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 700;
}

.window-selector {
  display: flex;
  gap: 4px;
}

.window-btn {
  background: none;
  border: 1px solid var(--border);
  border-radius: 5px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 11px;
  padding: 4px 10px;
  cursor: pointer;
  transition: all 0.15s;
}

.window-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.window-btn.active {
  background: var(--accent-dim);
  border-color: var(--accent);
  color: var(--accent);
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

/* Model cards */
.model-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
}

.model-card {
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.model-name {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 600;
  color: var(--accent);
}

.request-count {
  font-size: 11px;
  color: var(--text-dim);
  background: var(--bg-3);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 2px 8px;
}

.card-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.stat-label {
  font-size: 10px;
  color: var(--text-dim);
  letter-spacing: 0.5px;
}
.stat-val {
  font-size: 16px;
  color: var(--text);
}
.stat-val.green {
  color: var(--green);
}
.stat-val.yellow {
  color: var(--yellow);
}
.stat-val.red {
  color: var(--red);
}

/* Charts */
.chart-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 24px 0 24px 0;
}

.section-title {
  font-size: 10px;
  letter-spacing: 1.5px;
  color: var(--text-dim);
}

.chart-container {
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  height: 260px;
}

.chart-container--sm {
  height: 180px;
}
.chart {
  width: 100%;
  height: 100%;
}

/* States */
.loading-state,
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 80px 0;
  color: var(--text-dim);
}
</style>
