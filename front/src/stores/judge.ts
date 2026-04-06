// SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
// SPDX-License-Identifier: EUPL-1.2
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/api/client'
import type { JudgeConfig } from '@/api/client'

export const useJudgeStore = defineStore('judge', () => {
  const config = ref<JudgeConfig | null>(null)
  const loading = ref(false)
  const saving = ref(false)

  async function fetchConfig() {
    loading.value = true
    try {
      const res = await api.getJudgeConfig()
      config.value = res.data
    } finally {
      loading.value = false
    }
  }

  async function saveConfig() {
    if (!config.value) return
    saving.value = true
    try {
      const res = await api.saveJudgeConfig(config.value)
      config.value = res.data
    } finally {
      saving.value = false
    }
  }

  return { config, loading, saving, fetchConfig, saveConfig }
})
