# SemanticImageGallery — Local-First AI Photo System: Build Plan

> **Status:** Draft · Awaiting approval before coding begins  
> **Engineer POV:** Opinionated senior full-stack + ML systems design

---

## 1. Stack Validation & Recommendations

### ✅ Confirmed — Good Choices
| Component | Decision |
|---|---|
| FastAPI + SQLAlchemy | Solid. Use `aiosqlite` async driver + WAL mode |
| SQLite FTS5 | Perfect for local keyword search, zero ops |
| LanceDB (embedded) | Best fit: serverless, columnar, handles >RAM datasets |
| OpenCLIP ViT-B-32 | Right balance: fast CPU inference, proven accuracy |
| HDBSCAN | Correct for face clustering (handles noise, no K needed) |
| Vue 3 + Vite + TypeScript | Good frontend stack |

### ⚠️ Modifications Recommended

| Original | Recommendation | Reason |
|---|---|---|
| Tesseract OR PaddleOCR | **Use EasyOCR as default; PaddleOCR for power mode** | EasyOCR easier to install cross-platform; PaddleOCR more accurate on complex layouts |
| Ollama (captioning) | **Keep, but use `llava:7b` or `moondream`** | `moondream` is 1.6B params, CPU-friendly; llava:7b better quality |
| Celery (implied) | **Use `ARQ` (asyncio-native) backed by Redis-lite** | ARQ pairs perfectly with FastAPI async; BUT Redis adds a process dependency |
| Redis for queue | **Replace with SQLite-backed job queue (custom)** | No external broker; SQLite already in use; sufficient for single-machine throughput |
| InsightFace | **Keep InsightFace, use `buffalo_sc` (small/CPU) model** | `buffalo_l` is too heavy on CPU; `buffalo_sc` is the right CPU-tier model |
| Tailwind CSS | **Keep, but note: Vue 3 + Tailwind v3 only** | Tailwind v4 has breaking changes; pin to v3 |
| Vis.js for graph | **Use Cytoscape.js** | Vis.js is community-archived; Cytoscape.js is MIT, actively maintained, rich API |

### 🚩 Risks Flagged
- **Ollama captioning is slow on CPU** — budget 5–30s per image. Must be async + batched.
- **InsightFace install on Windows** is notoriously painful (ONNX Runtime + build tools). Document clearly.
- **LanceDB + SQLite dual-write** requires careful transaction coordination — embedding storage must be atomic with DB record.
- **HDBSCAN incremental clustering** is not native — requires periodic full re-cluster or approximate updates.

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND (Vue 3)                      │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │
│   │ Gallery  │ │ Search   │ │ Faces    │ │  Graph View  │  │
│   │ Grid     │ │ Bar      │ │ Panel    │ │  Cytoscape   │  │
│   └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬───────┘  │
└────────┼────────────┼────────────┼──────────────┼──────────┘
         │            │            │              │
         └────────────┴────────────┴──────────────┘
                              │ HTTP / SSE
┌─────────────────────────────▼───────────────────────────────┐
│                     API LAYER (FastAPI)                      │
│  /images  /search  /faces  /graph  /jobs  /index  /stream   │
└──────┬─────────────┬──────────────┬───────────────┬─────────┘
       │             │              │               │
┌──────▼──────┐ ┌────▼────┐  ┌─────▼──────┐ ┌─────▼──────────┐
│  INDEXING   │ │ SEARCH  │  │   FACE     │ │   GRAPH        │
│  PIPELINE   │ │ ENGINE  │  │  PIPELINE  │ │   ENGINE       │
│  (Workers)  │ │         │  │            │ │                │
└──────┬──────┘ └────┬────┘  └─────┬──────┘ └─────┬──────────┘
       │             │              │               │
┌──────▼─────────────▼──────────────▼───────────────▼─────────┐
│                      STORAGE LAYER                           │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐│
│  │  SQLite     │  │   LanceDB    │  │   Filesystem         ││
│  │  (main.db)  │  │  (vectors/)  │  │  /thumbs /faces      ││
│  │  FTS5 index │  │  images tbl  │  │  /originals (symlink)││
│  └─────────────┘  │  faces tbl   │  └──────────────────────┘│
│                   └──────────────┘                          │
└─────────────────────────────────────────────────────────────┘
         │
