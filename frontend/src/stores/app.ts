import { defineStore } from 'pinia'
import { ref, onUnmounted } from 'vue'
import { api } from '../composables/api'
import type { Stats, FolderItem } from '../types'

export const useAppStore = defineStore('app', () => {
  const stats = ref<Stats | null>(null)
  const folders = ref<FolderItem[]>([])
  const scanning = ref(false)
  const sseConnected = ref(false)
  let eventSource: EventSource | null = null

  async function fetchStats() {
    stats.value = await api.jobs.stats()
  }

  async function fetchFolders() {
    folders.value = await api.folders.list()
  }

  async function addFolder(path: string, recursive = true, faceDetection = true) {
    const folder = await api.folders.add({
      path,
      recursive,
      face_detection_enabled: faceDetection,
    })
    folders.value.push(folder)
    return folder
  }

  async function removeFolder(id: number) {
    await api.folders.remove(id)
    folders.value = folders.value.filter(f => f.id !== id)
  }

  async function triggerScan(folderId?: number) {
    scanning.value = true
    try {
      const result = await api.folders.scan(folderId)
      await fetchStats()
      return result
    } finally {
      scanning.value = false
    }
  }

  function connectSSE() {
    if (eventSource) return
    eventSource = new EventSource('http://localhost:8000/api/jobs/stream')
    eventSource.onopen = () => { sseConnected.value = true }
    eventSource.onmessage = (e) => {
      try {
        const counts = JSON.parse(e.data)
        if (stats.value) {
          stats.value.queued_jobs = counts.queued || 0
          stats.value.running_jobs = counts.running || 0
        }
      } catch { /* ignore parse errors */ }
    }
    eventSource.onerror = () => { sseConnected.value = false }
  }

  function disconnectSSE() {
    eventSource?.close()
    eventSource = null
    sseConnected.value = false
  }

  return {
    stats,
    folders,
    scanning,
    sseConnected,
    fetchStats,
    fetchFolders,
    addFolder,
    removeFolder,
    triggerScan,
    connectSSE,
    disconnectSSE,
  }
})
