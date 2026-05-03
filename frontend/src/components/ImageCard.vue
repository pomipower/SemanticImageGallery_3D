<script setup lang="ts">
import { computed } from 'vue'
import { api } from '../composables/api'
import type { ImageItem } from '../types'

const props = defineProps<{
  image: ImageItem
}>()

const emit = defineEmits<{
  click: [image: ImageItem]
}>()

const thumbUrl = computed(() => api.images.thumbnailUrl(props.image.id))
const isIndexed = computed(() => props.image.status === 'indexed')
const isPending = computed(() => props.image.status === 'pending' || props.image.status === 'processing')

const dimensions = computed(() => {
  if (props.image.width && props.image.height) {
    return `${props.image.width}×${props.image.height}`
  }
  return null
})

const fileName = computed(() => {
  const parts = props.image.file_path.replace(/\\/g, '/').split('/')
  return parts[parts.length - 1]
})
</script>

<template>
  <div
    class="group relative rounded-xl overflow-hidden cursor-pointer
           bg-surface-800 border border-surface-700/40
           hover:border-brand-500/50 hover:shadow-lg hover:shadow-brand-500/10
           transition-all duration-300 ease-out hover:-translate-y-0.5"
    @click="emit('click', image)"
  >
    <!-- Thumbnail -->
    <div class="aspect-square overflow-hidden bg-surface-900">
      <img
        v-if="isIndexed"
        :src="thumbUrl"
        :alt="fileName"
        loading="lazy"
        class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
      />
      <!-- Pending placeholder -->
      <div v-else class="w-full h-full flex items-center justify-center">
        <div v-if="isPending" class="text-center">
          <div class="w-8 h-8 mx-auto mb-2 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin"></div>
          <span class="text-xs text-surface-500">Processing...</span>
        </div>
        <div v-else class="text-center">
          <span class="text-2xl opacity-30">🖼️</span>
          <p class="text-xs text-surface-600 mt-1">{{ image.status }}</p>
        </div>
      </div>
    </div>

    <!-- Hover overlay -->
    <div
      class="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent
             opacity-0 group-hover:opacity-100 transition-opacity duration-300
             flex flex-col justify-end p-3"
    >
      <p class="text-xs font-medium text-white truncate">{{ fileName }}</p>
      <p v-if="dimensions" class="text-xs text-surface-300">{{ dimensions }}</p>
    </div>

    <!-- Status badge -->
    <div class="absolute top-2 right-2">
      <span v-if="isPending" class="badge-warning text-[10px]">Pending</span>
      <span v-else-if="image.status === 'error'" class="badge-error text-[10px]">Error</span>
    </div>
  </div>
</template>
