<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { api } from '../composables/api'
import type { ImageItem } from '../types'

const props = defineProps<{
  image: ImageItem
}>()

const emit = defineEmits<{
  close: []
}>()

const fullUrl = computed(() => api.images.fullUrl(props.image.id))
const imageLoaded = ref(false)

const fileName = computed(() => {
  const parts = props.image.file_path.replace(/\\/g, '/').split('/')
  return parts[parts.length - 1]
})

const folderPath = computed(() => {
  const parts = props.image.file_path.replace(/\\/g, '/').split('/')
  return parts.slice(0, -1).join('/')
})

const fileSizeFormatted = computed(() => {
  if (!props.image.file_size) return '—'
  const mb = props.image.file_size / (1024 * 1024)
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${(props.image.file_size / 1024).toFixed(0)} KB`
})

const exifData = computed(() => {
  if (!props.image.exif_json) return null
  try {
    return JSON.parse(props.image.exif_json)
  } catch {
    return null
  }
})

const formatDate = (d: string | null) => {
  if (!d) return '—'
  return new Date(d).toLocaleString()
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}

onMounted(() => window.addEventListener('keydown', handleKeydown))
onUnmounted(() => window.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <Teleport to="body">
    <div
      class="fixed inset-0 z-50 flex items-center justify-center p-4 animate-fade-in"
      @click.self="emit('close')"
    >
      <!-- Backdrop -->
      <div class="absolute inset-0 bg-black/70 backdrop-blur-sm"></div>

      <!-- Modal -->
      <div class="relative w-full max-w-6xl max-h-[90vh] glass-panel flex overflow-hidden animate-slide-up">
        <!-- Image viewer -->
        <div class="flex-1 min-w-0 bg-black flex items-center justify-center p-4">
          <div v-if="!imageLoaded" class="w-10 h-10 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin"></div>
          <img
            :src="fullUrl"
            :alt="fileName"
            class="max-w-full max-h-[80vh] object-contain rounded-lg"
            :class="{ 'opacity-0': !imageLoaded, 'opacity-100 transition-opacity duration-300': imageLoaded }"
            @load="imageLoaded = true"
          />
        </div>

        <!-- Metadata panel -->
        <div class="w-80 flex-shrink-0 border-l border-surface-700/50 overflow-y-auto p-5 space-y-5">
          <!-- Close button -->
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-semibold text-surface-200">Details</h3>
            <button
              class="btn-ghost text-surface-400 hover:text-white"
              @click="emit('close')"
            >
              ✕
            </button>
          </div>

          <!-- Filename -->
          <div>
            <p class="text-xs text-surface-500 mb-1">Filename</p>
            <p class="text-sm font-medium text-surface-200 break-all">{{ fileName }}</p>
          </div>

          <!-- Path -->
          <div>
            <p class="text-xs text-surface-500 mb-1">Location</p>
            <p class="text-xs text-surface-400 break-all">{{ folderPath }}</p>
          </div>

          <!-- Status -->
          <div>
            <p class="text-xs text-surface-500 mb-1">Status</p>
            <span
              :class="[
                image.status === 'indexed' ? 'badge-success' :
                image.status === 'error' ? 'badge-error' :
                'badge-warning'
              ]"
            >
              {{ image.status }}
            </span>
          </div>

          <!-- Dimensions & Size -->
          <div class="grid grid-cols-2 gap-3">
            <div>
              <p class="text-xs text-surface-500 mb-1">Dimensions</p>
              <p class="text-sm text-surface-300">
                {{ image.width && image.height ? `${image.width}×${image.height}` : '—' }}
              </p>
            </div>
            <div>
              <p class="text-xs text-surface-500 mb-1">File Size</p>
              <p class="text-sm text-surface-300">{{ fileSizeFormatted }}</p>
            </div>
            <div>
              <p class="text-xs text-surface-500 mb-1">Format</p>
              <p class="text-sm text-surface-300 uppercase">{{ image.format || '—' }}</p>
            </div>
            <div>
              <p class="text-xs text-surface-500 mb-1">Indexed</p>
              <p class="text-sm text-surface-300">{{ formatDate(image.indexed_at) }}</p>
            </div>
          </div>

          <!-- EXIF -->
          <div v-if="exifData">
            <p class="text-xs text-surface-500 mb-2">EXIF Data</p>
            <div class="space-y-1.5 max-h-60 overflow-y-auto">
              <div
                v-for="(value, key) in exifData"
                :key="String(key)"
                class="flex gap-2 text-xs"
              >
                <span class="text-surface-500 flex-shrink-0 w-28 truncate">{{ key }}</span>
                <span class="text-surface-300 truncate">{{ value }}</span>
              </div>
            </div>
          </div>

          <!-- Error -->
          <div v-if="image.error_msg" class="p-3 rounded-lg bg-red-500/10 border border-red-500/20">
            <p class="text-xs text-red-400">{{ image.error_msg }}</p>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