┌────────▼────────────────────────────────────────────────────┐
│                     ML PIPELINE                              │
│  OpenCLIP │ InsightFace │ EasyOCR │ Ollama (LLaVA/moondream)│
│  (loaded once, shared across worker processes)              │
└─────────────────────────────────────────────────────────────┘
```

**Key Design Decisions:**
- Single-process FastAPI server + background worker threads (no external broker)
- SQLite WAL mode: concurrent reads, serialized writes via asyncio lock
- LanceDB embedded in same process as API (no extra server)
- Thumbnails stored on filesystem, paths in SQLite
- Ollama runs as a sidecar process (user starts it separately)

---

## 3. Data Model

### SQLite Tables

#### `images`
```
id            INTEGER PK
file_path     TEXT UNIQUE NOT NULL       -- absolute path
file_hash     TEXT NOT NULL              -- SHA256 of file content
file_size     INTEGER
width         INTEGER
height         INTEGER
format        TEXT                       -- jpg/png
exif_json     TEXT                       -- raw EXIF as JSON blob
thumbnail_path TEXT
indexed_at    DATETIME
modified_at   DATETIME                   -- file mtime at index time
status        TEXT DEFAULT 'pending'     -- pending/processing/done/error
error_msg     TEXT
```

#### `tags`
```
id            INTEGER PK
image_id      INTEGER FK → images.id
tag           TEXT
source        TEXT                       -- 'clip'|'llm'|'user'
confidence    REAL
```

#### `captions`
```
id            INTEGER PK
image_id      INTEGER FK → images.id
caption       TEXT
model         TEXT                       -- 'moondream'|'llava'
created_at    DATETIME
```

#### `ocr_results`
```
id            INTEGER PK
image_id      INTEGER FK → images.id
text          TEXT
engine        TEXT                       -- 'easyocr'|'paddle'
confidence    REAL
created_at    DATETIME
```

#### `faces`
```
id            INTEGER PK
image_id      INTEGER FK → images.id
identity_id   INTEGER FK → identities.id  -- nullable
bbox_x1 bbox_y1 bbox_x2 bbox_y2  INTEGER
crop_path     TEXT
det_score     REAL
cluster_id    INTEGER                    -- raw HDBSCAN cluster label
```

#### `identities`
```
id            INTEGER PK
name          TEXT
created_at    DATETIME
thumbnail_face_id INTEGER FK → faces.id
```

#### `graph_edges`
```
id            INTEGER PK
identity_a    INTEGER FK → identities.id
identity_b    INTEGER FK → identities.id
weight        INTEGER DEFAULT 1          -- co-occurrence count
last_seen     DATETIME
UNIQUE(identity_a, identity_b)           -- enforce a < b for dedup
```

#### `jobs`
```
id            INTEGER PK
type          TEXT                       -- 'index'|'embed'|'ocr'|'caption'|'face'|'cluster'
image_id      INTEGER FK → images.id (nullable for global jobs)
status        TEXT DEFAULT 'queued'      -- queued/running/done/failed
priority      INTEGER DEFAULT 5
created_at    DATETIME
started_at    DATETIME
finished_at   DATETIME
error         TEXT
retries       INTEGER DEFAULT 0
```

#### `image_folders` (watched directories)
```
id            INTEGER PK
path          TEXT UNIQUE
recursive     BOOLEAN DEFAULT TRUE
last_scanned  DATETIME
```

### FTS5 Virtual Table
```sql
CREATE VIRTUAL TABLE images_fts USING fts5(
  image_id UNINDEXED,
  caption,
  tags,
  ocr_text,
  content='',          -- contentless for manual population
  tokenize='porter ascii'
);
```

### LanceDB Tables
- **`image_embeddings`**: `{image_id: str, vector: float32[512], file_path: str}`
- **`face_embeddings`**: `{face_id: str, image_id: str, vector: float32[512]}`

---

## 4. Indexing Pipeline Design

### Step-by-Step Flow

```
1. SCAN
   └── Walk registered folders recursively
   └── Filter: .jpg .jpeg .png only
   └── For each file: read mtime + size

2. CHANGE DETECTION (Hybrid Strategy)
   └── Fast path: compare mtime + size vs. stored values
   └── If changed: compute SHA256 hash
   └── If hash differs from stored: mark as modified
   └── New files: insert with status='pending'
   └── Missing files: mark status='deleted' (soft delete)
   └── Rationale: mtime+size check is O(1); hash only on candidates

