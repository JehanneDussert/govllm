<!--
  SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
  SPDX-License-Identifier: EUPL-1.2
-->

<script setup lang="ts">
// Imports
import { ref, nextTick, watch, onMounted } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useJudgeStore } from '@/stores/judge'
import MessageScore from '@/components/MessageScore.vue'
import { api } from '@/api/client'
import type { RoutingResult } from '@/api/client'
import { modelShortName } from '@/utils/model'

// Stores
const store = useChatStore()
const judgeStore = useJudgeStore()

// Reactive state
const input = ref('')
const messagesEl = ref<HTMLElement>()
const inputEl = ref<HTMLTextAreaElement>()

// Routing
const routing = ref<RoutingResult | null>(null)
const routingExpanded = ref(false)
const autoRoute = ref(true)

async function fetchRouting(applyModel = true) {
  try {
    const res = await api.getRouting()
    routing.value = res.data
    if (!applyModel || !autoRoute.value) return
    if (res.data?.recommended) {
      const recommended = res.data.models.find((m) => m.model === res.data.recommended)
      if (!recommended || recommended.meets_threshold !== false) {
        store.currentModel = res.data.recommended
      } else {
        const firstValid = res.data.models.find((m) => m.meets_threshold === true)
        if (firstValid) store.currentModel = firstValid.model
      }
    }
  } catch {}
}

function selectModel(model: string) {
  autoRoute.value = false
  store.currentModel = model
  routingExpanded.value = false
}

function toggleAutoRoute() {
  autoRoute.value = !autoRoute.value
  if (autoRoute.value) fetchRouting(true)
}

onMounted(async () => {
  await judgeStore.fetchConfig()
  await fetchRouting()
})

// Refetch routing when profile or use case changes
watch(() => judgeStore.config?.active_profile_id, fetchRouting)
watch(() => judgeStore.config?.active_use_case_id, fetchRouting)

async function send() {
  if (!input.value.trim() || store.isStreaming) return
  if (autoRoute.value) await fetchRouting(true)
  const msg = input.value.trim()
  input.value = ''
  if (inputEl.value) {
    inputEl.value.style.height = 'auto'
  }
  await store.sendMessage(msg)
}

function autoResize(e: Event) {
  const el = e.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 200) + 'px'
}

watch(
  () => store.messages.length,
  async () => {
    await nextTick()
    messagesEl.value?.scrollTo({ top: messagesEl.value.scrollHeight, behavior: 'smooth' })
  },
)
</script>

