<!--
  SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
  SPDX-License-Identifier: EUPL-1.2
-->

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/api/client'
import { useIntervalFn } from '@vueuse/core'

const health = ref([false, false, false])

async function checkHealth() {
  health.value = await api.health()
}

onMounted(checkHealth)
useIntervalFn(checkHealth, 30000)
</script>

<template>
  <div class="app">
    <nav class="sidebar">
      <div class="sidebar-logo">
        <span class="logo-icon">⬡</span>
        <span class="logo-text">gov<span class="logo-accent">llm</span></span>
      </div>

      <div class="nav-links">
        <RouterLink to="/" class="nav-item">
          <span class="nav-icon">◈</span>
          <span>Chat</span>
        </RouterLink>
        <RouterLink to="/metrics" class="nav-item">
          <span class="nav-icon">◎</span>
          <span>Metrics</span>
        </RouterLink>
        <RouterLink to="/traces" class="nav-item">
          <span class="nav-icon">◫</span>
          <span>Traces</span>
        </RouterLink>
        <RouterLink to="/matrix" class="nav-item">
          <span class="nav-icon">⊞</span>
          <span>Matrix</span>
        </RouterLink>
        <RouterLink to="/arena" class="nav-item">
          <span class="nav-icon">⚔</span>
          <span>Arena</span>
        </RouterLink>
        <RouterLink to="/ab" class="nav-item">
          <span class="nav-icon">⊕</span>
          <span>A/B Test</span>
        </RouterLink>
        <RouterLink to="/settings" class="nav-item">
          <span class="nav-icon">⚙</span>
          <span>Settings</span>
        </RouterLink>
      </div>

      <div class="service-status">
        <div class="status-label">SERVICES</div>
        <div class="status-item" :class="health[0] ? 'up' : 'down'">
          <span class="status-dot" />
          <span>gateway</span>
        </div>
        <div class="status-item" :class="health[1] ? 'up' : 'down'">
          <span class="status-dot" />
          <span>observability</span>
        </div>
        <div class="status-item" :class="health[2] ? 'up' : 'down'">
          <span class="status-dot" />
          <span>evaluation</span>
        </div>
      </div>
    </nav>

    <main class="content">
      <RouterView />
    </main>
  </div>
</template>

<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:ital,wght@0,300;0,400;0,500;1,300&family=Syne:wght@400;600;700;800&display=swap');

*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

:root {
  --bg: #080c10;
  --bg-2: #0d1117;
  --bg-3: #161b22;
  --bg-4: #21262d;
  --border: #30363d;
  --text: #e6edf3;
  --text-muted: #7d8590;
  --text-dim: #484f58;
  --accent: #00e5ff;
  --accent-dim: rgba(0, 229, 255, 0.12);
  --accent-glow: rgba(0, 229, 255, 0.06);
  --green: #3fb950;
  --red: #f85149;
  --yellow: #d29922;
  --font-display: 'Syne', sans-serif;
  --font-mono: 'DM Mono', monospace;
}

html,
body {
  height: 100%;
  background: var(--bg);
  color: var(--text);
}
body {
  font-family: var(--font-mono);
  font-size: 13px;
}

.app {
  display: grid;
  grid-template-columns: 200px 1fr;
  height: 100vh;
  overflow: hidden;
}

/* Sidebar */
.sidebar {
  background: var(--bg-2);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 24px 0;
  gap: 32px;
}

.sidebar-logo {
  padding: 0 20px;
  display: flex;
  align-items: center;
  gap: 10px;
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.5px;
}

.logo-icon {
  color: var(--accent);
  font-size: 20px;
}
.logo-accent {
  color: var(--accent);
}

.nav-links {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 12px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: 6px;
  color: var(--text-muted);
  text-decoration: none;
  font-size: 12px;
  letter-spacing: 0.3px;
  transition: all 0.15s;
}

.nav-item:hover {
  background: var(--bg-3);
  color: var(--text);
}
.nav-item.router-link-active {
  background: var(--accent-dim);
  color: var(--accent);
  border: 1px solid rgba(0, 229, 255, 0.2);
}

.nav-icon {
  font-size: 14px;
  width: 16px;
  text-align: center;
}

/* Service status */
.service-status {
  margin-top: auto;
  padding: 0 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.status-label {
  font-size: 10px;
  letter-spacing: 1.5px;
  color: var(--text-dim);
  margin-bottom: 4px;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--text-muted);
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-dim);
  flex-shrink: 0;
}

.status-item.up .status-dot {
  background: var(--green);
  box-shadow: 0 0 6px var(--green);
}

.status-item.down .status-dot {
  background: var(--red);
}

/* Content */
.content {
  overflow-y: auto;
  background: var(--bg);
}

/* Scrollbar */
::-webkit-scrollbar {
  width: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: var(--text-dim);
}

/* Loading dots — shared across views */
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
