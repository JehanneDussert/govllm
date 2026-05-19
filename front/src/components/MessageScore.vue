<!--
  SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
  SPDX-License-Identifier: EUPL-1.2
-->
<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from '@/api/client'
import type { EvalResult } from '@/api/client'
import { useJudgeStore } from '@/stores/judge'
import { scoreClass } from '@/utils/score'

const props = defineProps<{
  traceId: string
  model: string
  question: string
  answer: string
}>()

const judgeStore = useJudgeStore()
const result = ref<EvalResult | null>(null)
const state = ref<'evaluating' | 'done' | 'error'>('evaluating')
const visibleScores = computed(() => result.value?.criteria_scores ?? [])
const flaggedCriteria = computed(() => result.value?.criteria_scores.filter((cs) => cs.flag) ?? [])
let pollInterval: ReturnType<typeof setInterval> | null = null

function labelFor(id: string) {
  return judgeStore.config?.criteria.find((c) => c.id === id)?.label ?? id
}

async function triggerAndPoll() {
  // Check if result already exists before triggering evaluation
  try {
    const existing = await api.getEvalResult(props.traceId)
    if (existing.data?.evaluated_at) {
      result.value = existing.data
      state.value = 'done'
      return
    }
  } catch {}

  try {
    await api.triggerEval({
      trace_id: props.traceId,
      model: props.model,
      question: props.question,
      answer: props.answer,
    })
  } catch {
    state.value = 'error'
    return
  }

  // Wait 5 seconds before starting to poll (the judge takes a while)
  await new Promise((resolve) => setTimeout(resolve, 5000))

  // Poll every 3 seconds, up to a maximum of 2 minutes
  let attempts = 0
  pollInterval = setInterval(async () => {
    attempts++
    try {
      const res = await api.getEvalResult(props.traceId)
      // null = not ready yet, continue polling
      // object = result available
      if (res.data && res.data.composite_score !== undefined && res.data.evaluated_at) {
        result.value = res.data
        state.value = 'done'
        clearInterval(pollInterval!)
        return
      }
    } catch {}
    // Timeout after 2 minutes (40 * 3s)
    if (attempts >= 40) {
      state.value = 'error'
      clearInterval(pollInterval!)
    }
  }, 3000)
}

onMounted(async () => {
  if (!judgeStore.config) await judgeStore.fetchConfig()
  triggerAndPoll()
})
onUnmounted(() => {
  if (pollInterval) clearInterval(pollInterval)
})
</script>

<template>
  <div class="message-score" :class="state">
    <template v-if="state === 'evaluating'">
      <span class="eval-dots"><span /><span /><span /></span>
      <span class="eval-label">scoring with local judge...</span>
    </template>

    <template v-else-if="state === 'done' && result">
      <div class="score-composite" :class="scoreClass(result.composite_score)">
        <span class="score-icon">◈</span>
        <span class="score-value">{{ result.composite_score.toFixed(2) }}</span>
      </div>

      <div class="score-criteria">
        <div
          v-for="cs in visibleScores"
          :key="cs.criterion_id"
          class="criterion-pill"
          :class="{ flagged: cs.flag }"
          :title="cs.reason"
        >
          <span class="pill-flag" v-if="cs.flag && scoreClass(cs.score) == 'red'">⚠</span>
          <span class="pill-label">{{ labelFor(cs.criterion_id) }}</span>
          <span class="pill-score" :class="scoreClass(cs.score)">{{ cs.score.toFixed(2) }}</span>
        </div>
      </div>

      <div v-if="flaggedCriteria.length" class="flags">
        <span
          v-for="cs in flaggedCriteria"
          :key="cs.criterion_id"
          class="flag-badge"
          :class="scoreClass(cs.score)"
        >
          <span v-if="scoreClass(cs.score) == 'red'">⚠ </span>
          {{ labelFor(cs.criterion_id) }}: {{ cs.reason }}
        </span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.message-score {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 6px 16px 6px 0;
  margin-left: 76px;
  font-size: 11px;
}

/* Evaluating */
.eval-dots {
  display: flex;
  gap: 3px;
  align-items: center;
}
.eval-dots span {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--text-dim);
  animation: bounce 1.2s ease infinite;
}
.eval-dots span:nth-child(2) {
  animation-delay: 0.2s;
}
.eval-dots span:nth-child(3) {
  animation-delay: 0.4s;
}
.eval-label {
  color: var(--text-dim);
  font-size: 10px;
}

/* Composite score */
.score-composite {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}
.score-icon {
  font-size: 10px;
  opacity: 0.7;
}
.score-value {
  font-weight: 500;
}

/* Criteria pills */
.score-criteria {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.criterion-pill {
  display: flex;
  align-items: center;
  gap: 4px;
  background: var(--bg-3);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 2px 8px;
  font-size: 10px;
  color: var(--text-muted);
}

.criterion-pill.flagged {
  border-color: rgba(248, 81, 73, 0.4);
  background: rgba(248, 81, 73, 0.06);
}

.pill-flag {
  color: var(--red);
  font-size: 9px;
}
.pill-label {
  color: var(--text-dim);
}
.pill-score {
  font-weight: 500;
}

/* Flags */
.flags {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.flag-badge {
  font-size: 10px;
  color: var(--red);
  opacity: 0.8;
}

/* Score colors */
.green {
  color: var(--green);
}
.yellow {
  color: var(--yellow);
}
.red {
  color: var(--red);
}

@keyframes bounce {
  0%,
  100% {
    transform: translateY(0);
    opacity: 0.4;
  }
  50% {
    transform: translateY(-4px);
    opacity: 1;
  }
}
</style>