<template>
  <div class="chat-view">
    <div class="chat-header">
      <div class="header-top">
        <div class="header-left">
          <h1 class="page-title">Chat</h1>
        </div>
        <div class="header-right">
          <span v-if="judgeStore.config?.active_profile_id" class="profile-badge">
            {{
              judgeStore.config.profiles.find((p) => p.id === judgeStore.config!.active_profile_id)
                ?.label ?? judgeStore.config.active_profile_id
            }}
          </span>
          <span v-if="judgeStore.config?.active_use_case_id" class="usecase-badge">
            {{
              judgeStore.config.use_cases.find(
                (u) => u.id === judgeStore.config!.active_use_case_id,
              )?.label ?? judgeStore.config.active_use_case_id
            }}
          </span>
        </div>
      </div>

      <!-- Routing bar -->
      <div class="routing-bar">
        <div class="routing-bar-left" @click="routingExpanded = !routingExpanded" style="flex:1; cursor:pointer">
          <span class="routing-label">ROUTING</span>
          <button
            class="auto-route-toggle"
            :class="{ active: autoRoute }"
            @click.stop="toggleAutoRoute"
            :title="autoRoute ? 'Auto-routing ON — click to switch to manual' : 'Manual mode — click to enable auto-routing'"
          >
            {{ autoRoute ? 'AUTO' : 'MANUAL' }}
          </button>
          <span v-if="autoRoute && judgeStore.config?.routing_strategy" class="routing-strategy">
            {{ judgeStore.config.routing_strategy.replace('_', ' ') }}
          </span>
          <span class="routing-sep" v-if="autoRoute && judgeStore.config?.routing_strategy">·</span>
          <span class="routing-model">{{ modelShortName(store.currentModel) }}</span>
          <span v-if="routing?.models[0]?.avg_score != null" class="routing-score">
            {{
              routing.models.find((m) => m.model === store.currentModel)?.avg_score?.toFixed(2) ??
              '—'
            }}
          </span>
          <span v-else class="routing-score-empty">no data yet</span>
          <span class="routing-reason" v-if="autoRoute && routing?.recommended === store.currentModel"
            >— best for this profile + use case</span
          >
        </div>
        <span class="routing-toggle" @click="routingExpanded = !routingExpanded" style="cursor:pointer">{{ routingExpanded ? 'collapse ↑' : 'show all ↓' }}</span>
      </div>

      <!-- Scoreboard expanded -->
      <div v-if="routingExpanded" class="routing-scoreboard">
        <div class="scoreboard-label">
          MODEL SCORES ·
          {{ judgeStore.config?.active_profile_id?.toUpperCase().replace('_', ' ') }} ·
          {{ judgeStore.config?.active_use_case_id?.toUpperCase() }}
          <span v-if="routing?.min_threshold" class="threshold-label"
            >· min {{ routing.min_threshold.toFixed(2) }}</span
          >
        </div>
        <div class="scoreboard-grid">
          <div
            v-for="(m, i) in routing?.models ?? []"
            :key="m.model"
            class="score-card"
            :class="{
              winner: i === 0 && m.avg_score !== null && m.meets_threshold !== false,
              selected: store.currentModel === m.model,
              'below-threshold': m.meets_threshold === false,
            }"
          >
            <div class="score-card-badge">
              {{ i === 0 && m.avg_score !== null ? 'RECOMMENDED' : 'model' }}
            </div>
            <div class="score-card-name">{{ modelShortName(m.model) }}</div>
            <div class="score-card-avg" :class="{ 'score-na': m.avg_score === null }">
              {{ m.avg_score !== null ? m.avg_score.toFixed(2) : '—' }}
            </div>
            <div class="score-card-criteria">
              <div
                v-for="c in routing?.active_criteria.slice(0, 3)"
                :key="c.id"
                class="criterion-row"
              >
                <span class="criterion-name">{{ c.label.toLowerCase().slice(0, 10) }}</span>
                <span class="criterion-val">{{
                  m.criteria_scores[c.id] != null ? m.criteria_scores[c.id]!.toFixed(2) : '—'
                }}</span>
              </div>
            </div>
            <button
              class="score-card-btn"
              :class="{ 'btn-recommended': i === 0 && m.avg_score !== null }"
              @click.stop="selectModel(m.model)"
            >
              {{
                store.currentModel === m.model
                  ? '✓ selected'
                  : i === 0 && m.avg_score !== null
                    ? 'use this model'
                    : 'select'
              }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="messages" ref="messagesEl">
      <div v-if="!store.messages.length" class="empty-state">
        <div class="empty-icon">◈</div>
        <p>Send a message to start monitoring</p>
        <p class="empty-sub">Responses will be traced in Langfuse and scored by the local judge</p>
      </div>

      <template v-for="(msg, i) in store.messages" :key="i">
        <div class="message" :class="msg.role">
          <div class="message-role">{{ msg.role }}</div>
          <div class="message-content">
            <span
              v-if="
                msg.role === 'assistant' && store.isStreaming && i === store.messages.length - 1
              "
            >
              {{ msg.content }}<span class="cursor" />
            </span>
            <span v-else>{{ msg.content }}</span>
          </div>
        </div>

        <!-- Async governance score badge below each completed assistant message -->
        <!-- stable key = traceId to avoid component remount -->
        <MessageScore
          v-if="
            msg.role === 'assistant' &&
            msg.traceId &&
            msg.content &&
            (!store.isStreaming || i < store.messages.length - 1)
          "
          :key="msg.traceId"
          :trace-id="msg.traceId"
          :model="msg.model ?? store.currentModel"
          :question="msg.question ?? ''"
          :answer="msg.content"
        />
      </template>
    </div>

    <div class="input-area">
      <div class="input-wrapper">
        <textarea
          v-model="input"
          class="chat-input"
          placeholder="Ask something..."
          rows="1"
          @keydown.enter.exact.prevent="send"
          @input="autoResize"
          ref="inputEl"
          :disabled="store.isStreaming"
        />
        <button class="send-btn" @click="send" :disabled="store.isStreaming || !input.trim()">
          <span v-if="store.isStreaming" class="streaming-indicator">▪▪▪</span>
          <span v-else>↑</span>
        </button>
      </div>
      <div class="input-hint">↵ send · model: {{ store.currentModel }}</div>
    </div>
  </div>
</template>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.chat-header {
  display: flex;
  flex-direction: column;
  border-bottom: 1px solid var(--border);
  background: var(--bg-2);
  flex-shrink: 0;
}

.header-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 28px 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.profile-badge {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 20px;
  background: rgba(0, 229, 255, 0.1);
  color: var(--accent);
  border: 1px solid rgba(0, 229, 255, 0.2);
}
.usecase-badge {
  font-size: 11px;
  color: var(--text-dim);
}

/* Routing bar */
.routing-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 28px;
  background: var(--bg-3);
  border-top: 1px solid var(--border);
  user-select: none;
  transition: background 0.15s;
}
.routing-bar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.routing-bar-left:hover {
  background: none;
}