3. JOB QUEUE INSERTION
   └── For each new/modified image: insert rows into `jobs` table
   └── Job types: thumbnail → embed → ocr → caption → face
   └── Priority ordering: thumbnail > embed > ocr > caption > face

4. WORKER LOOP (background asyncio task)
   └── Poll `jobs` WHERE status='queued' ORDER BY priority, created_at
   └── Claim job: UPDATE status='running', started_at=NOW()
   └── Execute stage
   └── On success: UPDATE status='done', finished_at=NOW()
   └── On failure: UPDATE status='failed', error=..., retries+=1
   └── Max retries: 3 before permanent failure
```

### Job Queue Design
**Decision: SQLite-backed custom queue** (no Redis/Celery)
- Single SQLite DB, WAL mode, `busy_timeout=30s`
- Worker is a background `asyncio.Task` spawned at FastAPI startup
- Heavy CPU work (embedding, OCR, face detection) runs in `ProcessPoolExecutor` via `loop.run_in_executor()`
- Queue polled every 500ms when empty; immediate retry when work is found
- SSE endpoint `/api/jobs/stream` pushes progress to frontend

### Thumbnail Stage
- Resize to 300px longest edge, JPEG quality 85
- Store at `{data_dir}/thumbs/{image_hash[:2]}/{image_hash}.jpg`
- Use Pillow (fast, no ML model needed)

---

## 5. ML Pipeline Design

### Model Loading Strategy
**Critical: Load models ONCE at worker startup, keep in memory.**

```
Worker Process Pool:
  ProcessPoolExecutor(max_workers=2)   ← CPU-only: 2 workers max
  Each worker process:
    - Loads OpenCLIP model on first task (cached via module-level singleton)
    - Loads InsightFace model on first face task
    - EasyOCR reader loaded per-worker (heavy, ~500MB)
    - Ollama: HTTP call to localhost:11434 (separate process)
```

### Model Memory Budget (CPU)
| Model | RAM |
|---|---|
| OpenCLIP ViT-B-32 | ~350 MB |
| InsightFace buffalo_sc | ~200 MB |
| EasyOCR (en) | ~500 MB |
| Ollama moondream | ~1.6 GB |
| **Total** | **~2.7 GB** |

> On 8GB RAM systems this is fine. On 4GB systems, disable Ollama captioning or use moondream only.

### Batch Processing
- Embeddings: batch size 16 (OpenCLIP)
- OCR: single image (EasyOCR not efficiently batchable on CPU)
- Face detection: single image
- Captions: single image (Ollama HTTP, sequential)

### CPU vs GPU Fallback
```python
device = "cuda" if torch.cuda.is_available() else "cpu"
# For ONNX-based models (InsightFace):
providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
```
No special user config needed — auto-detected at startup.

### Embedding Caching
- LanceDB stores embeddings persistently; skip re-embedding if `image_hash` unchanged
- File hash = cache key; no expiry needed (deterministic model outputs)

---

## 6. Search System Design

### Architecture
```
User Query (text)
      │
      ▼
  Query Parser
  ├── Extract filters: date:, tag:, person:, has:text
  └── Remaining text → embedding query

      │
      ├──── Vector Search ──────────► LanceDB ANN (top-50)
      │                               cosine similarity, ViT-B-32 space
      │
      └──── Keyword Search ─────────► SQLite FTS5 (top-50)
                                      BM25 ranking built-in

      │
      ▼
  Reciprocal Rank Fusion (RRF)
  score = Σ 1 / (k + rank_i)   k=60 (standard)
      │
      ▼
  Metadata Filter (SQL WHERE)
  └── date range, tags, identity, has_faces, has_ocr
      │
      ▼
  Final ranked results → paginated response
```

### Query Flow
1. `POST /api/search` — `{query: string, filters: {...}, page: int}`
2. Backend: embed query text with OpenCLIP (cached per query string)
3. Parallel: LanceDB `search().limit(50)` + SQLite FTS5 `MATCH` query
4. RRF fusion → apply metadata filters → return top-20 with cursor pagination
5. Frontend receives `{results: [...], next_cursor: str}`

### Metadata Filters (SQL)
```sql
SELECT i.* FROM images i
JOIN tags t ON t.image_id = i.id
WHERE t.tag IN (?) AND i.indexed_at BETWEEN ? AND ?
  AND i.id IN (SELECT image_id FROM faces WHERE identity_id = ?)
