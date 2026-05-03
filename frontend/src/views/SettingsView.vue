<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useAppStore } from '../stores/app'
import { useGalleryStore } from '../stores/gallery'
import type { ScanResponse } from '../types'

const appStore = useAppStore()
const gallery = useGalleryStore()

const newFolderPath = ref('')
const newFolderRecursive = ref(true)
const newFolderFaceDetection = ref(true)
const addingFolder = ref(false)
const folderError = ref('')
const lastScanResult = ref<ScanResponse | null>(null)

onMounted(async () => {
  await appStore.fetchFolders()
  await appStore.fetchStats()
})

async function handleAddFolder() {
  if (!newFolderPath.value.trim()) return
  folderError.value = ''
  addingFolder.value = true
  try {
    await appStore.addFolder(
      newFolderPath.value.trim(),
      newFolderRecursive.value,
      newFolderFaceDetection.value,
    )
    newFolderPath.value = ''
    await appStore.fetchStats()
  } catch (e: any) {
    folderError.value = e.message || 'Failed to add folder'
  } finally {
    addingFolder.value = false
  }
}

async function handleRemoveFolder(id: number) {
  await appStore.removeFolder(id)
  await appStore.fetchStats()
}

async function handleScanAll() {
  lastScanResult.value = (await appStore.triggerScan()) ?? null
  await appStore.fetchStats()
  // Refresh gallery if on that page
  await gallery.fetchImages(true)
}

async function handleScanFolder(id: number) {
  lastScanResult.value = (await appStore.triggerScan(id)) ?? null
  await appStore.fetchStats()
}
</script>

<template>
  <div class="p-6 max-w-4xl space-y-8">
    <div>
      <h2 class="text-2xl font-bold text-surface-100">Settings</h2>
      <p class="text-sm text-surface-500 mt-0.5">Manage image folders and indexing</p>
    </div>

    <!-- Stats cards -->
    <div v-if="appStore.stats" class="grid grid-cols-2 sm:grid-cols-4 gap-4">
      <div class="glass-panel-light p-4">
        <p class="text-2xl font-bold text-brand-400">{{ appStore.stats.total_images }}</p>
        <p class="text-xs text-surface-500 mt-1">Total Images</p>
      </div>
      <div class="glass-panel-light p-4">
        <p class="text-2xl font-bold text-emerald-400">{{ appStore.stats.indexed_images }}</p>
        <p class="text-xs text-surface-500 mt-1">Indexed</p>
      </div>
      <div class="glass-panel-light p-4">
        <p class="text-2xl font-bold text-amber-400">{{ appStore.stats.pending_images }}</p>
        <p class="text-xs text-surface-500 mt-1">Pending</p>
      </div>
      <div class="glass-panel-light p-4">
        <p class="text-2xl font-bold text-red-400">{{ appStore.stats.error_images }}</p>
        <p class="text-xs text-surface-500 mt-1">Errors</p>
      </div>
    </div>

    <!-- Add folder -->
    <div class="glass-panel p-6 space-y-4">
      <h3 class="text-lg font-semibold text-surface-200">Add Image Folder</h3>

      <div class="flex gap-3">
        <input
          v-model="newFolderPath"
          type="text"
          placeholder="Enter absolute folder path, e.g. C:\Users\Photos"
          class="input-field flex-1"
          @keydown.enter="handleAddFolder"
        />
        <button
          class="btn-primary flex-shrink-0"
          :disabled="addingFolder || !newFolderPath.trim()"
          @click="handleAddFolder"
        >
          {{ addingFolder ? 'Adding...' : '+ Add' }}
        </button>
      </div>

      <div class="flex items-center gap-6 text-sm">
        <label class="flex items-center gap-2 text-surface-400 cursor-pointer">
          <input v-model="newFolderRecursive" type="checkbox" class="rounded border-surface-600 bg-surface-800 text-brand-500 focus:ring-brand-500/50" />
          Scan subfolders
        </label>
        <label class="flex items-center gap-2 text-surface-400 cursor-pointer">
          <input v-model="newFolderFaceDetection" type="checkbox" class="rounded border-surface-600 bg-surface-800 text-brand-500 focus:ring-brand-500/50" />
          Face detection (M4)
        </label>
      </div>

      <p v-if="folderError" class="text-sm text-red-400">{{ folderError }}</p>
    </div>

    <!-- Registered folders -->
    <div class="glass-panel p-6 space-y-4">
      <div class="flex items-center justify-between">
        <h3 class="text-lg font-semibold text-surface-200">Registered Folders</h3>
        <button
          class="btn-primary text-sm"
          :disabled="appStore.scanning || appStore.folders.length === 0"
          @click="handleScanAll"
        >
          {{ appStore.scanning ? 'Scanning...' : '🔍 Scan All' }}
        </button>
      </div>

      <div v-if="appStore.folders.length === 0" class="text-sm text-surface-500 py-4 text-center">
        No folders registered yet. Add one above to get started.
      </div>

      <div v-else class="divide-y divide-surface-700/50">
        <div
          v-for="folder in appStore.folders"
          :key="folder.id"
          class="flex items-center justify-between py-3 group"
        >
          <div class="min-w-0 flex-1">
            <p class="text-sm font-medium text-surface-200 truncate">{{ folder.path }}</p>
            <div class="flex items-center gap-3 mt-1 text-xs text-surface-500">
              <span v-if="folder.recursive">📂 Recursive</span>
              <span v-if="folder.face_detection_enabled">👤 Faces</span>
              <span v-if="folder.last_scanned">
                Last scanned: {{ new Date(folder.last_scanned).toLocaleString() }}
              </span>
              <span v-else>Never scanned</span>
            </div>
          </div>
          <div class="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              class="btn-ghost text-xs"
              @click="handleScanFolder(folder.id)"
            >
              🔍 Scan
            </button>
            <button
              class="btn-ghost text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10"
              @click="handleRemoveFolder(folder.id)"
            >
              🗑 Remove
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Last scan result -->
    <div v-if="lastScanResult" class="glass-panel-light p-4 animate-slide-up">
      <h4 class="text-sm font-semibold text-surface-300 mb-2">Last Scan Result</h4>
      <div class="flex gap-4 text-sm">
        <span class="text-emerald-400">+{{ lastScanResult.new_images }} new</span>
        <span class="text-amber-400">~{{ lastScanResult.modified_images }} modified</span>
        <span class="text-red-400">-{{ lastScanResult.deleted_images }} deleted</span>
        <span class="text-brand-400">{{ lastScanResult.jobs_created }} jobs queued</span>
      </div>
    </div>
  </div>
</template>
