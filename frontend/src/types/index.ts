export interface ImageItem {
  id: number
  file_path: string
  file_hash: string
  file_size: number | null
  width: number | null
  height: number | null
  format: string | null
  exif_json: string | null
  thumbnail_path: string | null
  indexed_at: string | null
  modified_at: string | null
  status: string
  embedding_status: string
}

export interface ImageList {
  items: ImageItem[]
  total: number
  page: number
  page_size: number
}

export interface FolderItem {
  id: number
  path: string
  recursive: boolean
  face_detection_enabled: boolean
  last_scanned: string | null
}

export interface FolderCreate {
  path: string
  recursive: boolean
  face_detection_enabled: boolean
}

export interface JobItem {
  id: number
  type: string
  image_id: number | null
  status: string
  priority: number
  created_at: string | null
  started_at: string | null
  finished_at: string | null
  error: string | null
  retries: number
}

export interface JobList {
  items: JobItem[]
  total: number
}

export interface ScanResponse {
  new_images: number
  modified_images: number
  deleted_images: number
  jobs_created: number
}

export interface Stats {
  total_images: number
  indexed_images: number
  pending_images: number
  error_images: number
  total_folders: number
  queued_jobs: number
  running_jobs: number
}

export interface SearchHit {
  image: ImageItem
  score: number
  vector_distance: number
  source: 'vector' | 'keyword' | 'both'
}

export interface SearchResult {
  results: SearchHit[]
  total: number
  query: string
}

export interface ImageMetadata {
  image_id: number
  captions: { caption: string; model: string | null }[]
  tags: { tag: string; source: string; confidence: number | null }[]
  ocr: { text: string; engine: string | null; confidence: number | null }[]
}