```

---

## 7. Face Clustering Design

### Embedding Storage
- Face embeddings stored in LanceDB `face_embeddings` table
- Also store `cluster_id` and `identity_id` in SQLite `faces` table
- Face crops stored at `{data_dir}/faces/{face_id}.jpg`

### Clustering Pipeline

#### Batch (Full Re-cluster — runs on demand or nightly)
```
1. Load all face embeddings from LanceDB as numpy array
2. Run HDBSCAN(min_cluster_size=3, metric='cosine')
3. Write cluster_id back to SQLite faces table
4. For unclaimed clusters (no identity): auto-create provisional identity
5. For existing identities: remap cluster → identity by majority vote
6. Update graph edges
```

#### Incremental (New faces after indexing)
```
1. New face embedding arrives
2. Query LanceDB: nearest neighbor among existing embeddings
3. If cosine_distance < 0.4: assign to same cluster/identity
4. If distance > 0.6: flag as 'unknown', queue for next full re-cluster
5. Schedule full re-cluster after every 100 new faces
```

### Identity Assignment Workflow
1. System shows "Unknown Clusters" panel in UI
2. User sees face grid per cluster → types name → saves
3. `POST /api/identities` creates `identities` row
4. `PATCH /api/faces/{id}` links faces to identity
5. User can merge clusters (two clusters → one identity)
6. User can split (mislabeled faces → new cluster)

### Cluster Stability Over Time
- Use a `cluster_version` counter in DB; increment on each full re-cluster
- Store `(face_id, cluster_id, cluster_version)` history for audit
- Never auto-rename user-assigned identities; only remap cluster_id

---

## 8. Graph System Design

### Co-occurrence Computation
```
For each image with ≥2 identified faces:
  For each pair (identity_a, identity_b) where a.id < b.id:
    UPSERT INTO graph_edges (identity_a, identity_b)
    SET weight = weight + 1, last_seen = NOW()
    ON CONFLICT DO UPDATE SET weight = weight + 1
```

Triggered after:
- Face identity assignment
- Full re-cluster completion

### Data Structure
- Stored in SQLite `graph_edges` (simple, queryable, no separate graph DB needed)
- For visualization: export as `{nodes: [...], edges: [...]}` JSON via API

### Update Strategy
- **Incremental**: Triggered immediately when a face is assigned/reassigned
- **Full recompute**: On full re-cluster (batch `DELETE + INSERT` for accuracy)
- Graph computation is O(F²) per image where F=faces; manageable for personal photo collections

### API
```
GET /api/graph
  → { nodes: [{id, name, photo, face_count}], edges: [{source, target, weight}] }
```

---

## 9. Frontend Architecture

### Component Tree
```
App
├── AppShell (sidebar nav, top bar, notifications)
├── GalleryView
│   ├── SearchBar (text input + filter chips)
│   ├── FilterPanel (date, tags, person, has_text)
│   ├── ImageGrid (virtual scroll)
│   │   └── ImageCard (thumbnail, hover overlay)
│   └── ImageDetailModal
│       ├── ImageViewer (zoom/pan)
│       ├── MetadataPanel (EXIF, tags, caption, OCR)
│       └── FaceChips (linked identities)
├── FacesView
│   ├── IdentityList
│   └── ClusterReviewPanel (unknown clusters → naming UI)
├── GraphView
│   └── CytoscapeGraph (force-directed, click → person filter)
└── SettingsView
    ├── FolderManager
    └── IndexingStatus (jobs list + SSE progress)
