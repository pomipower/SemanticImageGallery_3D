<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useGalleryStore } from '../stores/gallery'
import { useAppStore } from '../stores/app'
import ImageCard from '../components/ImageCard.vue'
import ImageDetailModal from '../components/ImageDetailModal.vue'

const gallery = useGalleryStore()
const appStore = useAppStore()

const sentinel = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null

onMounted(async () => {
  await gallery.fetchImages(true)

  // Infinite scroll via IntersectionObserver
  observer = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting && gallery.hasMore && !gallery.loading) {
        gallery.loadMore()
      }
    },
    { rootMargin: '200px' }
  )
  if (sentinel.value) observer.observe(sentinel.value)
})

const isEmpty = computed(() => !gallery.loading && gallery.images.length === 0)

async function handleRefresh() {
  await appStore.triggerScan()
  await gallery.fetchImages(true)
}
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Header bar -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-surface-100">Gallery</h2>
        <p class="text-sm text-surface-500 mt-0.5">
          {{ gallery.total }} image{{ gallery.total !== 1 ? 's' : '' }}
        </p>
      </div>
      <div class="flex items-center gap-3">
        <button
          class="btn-primary"
          :disabled="appStore.scanning"
          @click="handleRefresh"
        >
          <span v-if="appStore.scanning" class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
          <span v-else>🔄</span>
          {{ appStore.scanning ? 'Scanning...' : 'Scan & Refresh' }}
        </button>
      </div>
    </div>

    <!-- Empty state -->
    <div
      v-if="isEmpty"
      class="flex flex-col items-center justify-center py-32 text-center"
    >
      <div class="text-6xl mb-4 opacity-30">📸</div>
      <h3 class="text-xl font-semibold text-surface-300 mb-2">No images yet</h3>
      <p class="text-sm text-surface-500 max-w-md mb-6">
        Register a folder in Settings, then click "Scan &amp; Refresh" to start indexing your photos.
      </p>
      <router-link to="/settings" class="btn-primary">
        ⚙️ Go to Settings
      </router-link>
    </div>

    <!-- Image grid -->
    <div
      v-else
      class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-7 gap-3"
    >
      <ImageCard
        v-for="image in gallery.images"
        :key="image.id"
        :image="image"
        @click="gallery.selectImage(image)"
      />
    </div>

    <!-- Infinite scroll sentinel -->
    <div ref="sentinel" class="h-px"></div>

    <!-- Loading indicator -->
    <div v-if="gallery.loading" class="flex justify-center py-8">
      <div class="w-8 h-8 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin"></div>
    </div>

    <!-- Image detail modal -->
    <ImageDetailModal
      v-if="gallery.showDetail && gallery.selectedImage"
      :image="gallery.selectedImage"
      @close="gallery.closeDetail()"
    />
  </div>
</template>