.auto-route-toggle {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.8px;
  padding: 2px 7px;
  border-radius: 20px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
  transition: all 0.15s;
}
.auto-route-toggle.active {
  border-color: var(--accent);
  color: var(--accent);
  background: rgba(0, 229, 255, 0.08);
}
.auto-route-toggle:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.routing-strategy {
  font-size: 10px;
  color: var(--text-dim);
  font-style: italic;
}
.routing-sep {
  color: var(--text-dim);
  font-size: 10px;
}
.routing-label {
  font-size: 10px;
  letter-spacing: 0.06em;
  color: var(--text-dim);
}
.routing-model {
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
}
.routing-score {
  font-size: 11px;
  color: var(--green);
}
.routing-score-empty {
  font-size: 11px;
  color: var(--text-dim);
  font-style: italic;
}
.routing-reason {
  font-size: 11px;
  color: var(--text-dim);
}
.routing-toggle {
  font-size: 11px;
  color: var(--text-dim);
}

/* Scoreboard */
.routing-scoreboard {
  background: var(--bg-3);
  border-top: 1px solid var(--border);
  padding: 10px 28px 14px;
}
.scoreboard-label {
  font-size: 10px;
  letter-spacing: 0.06em;
  color: var(--text-dim);
  margin-bottom: 10px;
}
.scoreboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 8px;
}
.score-card {
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  transition: border-color 0.15s;
}
.score-card.winner {
  border-color: var(--green);
  background: rgba(63, 185, 80, 0.06);
}
.score-card.below-threshold {
  opacity: 0.4;
  pointer-events: none;
}
.threshold-label {
  color: var(--red);
  margin-left: 4px;
}
.score-card.selected {
  border-color: var(--accent);
}
.score-card-badge {
  font-size: 9px;
  letter-spacing: 0.06em;
  color: var(--text-dim);
}
.score-card.winner .score-card-badge {
  color: var(--green);
}
.score-card-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
}
.score-card-avg {
  font-size: 18px;
  font-weight: 500;
  color: var(--text-dim);
}
.score-card.winner .score-card-avg {
  color: var(--green);
}
.score-na {
  color: var(--text-dim);
  opacity: 0.5;
}
.score-card-criteria {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 4px;
}
.criterion-row {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
}
.criterion-name {
  color: var(--text-dim);
}
.criterion-val {
  color: var(--text);
}
.score-card-btn {
  margin-top: 6px;
  width: 100%;
  font-size: 11px;
  padding: 4px;
  background: transparent;
  color: var(--text-dim);
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}
.score-card-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.score-card-btn.btn-recommended {
  background: rgba(63, 185, 80, 0.1);
  color: var(--green);
  border-color: rgba(63, 185, 80, 0.3);
}

