// SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
// SPDX-License-Identifier: EUPL-1.2
import { createRouter, createWebHistory } from 'vue-router'
import ChatView from '@/views/ChatView.vue'

export default createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', component: ChatView },
    { path: '/metrics', component: () => import('@/views/MetricsView.vue') },
    { path: '/traces', component: () => import('@/views/TracesView.vue') },
    { path: '/ab', component: () => import('@/views/BenchmarkView.vue') },
    { path: '/settings', component: () => import('@/views/SettingsView.vue') },
    { path: '/matrix', component: () => import('@/views/MatrixView.vue') },
    { path: '/arena', component: () => import('@/views/ArenaView.vue') },
  ],
})
