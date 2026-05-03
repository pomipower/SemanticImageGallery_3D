<script setup lang="ts">
import { RouterView, RouterLink, useRoute } from 'vue-router'
import { useAppStore } from './stores/app'
import { onMounted, onUnmounted, computed } from 'vue'

const appStore = useAppStore()
const route = useRoute()

const navItems = [
  { path: '/', label: 'Gallery', icon: '🖼️' },
  { path: '/settings', label: 'Settings', icon: '⚙️' },
]

const isActive = (path: string) => route.path === path

onMounted(() => {
  appStore.fetchStats()
  appStore.connectSSE()
})

onUnmounted(() => {
  appStore.disconnectSSE()
})

const workerStatus = computed(() => {
  if (!appStore.stats) return null
  const q = appStore.stats.queued_jobs
  const r = appStore.stats.running_jobs
  if (r > 0) return { text: `Processing ${r} job${r > 1 ? 's' : ''}`, color: 'text-amber-400' }
  if (q > 0) return { text: `${q} queued`, color: 'text-brand-400' }
  return { text: 'Idle', color: 'text-emerald-400' }
})
</script>

<template>
  <div class="flex h-screen overflow-hidden">
    <!-- Sidebar -->
    <aside class="w-64 flex-shrink-0 glass-panel rounded-none border-t-0 border-b-0 border-l-0 flex flex-col">
      <!-- Logo -->
      <div class="p-5 border-b border-surface-700/50">
        <h1 class="text-lg font-bold bg-gradient-to-r from-brand-400 to-brand-600 bg-clip-text text-transparent">
          SemanticGallery
        </h1>
        <p class="text-xs text-surface-500 mt-0.5">AI-Powered Photo System</p>
      </div>

      <!-- Navigation -->
      <nav class="flex-1 p-3 space-y-1">
        <RouterLink
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          :class="[
            'flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 group',
            isActive(item.path)
              ? 'bg-brand-600/20 text-brand-300 border border-brand-500/30'
              : 'text-surface-400 hover:text-surface-200 hover:bg-surface-800/60'
          ]"
        >
          <span class="text-lg">{{ item.icon }}</span>
          <span class="font-medium text-sm">{{ item.label }}</span>
        </RouterLink>
      </nav>

      <!-- Status footer -->
      <div class="p-4 border-t border-surface-700/50">
        <div class="flex items-center gap-2 text-xs">
          <span class="relative flex h-2 w-2">
            <span
              v-if="appStore.stats?.running_jobs"
              class="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"
            ></span>
            <span
              :class="[
                'relative inline-flex rounded-full h-2 w-2',
                appStore.stats?.running_jobs ? 'bg-amber-400' : 'bg-emerald-400'
              ]"
            ></span>
          </span>
          <span :class="workerStatus?.color ?? 'text-surface-500'">
            {{ workerStatus?.text ?? 'Loading...' }}
          </span>
        </div>
        <div v-if="appStore.stats" class="mt-2 text-xs text-surface-500">
          {{ appStore.stats.total_images }} images · {{ appStore.stats.total_folders }} folders
        </div>
      </div>
    </aside>

    <!-- Main content -->
    <main class="flex-1 overflow-y-auto">
      <RouterView />
    </main>
  </div>
</template>