.page-title {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
}

.model-select {
  background: var(--bg-3);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--accent);
  font-family: var(--font-mono);
  font-size: 12px;
  padding: 5px 10px;
  cursor: pointer;
  outline: none;
}
.model-select:focus {
  border-color: var(--accent);
}

.header-stats {
  display: flex;
  gap: 8px;
}

.stat-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--bg-3);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 4px 10px;
  font-size: 11px;
}
.stat-label {
  color: var(--text-dim);
}
.stat-value {
  color: var(--text);
}
.stat-value.accent {
  color: var(--accent);
}
.stat-value.green {
  color: var(--green);
}
.stat-value.yellow {
  color: var(--yellow);
}
.stat-value.red {
  color: var(--red);
}

.clear-btn {
  background: none;
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 11px;
  padding: 5px 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.clear-btn:hover {
  border-color: var(--red);
  color: var(--red);
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 28px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.empty-state {
  margin: auto;
  text-align: center;
  color: var(--text-dim);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.empty-icon {
  font-size: 32px;
  color: var(--accent);
  opacity: 0.4;
  margin-bottom: 8px;
}
.empty-sub {
  font-size: 11px;
  color: var(--text-dim);
}

.message {
  display: flex;
  gap: 16px;
  animation: fadeIn 0.2s ease;
  margin-top: 16px;
}
.message.user {
  flex-direction: row-reverse;
}

.message-role {
  font-size: 10px;
  letter-spacing: 1px;
  color: var(--text-dim);
  padding-top: 4px;
  width: 60px;
  flex-shrink: 0;
  text-align: right;
}
.message.user .message-role {
  text-align: left;
  color: var(--accent);
  opacity: 0.7;
}

.message-content {
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
  line-height: 1.6;
  max-width: 680px;
  white-space: pre-wrap;
  word-break: break-word;
}
.message.user .message-content {
  background: var(--accent-dim);
  border-color: rgba(0, 229, 255, 0.2);
}

.cursor {
  display: inline-block;
  width: 8px;
  height: 14px;
  background: var(--accent);
  margin-left: 2px;
  vertical-align: middle;
  animation: blink 1s step-end infinite;
}

.input-area {
  padding: 20px 28px 24px;
  border-top: 1px solid var(--border);
  background: var(--bg-2);
  flex-shrink: 0;
}

.input-wrapper {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.chat-input {
  flex: 1;
  background: var(--bg-3);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 13px;
  padding: 12px 16px;
  resize: none;
  outline: none;
  line-height: 1.5;
  transition: border-color 0.15s;
}
.chat-input:focus {
  border-color: var(--accent);
}
.chat-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.chat-input::placeholder {
  color: var(--text-dim);
}

.send-btn {
  width: 40px;
  height: 40px;
  background: var(--accent);
  border: none;
  border-radius: 8px;
  color: var(--bg);
  font-size: 16px;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
}
.send-btn:hover:not(:disabled) {
  background: #33eaff;
}
.send-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.streaming-indicator {
  font-size: 10px;
  letter-spacing: 2px;
  animation: pulse 1s ease infinite;
}

.input-hint {
  margin-top: 6px;
  font-size: 10px;
  color: var(--text-dim);
  letter-spacing: 0.3px;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
@keyframes blink {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0;
  }
}
@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.4;
  }
}
</style>
