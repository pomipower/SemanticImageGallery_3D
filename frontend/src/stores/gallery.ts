import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../composables/api'
import type { ImageItem } from '../types'

export const useGalleryStore = defineStore('gallery', () => {
  const images = ref<ImageItem[]>([])
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(50)
  const loading = ref(false)
  const selectedImage = ref<ImageItem | null>(null)
  const showDetail = ref(false)

  const hasMore = computed(() => images.value.length < total.value)
  const indexedCount = computed(() => images.value.filter(i => i.status === 'indexed').length)

  async function fetchImages(resetPage = false) {
    if (resetPage) {
      page.value = 1
      images.value = []
    }
    loading.value = true
    try {
      const res = await api.images.list(page.value, pageSize.value)
      if (resetPage) {
        images.value = res.items
      } else {
        images.value.push(...res.items)
      }
      total.value = res.total
    } finally {
      loading.value = false
    }
  }

  async function loadMore() {
    if (!hasMore.value || loading.value) return
    page.value++
    await fetchImages()
  }

  function selectImage(image: ImageItem) {
    selectedImage.value = image
    showDetail.value = true
  }

  function closeDetail() {
    showDetail.value = false
    selectedImage.value = null
  }

  return {
    images,
    total,
    page,
    pageSize,
    loading,
    selectedImage,
    showDetail,
    hasMore,
    indexedCount,
    fetchImages,
    loadMore,
    selectImage,
    closeDetail,
  }
})
