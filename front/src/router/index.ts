import { createRouter, createWebHistory } from 'vue-router'
import ChatView from '@/views/ChatView.vue'

export default createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', component: ChatView },
    { path: '/metrics', component: () => import('@/views/MetricsView.vue') },
    { path: '/traces', component: () => import('@/views/TracesView.vue') },
    { path: '/ab', component: () => import('@/views/ABTestView.vue') },
    { path: '/settings', component: () => import('@/views/SettingsView.vue') },
    { path: '/matrix', component: () => import('@/views/MatrixView.vue') },
  ],
})