```

### State Management
- **Pinia** (Vue 3 official store) — not Vuex
- Stores: `galleryStore`, `searchStore`, `facesStore`, `graphStore`, `jobsStore`
- SSE connection in `jobsStore` for real-time indexing progress

### Efficient Image Loading
- Virtual scroll: `vue-virtual-scroller` library
- Thumbnails served via FastAPI static files endpoint (no base64)
- `IntersectionObserver` for lazy loading beyond virtual scroll
- Browser image cache: thumbnails are content-addressed by hash, cacheable forever (`Cache-Control: immutable`)
- Placeholder: blurred 20px thumbnail (LQIP) shown until full thumb loads

### Graph Visualization
- **Cytoscape.js** (MIT, actively maintained)
- Layout: `cose-bilkent` (force-directed, handles disconnected components)
- Node size = face count; edge thickness = co-occurrence weight
- Click node → navigate to gallery filtered by that person

---

## 10. Local Dev Setup Plan

### Folder Structure (Monorepo)
```
SmartImageGallery/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routers
│   │   ├── core/         # config, db, startup
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── pipeline/     # indexer, worker, job queue
│   │   └── ml/           # clip.py, face.py, ocr.py, caption.py
│   ├── alembic/          # DB migrations
│   ├── tests/
│   ├── pyproject.toml
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── views/
│   │   ├── stores/
│   │   ├── composables/
│   │   └── types/
│   ├── vite.config.ts
│   └── package.json
├── data/                 # .gitignore this
│   ├── main.db
│   ├── vectors/          # LanceDB files
│   ├── thumbs/
│   └── faces/
├── scripts/
│   ├── setup_models.py   # download/check Ollama models
│   └── dev_start.sh      # start all services
└── README.md
```

### Environment Setup
```bash
# Python
python -m venv .venv
pip install -r backend/requirements.txt

# Ollama (must be installed separately)
ollama pull moondream     # 1.6GB, CPU-friendly
ollama pull llava:7b      # optional, 4GB, better quality

# Frontend
cd frontend && npm install

# DB migrations
cd backend && alembic upgrade head
```

### Key Dependencies (backend/requirements.txt)
```
fastapi uvicorn[standard] sqlalchemy[asyncio] aiosqlite alembic
open-clip-torch pillow exifread
insightface onnxruntime
easyocr
hdbscan scikit-learn numpy
lancedb pyarrow
httpx python-multipart
```

### Dev Start Script
```bash
# Terminal 1: Ollama
ollama serve

# Terminal 2: Backend
cd backend && uvicorn app.main:app --reload --port 8000

