<script setup lang="ts">
import { onMounted, ref, computed, watch } from 'vue'
import { useGalleryStore } from '../stores/gallery'
import { useAppStore } from '../stores/app'
import { api } from '../composables/api'
import ImageCard from '../components/ImageCard.vue'
import ImageDetailModal from '../components/ImageDetailModal.vue'
import type { ImageItem, SearchHit } from '../types'

const gallery = useGalleryStore()
const appStore = useAppStore()

const searchQuery = ref('')
const searchResults = ref<SearchHit[]>([])
const isSearching = ref(false)
const searchTotal = ref(0)
const searchMode = computed(() => searchQuery.value.trim().length > 0 && searchResults.value.length > 0)

const sentinel = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null

onMounted(async () => {
  await gallery.fetchImages(true)

  observer = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting && gallery.hasMore && !gallery.loading && !searchMode.value) {
        gallery.loadMore()
      }
    },
    { rootMargin: '200px' }
  )
  if (sentinel.value) observer.observe(sentinel.value)
})

const isEmpty = computed(() => !gallery.loading && gallery.images.length === 0 && !searchMode.value)

async function handleSearch() {
  const q = searchQuery.value.trim()
  if (!q) {
    searchResults.value = []
    searchTotal.value = 0
    return
  }
  isSearching.value = true
  try {
    const res = await api.search.query(q, 50)
    searchResults.value = res.results
    searchTotal.value = res.total
  } catch (e) {
    console.error('Search failed:', e)
    searchResults.value = []
  } finally {
    isSearching.value = false
  }
}

function clearSearch() {
  searchQuery.value = ''
  searchResults.value = []
  searchTotal.value = 0
}

function searchResultAsImage(hit: SearchHit): ImageItem {
  return hit.image
}

async function handleRefresh() {
  await appStore.triggerScan()
  await gallery.fetchImages(true)
}

// Displayed images: either search results or all images
const displayedImages = computed(() => {
  if (searchMode.value) {
    return searchResults.value.map(h => h.image)
  }
  return gallery.images
})

const displayedTitle = computed(() => {
  if (searchMode.value) {
    return `${searchTotal.value} result${searchTotal.value !== 1 ? 's' : ''} for "${searchQuery.value}"`
  }
  return `${gallery.total} image${gallery.total !== 1 ? 's' : ''}`
})
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Header bar -->
    <div class="flex items-center justify-between gap-4">
      <div class="min-w-0">
        <h2 class="text-2xl font-bold text-surface-100">Gallery</h2>
        <p class="text-sm text-surface-500 mt-0.5">{{ displayedTitle }}</p>
      </div>
      <button
        class="btn-primary flex-shrink-0"
        :disabled="appStore.scanning"
        @click="handleRefresh"
      >
        <span v-if="appStore.scanning" class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
        <span v-else>🔄</span>
        {{ appStore.scanning ? 'Scanning...' : 'Scan & Refresh' }}
      </button>
    </div>

    <!-- Search bar -->
    <div class="relative">
      <div class="flex gap-3">
        <div class="relative flex-1">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search images semantically... (e.g. 'group photo outdoors', 'celebration')"
            class="input-field pl-10 pr-10"
            @keydown.enter="handleSearch"
          />
          <span class="absolute left-3 top-1/2 -translate-y-1/2 text-surface-500">🔍</span>
          <button
            v-if="searchQuery"
            class="absolute right-3 top-1/2 -translate-y-1/2 text-surface-500 hover:text-surface-300 transition-colors"
            @click="clearSearch"
          >✕</button>
        </div>
        <button
          class="btn-primary"
          :disabled="!searchQuery.trim() || isSearching"
          @click="handleSearch"
        >
          {{ isSearching ? 'Searching...' : 'Search' }}
        </button>
      </div>

      <!-- Search result badges -->
      <div v-if="searchMode" class="flex items-center gap-2 mt-3">
        <span class="badge-info">Semantic Search</span>
        <span
          v-for="hit in searchResults.slice(0, 3)"
          :key="hit.image.id"
          class="badge bg-surface-700 text-surface-300 border border-surface-600/50 text-[10px]"
        >
          {{ hit.source === 'vector' ? '🧠' : hit.source === 'keyword' ? '🔤' : '⚡' }}
          {{ (hit.score * 100).toFixed(0) }}%
        </span>
        <button class="btn-ghost text-xs" @click="clearSearch">Clear search</button>
      </div>
    </div>

    <!-- Loading spinner for search -->
    <div v-if="isSearching" class="flex justify-center py-12">
      <div class="w-10 h-10 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin"></div>
    </div>

    <!-- Empty state -->
    <div
      v-else-if="isEmpty"
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

    <!-- No search results -->
    <div
      v-else-if="searchMode && searchResults.length === 0 && !isSearching"
      class="flex flex-col items-center justify-center py-20 text-center"
    >
      <div class="text-5xl mb-3 opacity-30">🔍</div>
      <h3 class="text-lg font-semibold text-surface-300">No results found</h3>
      <p class="text-sm text-surface-500 mt-1">Try different search terms</p>
    </div>

    <!-- Image grid -->
    <div
      v-else
      class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-7 gap-3"
    >
      <ImageCard
        v-for="image in displayedImages"
        :key="image.id"
        :image="image"
        @click="gallery.selectImage(image)"
      />
    </div>

    <!-- Infinite scroll sentinel (only in browse mode) -->
    <div v-if="!searchMode" ref="sentinel" class="h-px"></div>
    <div v-if="gallery.loading && !searchMode" class="flex justify-center py-8">
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
