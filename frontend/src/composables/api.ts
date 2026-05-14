/** API client — thin wrapper around fetch for the FastAPI backend. */

const BASE_URL = 'http://localhost:8000/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API ${res.status}: ${body}`)
  }
  return res.json()
}

import type { ImageList, ImageItem, FolderItem, FolderCreate, ScanResponse, JobList, Stats, SearchResult, ImageMetadata } from '../types'

export const api = {
  images: {
    list: (page = 1, pageSize = 50) =>
      request<ImageList>(`/images?page=${page}&page_size=${pageSize}`),

    get: (id: number) =>
      request<ImageItem>(`/images/${id}`),

    thumbnailUrl: (id: number) =>
      `${BASE_URL}/images/${id}/thumbnail`,

    fullUrl: (id: number) =>
      `${BASE_URL}/images/${id}/full`,

    metadata: (id: number) =>
      request<ImageMetadata>(`/images/${id}/metadata`),
  },

  folders: {
    list: () =>
      request<FolderItem[]>('/folders'),

    add: (data: FolderCreate) =>
      request<FolderItem>('/folders', { method: 'POST', body: JSON.stringify(data) }),

    remove: (id: number) =>
      request<void>(`/folders/${id}`, { method: 'DELETE' }),

    scan: (folderId?: number) =>
      request<ScanResponse>('/folders/scan', {
        method: 'POST',
        body: JSON.stringify({ folder_id: folderId ?? null }),
      }),
  },

  jobs: {
    list: (status?: string, limit = 50) => {
      const params = new URLSearchParams({ limit: String(limit) })
      if (status) params.set('status', status)
      return request<JobList>(`/jobs?${params}`)
    },

    stats: () =>
      request<Stats>('/jobs/stats'),

    embedAll: () =>
      request<{ jobs_created: number }>('/jobs/embed-all', { method: 'POST' }),

    processAll: () =>
      request<{ ocr_jobs: number; caption_jobs: number }>('/jobs/process-all', { method: 'POST' }),
  },

  search: {
    query: (q: string, limit = 20, offset = 0) =>
      request<SearchResult>(`/search?q=${encodeURIComponent(q)}&limit=${limit}&offset=${offset}`),
  },
}