# Terminal 3: Frontend
cd frontend && npm run dev
```

> For production (single user, desktop app): bundle with **PyInstaller** + serve frontend as static files from FastAPI.

---

## 11. Phased Build Plan

### M1 — Core Indexing + Gallery (Week 1–2)
**Deliverables:**
- Folder registration + recursive file scanner
- Change detection (mtime+hash)
- SQLite schema + Alembic migrations
- EXIF extraction + thumbnail generation (Pillow)
- FastAPI: `/images`, `/thumbnails`, `/folders` endpoints
- Vue: Gallery grid with virtual scroll, image detail modal

**Key Challenges:**
- Designing the job queue correctly (gets re-used by all later stages)
- File watcher vs. polling decision (use polling at scan time + optional watchdog library)

**Testing:**
- Unit: scanner handles new/modified/deleted files correctly
- Integration: index 1000 images, verify thumbnails + DB rows
- UI: gallery renders, infinite scroll works

---

### M2 — Embeddings + Search (Week 3–4)
**Deliverables:**
- OpenCLIP embedding generation (worker stage)
- LanceDB storage + ANN search
- SQLite FTS5 index population
- RRF hybrid search implementation
- FastAPI `/search` endpoint
- Vue: search bar + filter chips + results view

**Key Challenges:**
- Async embedding without blocking API (ProcessPoolExecutor)
- RRF score normalization across two different scoring systems

**Testing:**
- Benchmark: embed 1000 images, measure throughput (target: >10 img/s CPU)
- Search recall: manually verify top-5 results for 20 queries
- Hybrid fusion: confirm RRF beats either system alone

---

### M3 — Metadata: OCR + Captions + Tags (Week 5–6)
**Deliverables:**
- EasyOCR integration (worker stage)
- Ollama moondream captioning (async HTTP)
- LLM-extracted tags from caption
- FTS5 populated with OCR + captions
- MetadataPanel in UI (tags, caption, OCR text display)

**Key Challenges:**
- Ollama is slow — must show progress in UI (SSE stream)
- OCR adds significant processing time — make it optional/configurable
- Tag extraction from LLM output: need robust JSON parsing with fallback

**Testing:**
- OCR: test on images with printed text, signs, receipts
- Captions: qualitative review of 50 diverse images
- Tags: confirm tags appear in search results

---

### M4 — Face Pipeline (Week 7–8)
**Deliverables:**
- InsightFace detection + embedding (worker stage)
- Face crop storage
- HDBSCAN clustering (batch, triggered manually or post-index)
- Identity naming UI (cluster review panel)
- Face search filter (`person:Alice`)

**Key Challenges:**
- InsightFace install on Windows (document carefully)
- HDBSCAN instability with small datasets (<50 faces)
- Identity persistence across re-clusters

**Testing:**
- Detection: run on dataset with known faces, measure recall
- Clustering: verify same person → same cluster on controlled dataset
- Identity: name a cluster, verify it persists after re-cluster

---

### M5 — Graph System (Week 9)
**Deliverables:**
- Co-occurrence computation on identity assignment
- `graph_edges` population
- FastAPI `/graph` endpoint
- Cytoscape.js visualization in Vue
- Click-to-filter from graph node

**Key Challenges:**
- Cytoscape layout performance with large graphs (>200 nodes)
- Keeping graph in sync with identity changes

**Testing:**
- Create 5 identities, manually construct expected graph, verify output
- UI: click node → gallery filters correctly

---

### M6 — Hardening + Polish (Week 10–11)
**Deliverables:**
- Error handling throughout pipeline (retries, dead-letter jobs)
- Background re-indexing (watchdog or periodic poll)
- Settings UI: folder management, model selection, disable stages
- Performance profiling + bottleneck fixes
- SQLite VACUUM scheduled task
- README + setup documentation
- Optional: PyInstaller desktop packaging

**Testing:**
- End-to-end: index 10,000 images, measure total time and memory
- Stress: simulate 50,000 images (synthetic), verify DB query performance
- Regression: run full test suite on clean install

---

## 12. Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| **Ollama captioning too slow** — 10–30s/image on CPU | High | Make captioning opt-in per folder; run overnight; use moondream (fastest) |
| **InsightFace install fails on Windows** | High | Pre-test + document exact steps; provide fallback to `deepface` with `yunet` |
| **LanceDB + SQLite dual-write inconsistency** | High | Wrap both writes in a Python context manager; store `embedding_status` flag in SQLite; on crash, re-embed any image where flag != 'done' |
| **Large datasets (>100k images) → SQLite slow** | Medium | Enable WAL + cache_size; add composite indexes early; FTS5 is surprisingly fast; monitor with `EXPLAIN QUERY PLAN` |
| **HDBSCAN instability on <50 faces** | Medium | Use `min_cluster_size=2` for small datasets; add heuristic: don't cluster if <10 faces total |
| **Memory explosion with 3 ML models loaded** | Medium | Load models lazily per worker; unload EasyOCR if not recently used (LRU model cache) |
| **Vector search recall degrades over time** | Low | Re-index with new model version only if user triggers; store model name in embedding record |
| **Storage growth (thumbs + face crops)** | Low | Deduplicate by hash; offer "delete thumbnails for deleted images" maintenance task |
| **ONNX Runtime version conflicts (InsightFace vs others)** | Medium | Pin exact `onnxruntime==1.18.x`; use isolated venv; document tested versions |

---

## Open Questions for Review

> [!IMPORTANT]
> **Q1: Ollama captioning opt-in?**  
> Captioning is the slowest stage (5–30s/image CPU). Should it be disabled by default and user-enabled per folder, or enabled for all images with a visible queue?

> [!IMPORTANT]
> **Q2: Desktop app packaging?**  
> Should M6 target PyInstaller (single `.exe` bundle) or is a "run from terminal" setup acceptable for the target user?

> [!NOTE]
> **Q3: Face privacy controls?**  
> Should there be an option to entirely skip face detection on specific folders (e.g., sensitive content)?

> [!NOTE]
> **Q4: Multi-language OCR?**  
> EasyOCR supports 80+ languages. Should we make the language list configurable in Settings, or default English-only for simplicity?

---

## Verification Plan

### Automated Tests
- `pytest` for all pipeline stages (mocked ML models)
- FastAPI `TestClient` for all API endpoints
- SQLite schema validation via Alembic

### Manual Verification
- Gallery renders 1000 thumbnails without lag
- Search returns relevant results within 500ms
- Face clustering correctly groups 3 known individuals
- Graph shows expected co-occurrence after identity assignment
- Full re-index of 500 images completes without crash

---

*Awaiting approval to begin M1 implementation.*
