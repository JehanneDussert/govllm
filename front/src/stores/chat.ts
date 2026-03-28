import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Message } from '@/api/client'

const GATEWAY_URL = import.meta.env.VITE_GATEWAY_URL ?? 'http://localhost:8001'

export interface ChatMessage extends Message {
  traceId?: string
  question?: string // original input to the judge 
  model?: string // model used for this response 
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const isStreaming = ref(false)
  const currentModel = ref('ollama/qwen2.5:1.5b')
  const lastLatency = ref<number | null>(null)
  const tokensPerSecond = ref<number | null>(null)

  async function sendMessage(content: string) {
    messages.value.push({ role: 'user', content })
    const assistantMsg: ChatMessage = {
      role: 'assistant',
      content: '',
      question: content,
      model: currentModel.value,
    }
    messages.value.push(assistantMsg)
    isStreaming.value = true
    lastLatency.value = null
    tokensPerSecond.value = null

    const startTime = Date.now()
    let tokenCount = 0
    const assistantIndex = messages.value.length - 1

    try {
      const response = await fetch(`${GATEWAY_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: messages.value.slice(0, -1).map((m) => ({ role: m.role, content: m.content })),
          model: currentModel.value,
          stream: true,
        }),
      })

      // Retrieves the trace_id from the headers, if available
      const traceId = response.headers.get('x-trace-id') ?? crypto.randomUUID()
      messages.value[assistantIndex]!.traceId = traceId

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n').filter((l) => l.startsWith('data: '))

        for (const line of lines) {
          const data = line.slice(6)
          if (data === '[DONE]') continue
          try {
            const parsed = JSON.parse(data)
            const delta = parsed.choices?.[0]?.delta?.content ?? ''
            if (delta) {
              messages.value[assistantIndex]!.content += delta
              tokenCount++
              const elapsed = (Date.now() - startTime) / 1000
              tokensPerSecond.value = Math.round(tokenCount / elapsed)
            }
          } catch {}
        }
      }
    } finally {
      isStreaming.value = false
      lastLatency.value = Date.now() - startTime
    }
  }

  function clearMessages() {
    messages.value = []
  }

  return {
    messages,
    isStreaming,
    currentModel,
    lastLatency,
    tokensPerSecond,
    sendMessage,
    clearMessages,
  }
})
