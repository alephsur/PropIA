# PropIA v3.0 · Real Estate Automation System

Automates the documentary searches that a real estate agent performs manually:
Cadastre (Catastro), urban planning (PGOU), regional regulation
(BOC / BOPA — official gazettes of Cantabria and Asturias), national
regulation (BOE) and document analysis with AI.

> **Target regions:** Cantabria and Asturias. Designed to scale to the rest of
> Spain without refactoring.

---

## Quick start

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env with ANTHROPIC_API_KEY (Ollama does not require a key)

# 2. Bring up the full stack (db + ollama + backend + frontend)
docker-compose up -d

# 3. Health check
curl http://localhost:8000/health
# → { "db": "ok", "llm": "ok", "llm_provider": "anthropic" }
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API docs (Swagger) | http://localhost:8000/docs |
| API docs (Redoc) | http://localhost:8000/redoc |
| Health | http://localhost:8000/health |

Alembic migrations are applied automatically on startup (FastAPI `lifespan`).
The first time the embedding endpoint is invoked, Ollama downloads the
`mxbai-embed-large` and `qwen2.5:7b` models.

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 · FastAPI 0.115 · Pydantic v2 |
| ORM | SQLAlchemy 2.0 async + Alembic |
| Database | PostgreSQL 16 + `pgvector` extension |
| Embeddings | Local Ollama · `mxbai-embed-large` · 1024 dim |
| LLM synthesis | `claude-sonnet-4-20250514` (Anthropic) + fallbacks OpenRouter, Groq and Ollama (`qwen2.5:7b`) |
| Lexical search | PostgreSQL FTS (`tsvector` + `websearch_to_tsquery` with Spanish dictionary) |
| PDF parsing | `pdfplumber` (text and tables) · `pymupdf` (OCR fallback) · `pytesseract` (lang=`spa`) |
| Scraping | async `httpx` + `BeautifulSoup4` |
| Async tasks | `FastAPI BackgroundTasks` + polling on the `tareas_background` table |
| Frontend | React 18 · Vite · TypeScript · Tailwind CSS · Zustand · TanStack Query v5 |

### Firm decisions
- **No Redis, no Celery.** Long-running tasks (download + indexing) live in
  `BackgroundTasks` and the frontend polls `/tareas/{id}` every 2 s.
- **No WMS/WFS** for Cantabria and Asturias — those regions do not publish WMS
  planning services. Urban planning queries rely **exclusively** on the
  in-house RAG index of the PGOU PDFs themselves.
- **100% local embeddings** via Ollama: no per-token cost, no quota limits and
  no external dependency on the critical indexing path.

---

## Architecture

```
┌──────────────┐     HTTP/JSON     ┌──────────────────────────────┐
│  React SPA   │ ────────────────▶ │   FastAPI (async, lifespan)  │
│ (Vite + Zus) │ ◀──────────────── │                              │
└──────────────┘                   │  ┌────────────────────────┐  │
                                   │  │ api/  routers          │  │
                                   │  │ services/  domain      │  │
                                   │  │ integrations/  OVC,    │  │
                                   │  │   BOE, BOC, BOPA       │  │
                                   │  │ ai/   pgou_index, RAG  │  │
                                   │  └────────────────────────┘  │
                                   └──────────────┬───────────────┘
                                                  │
                  ┌───────────────────────────────┼───────────────────┐
                  ▼                               ▼                   ▼
        ┌──────────────────┐         ┌──────────────────────┐  ┌───────────────┐
        │ PostgreSQL 16    │         │ Ollama (GPU)         │  │ Anthropic API │
        │  + pgvector      │         │  mxbai-embed-large   │  │ claude-sonnet │
        │  + FTS spanish   │         │  qwen2.5:7b (LLM)    │  │   -4-20250514 │
        └──────────────────┘         └──────────────────────┘  └───────────────┘
```

### Directory layout

```
propia/
├── backend/
│   └── app/
│       ├── main.py              # FastAPI app, CORS, lifespan (alembic upgrade head)
│       ├── config.py            # Settings (pydantic-settings) loaded from .env
│       ├── api/                 # HTTP routers — validation + delegation only
│       │   ├── catastro.py      # OVC: query by cadastral reference or address
│       │   ├── urbanismo.py     # /urbanismo/informe → RAG + synthesis
│       │   ├── normativa.py     # BOC, BOPA, BOE
│       │   ├── documentos.py    # Analysis with Claude vision
│       │   ├── biblioteca.py    # Explore URL → confirm → download → index
│       │   └── tareas.py        # GET /tareas/{id} (BackgroundTasks polling)
│       ├── services/            # Domain logic
│       │   ├── ai_synthesis.py  # SYSTEM_INFORME / SYSTEM_PGOU / SYSTEM_DOCUMENTOS
│       │   ├── scraper.py       # scrape_documentos_url() + _detectar_seccion()
│       │   ├── orquestador.py   # Catastro + PGOU + Normativa
│       │   └── biblioteca.py
│       ├── integrations/        # External API clients
│       │   ├── catastro.py      # OVC — always POST form-urlencoded
│       │   ├── boe.py           # BOE (REST API) + BOC + BOPA (scraping)
│       │   └── pgou_wms.py      # Stub for other regions
│       ├── ai/
│       │   ├── embeddings.py    # Ollama + sliding window + mean-pool
│       │   ├── pgou_index.py    # Semantic chunking, hybrid RAG, re-ranking
│       │   ├── fichas_aa_parser.py # Development sheet + cadastral reference parser
│       │   └── llm_client.py    # Provider abstraction: Anthropic / OpenRouter / Groq / Ollama
│       ├── db/
│       │   ├── models.py        # SQLAlchemy models (pgvector included)
│       │   ├── session.py       # AsyncSession + get_db
│       │   └── migrations/      # Alembic (001_initial.py includes GIN over tsv)
│       └── utils/
│           ├── ccaa.py
│           ├── logger.py
│           └── storage.py       # PDFs under backend/storage/docs/<region>/<municipality>/
├── frontend/
│   └── src/
│       ├── api/client.ts        # axios + typed helpers
│       ├── stores/appStore.ts   # global Zustand store
│       └── components/
│           ├── modules/         # CatastroPanel, UrbanismoPanel, NormativaPanel,
│           │                    # DocumentosPanel, BibliotecaPanel
│           └── shared/          # Sidebar, PdfViewer, ProgressTracker, ConfirmDialog
└── docker-compose.yml           # db (pgvector/pg16) + ollama (GPU) + backend + frontend
```

### PostgreSQL tables

| Table | Purpose |
|---|---|
| `documentos_biblioteca` | PDFs downloaded by municipality/section |
| `tareas_background` | Download/indexing state (`pending|running|done|error`) |
| `pgou_municipios` | Municipalities with an active RAG index |
| `pgou_chunks` | Text chunks + `embedding vector(1024)` + `tsv tsvector` (FTS) |
| `pgou_fichas_aa` | Structured development sheets (one ámbito per row) |
| `pgou_refs_catastrales` | Normalized block/plot pairs per sheet — lookup by cadastral reference |
| `normativa_cache` | BOC/BOPA search cache with `expires_at` |

---

## Functional modules

| Module | Flow |
|---|---|
| **Cadastre** | `POST /catastro/...` → OVC (form-urlencoded, uppercase) → property data |
| **Urban planning / PGOU** | `POST /urbanismo/informe` → hybrid RAG + lookup by cadastral reference → Claude synthesis |
| **Regulation** | BOC/BOPA scraping + BOE API with PostgreSQL caching |
| **Documents** | PDF upload → Claude vision → structured JSON (deeds, simple notes...) |
| **Library** | Town-hall URL → scraping → confirmation → download → RAG indexing |

### Library flow (four steps)
1. **Explore.** `POST /biblioteca/explorar` with the town-hall URL → the page
   is parsed with `httpx + BeautifulSoup` and returns the PDFs grouped by
   section (Normativa, Memoria, Fichas, PEPRI, Planos, Boletín...).
2. **Confirm.** The user ticks which documents to download (UI checkboxes).
3. **Download.** `POST /biblioteca/descargar` inserts a row into
   `tareas_background` and spawns a `BackgroundTask`. For indexable sections
   (everything except `Planos` and `Boletín`), `indexar_pdf()` is invoked
   right after the download.
4. **Poll.** The frontend hits `GET /tareas/{id}` every 2 s until
   `status == "done"`.

---

## RAG · Full pipeline

The system answers urban-planning questions about a municipality by
synthesizing real fragments of the indexed PGOU. The core lives in
`backend/app/ai/pgou_index.py`. The pipeline has two phases —
**indexing** (offline, once per document) and **query** (online, per
question).

### 1 · Indexing

```
PDF  →  Extraction  →  Semantic chunking  →  Embeddings  →  Persistence
        (pdfplumber)   (articles / sheets)   (mxbai 1024)   (pgou_chunks)
```

#### 1.1 · Text extraction
- `pdfplumber` extracts text **page by page**, preserving the page number
  (required for deep-links in the frontend PDF viewer).
- For each page the **tables** are also exported as `Key: Value` pairs. This
  is critical for **PGOU development sheets**, where parameters such as
  buildability, dwellings, transfers, instruments and deadlines live in
  two-column tables that `extract_text()` would flatten, breaking the
  key↔value relation.
- **Automatic OCR** when the average drops below 80 characters per page: each
  page is rasterized at 200 dpi with `pymupdf` and OCR'd with `pytesseract`
  in Spanish (`lang=spa`).

#### 1.2 · Semantic chunking by article
For Spanish urban-planning text, arbitrary size-based chunking breaks
articles. The indexer uses a regex that detects the typical PGOU delimiters:

```regex
Art(?:ículo|\.)\s*[\d]+(?:[\.\-]\d+)*       # Artículo 1, Art. 4.3.1
| CAPÍTULO\s+[IVXLCDM\d]+[\.\-ºª]?           # CAPÍTULO I, CAPÍTULO 1
| SECCIÓN\s+[IVXLCDM\d\.\-ºª]+               # SECCIÓN 1ª
| TÍTULO\s+[IVXLCDM\d]+[\.\-ºª]?             # TÍTULO I
| Disposición\s+(?:adicional|transitoria|final|derogatoria)\s+\w+
```

Size policy:
- Section between `_MIN_CHUNK_CHARS = 80` and `_MAX_CHUNK_CHARS = 1500` →
  single chunk.
- Section > 1500 chars → split by paragraphs (`\n\s*\n`) into pieces with a
  derived title (`(part 1)`, `(part 2)`...).
- Section < 80 chars → merged into the previous chunk (noise avoidance).
- If the regex detects **fewer than 3 articles**, the indexer assumes the
  document is not legal text (report, study...) and falls back to paragraph
  chunking with overlap (`_FALLBACK_CHUNK_SIZE = 800`,
  `_FALLBACK_OVERLAP = 150`).

Each chunk carries in `metadatos`: `seccion`, `posicion`, `total_chunks`,
`pagina_inicio`, `pagina_fin`. `posicion` is key for the **±1 context
expansion** at query time.

#### 1.3 · Development sheets (AA / URB)
If the section consists of development sheets, in addition to semantic
chunking `fichas_aa_parser.parsear_fichas_pdf()` is invoked, which:
1. Detects each **ámbito** (`AA V1`, `AA BA`, `URB SM`...) with regex.
2. Extracts the basic fields with regex (fast, no cost).
3. Calls Claude (specific `SYSTEM` prompt) over the full sheet text to
   extract **every schema field** (objectives, typology, ordinance,
   buildability, transfers as a dict, instruments, deadlines, conditions as
   an array...).
4. Extracts **normalized cadastral references**:
   `"Parcelas 13 y 14 de la MANZANA 67441"` →
   `(block=67441, plot=13)` and `(block=67441, plot=14)`.
5. Persists a record in `pgou_fichas_aa` with `datos_json` (Claude) +
   structured fields; normalized cadastral refs into `pgou_refs_catastrales`;
   and **an extra semantic chunk** into `pgou_chunks` with the sheet as plain
   text (so it is retrievable through semantic search, not only by direct
   cadastral lookup).

#### 1.4 · Embeddings with sliding window + mean-pool
`mxbai-embed-large` has a fixed window of **512 tokens** (~1000 chars of
Spanish legal text with numbers and acronyms). Chunks can be longer (dense
articles run ~1500 chars), so `ai/embeddings.py` applies **transparent
windowing**:

1. For each text, windows of `_MAX_CHARS = 1000` are generated with
   `_WINDOW_OVERLAP = 200` overlap.
2. All windows (across all chunks) are grouped into batches of
   `_BATCH_SIZE = 32` and sent to Ollama's `POST /api/embed` in a single
   inference per batch.
3. The windows belonging to the same text are averaged coordinate-wise
   (`_mean_pool`). Since `mxbai-embed-large` emits normalized vectors, the
   mean preserves the dominant semantic direction.

Result: **one 1024-dim vector per chunk**, regardless of text length. Same
pgvector schema as any 1024-dim model.

Resilience: 3 retries with 2 s back-off if Ollama is not ready yet (typical
on the very first boot, while the model is still being pulled).

#### 1.5 · Persistence
```sql
INSERT INTO pgou_chunks (id, municipio, provincia, documento_id, seccion,
                         articulo, contenido, pagina, metadatos)
VALUES (...);

UPDATE pgou_chunks
   SET embedding = CAST(:emb AS vector)
 WHERE id = :id;
```

The `tsv` column is **generated automatically** by a SQL expression in
migration `001_initial.py` (`to_tsvector('spanish', contenido)`) with a GIN
index. It is not managed from Python code.

### 2 · Query — hybrid RAG

```python
chunks = await buscar_pgou(db, municipio, provincia, pregunta,
                           top_k=10, rerank=True, expand_query=True)
```

8-step pipeline (`pgou_index.buscar_pgou`):

#### 2.1 · Query expansion (light HyDE)
The real estate agent asks in casual language ("can this plot be split?").
To make the search retrieve the PGOU's technical vocabulary ("segregation",
"minimum plot", "minimum frontage"), the system asks the LLM for **two
technical reformulations** with a short system prompt:

```text
You are an expert in Spanish PGOU. Produce 2 reformulations using technical
urban-planning vocabulary (artículo, ordenanza, clasificación,
aprovechamiento, coeficiente, zonificación, retranqueo, edificabilidad,
etc.).
```

If the LLM fails, it degrades to `[query]` (search is not blocked).

#### 2.2 · Averaged embedding
The 3 variants (original + 2 technical) are embedded in batch and averaged
with `_mean_pool`. The resulting vector captures the different phrasings at
once.

#### 2.3 · Semantic search (top 20)
```sql
SELECT id, contenido, seccion, articulo, metadatos, documento_id, pagina,
       1 - (embedding <=> CAST(:emb AS vector)) AS similitud
  FROM pgou_chunks
 WHERE municipio = :municipio AND provincia = :provincia
 ORDER BY embedding <=> CAST(:emb AS vector)
 LIMIT 20;
```

pgvector's `<=>` operator yields cosine distance; `1 - distance` is the final
similarity.

#### 2.4 · Lexical search (top 20)
In conceptual parallel, Spanish FTS over the generated `tsv` column:

```sql
SELECT id, ..., ts_rank(tsv, websearch_to_tsquery('spanish', :q)) AS ts_score
  FROM pgou_chunks
 WHERE municipio = :municipio AND provincia = :provincia
   AND tsv @@ websearch_to_tsquery('spanish', :q)
 ORDER BY ts_score DESC
 LIMIT 20;
```

Terms from the 3 variants are concatenated: `websearch_to_tsquery` joins them
with implicit OR. The lexical channel recovers rare terms (numbers,
acronyms, ordinance codes) that semantic embeddings can miss.

#### 2.5 · RRF (Reciprocal Rank Fusion)
```text
rrf_score(chunk) = Σ (1 / (K + rank_i))     with K = 60
```

Each chunk earns points based on its rank in each list (semantic and
lexical). RRF is robust to heterogeneous scales (cosine similarity vs
ts_rank) and favors chunks appearing in both lists. After fusion the top
**15** survive into the next step.

#### 2.6 · LLM re-ranking
Over those 15 chunks, a second LLM evaluates **true relevance** against the
original question. Each chunk is sent trimmed to 500 chars with an `[N]`
identifier, and the LLM returns:

```json
{ "scores": [{ "id": 0, "score": 8 }, { "id": 1, "score": 3 }, ...] }
```

Chunks are sorted by descending score and the top `top_k` (10 by default) is
kept. If the re-ranker fails, the system falls back to RRF's top 10
(answering is not blocked).

#### 2.7 · ±1 context expansion
For each chunk in the top-N, the **adjacent** chunks (`posicion ± 1`) of the
same document are also loaded. Reason: PGOU articles cross-reference each
other ("as stated in the previous article"), and a single chunk often loses
immediate context.

#### 2.8 · Sequential ordering
Before returning, the chunks are sorted by `(documento_id, posicion)` so the
final LLM reads them **in the document's natural order**, not by score. This
improves the coherence of synthesized answers.

### 3 · Final synthesis
The chunks are passed to `services/ai_synthesis.consultar_urbanismo()` with
the `SYSTEM_PGOU` prompt. The LLM must respond **only with valid JSON**:

```json
{
  "tipo_consulta": "parcela|normativa",
  "datos_urbanisticos": { "clasificacion_suelo": "...", ... },
  "respuesta": "...",
  "confianza": "alta|media|baja",
  "fuentes": [
    { "documento_id": "uuid", "pagina": 12, "seccion": "Normativa", "articulo": "Artículo 4.3.1" }
  ]
}
```

The `fuentes` field powers deep-links in the frontend's PDF viewer.

### 4 · Direct lookup by cadastral reference
When the query carries a cadastral reference (e.g.
`6646704UP8064N0001ST`), `buscar_por_rc()` runs before RAG:

```python
block = rc[0:5]   # '66467'
plot  = rc[5:7]   # '04'
```

A B-tree lookup (O log n) on `pgou_refs_catastrales` → if it exists, the
full sheet from `pgou_fichas_aa` (including the `datos_json` extracted by
Claude during indexing) is returned. If the exact block+plot combination is
not found, a second lookup is attempted by block only (same ámbito).

The sheet (when found) is combined with the RAG chunks and the LLM treats it
as the preferred source.

### 5 · Fast mode (`PGOU_FAST_MODE`)
When `AI_PROVIDER=ollama` it is recommended to enable `PGOU_FAST_MODE=true`
in `.env`. This:
- Disables **query expansion** (-1 LLM call).
- Disables **LLM re-ranking** (-1 call).
- Lowers `top_k` from 10 to 6 (`PGOU_FAST_TOP_K`).

Only 1 LLM call remains (the final synthesis). Reasonable latency with small
local models at the cost of some precision.

---

## Environment variables

```env
# Primary LLM
ANTHROPIC_API_KEY=sk-ant-...
AI_PROVIDER=anthropic           # anthropic | openrouter | groq | ollama
AI_MODEL=                       # empty = provider default

# Automatic fallback on rate-limit (HTTP 429)
AI_PROVIDER_FALLBACK=openrouter
AI_MODEL_FALLBACK=

# Other providers (optional)
OPENROUTER_API_KEY=
GROQ_API_KEY=

# Embeddings — local Ollama
OLLAMA_BASE_URL=http://ollama:11434
EMBEDDING_MODEL=mxbai-embed-large
OLLAMA_LLM_MODEL=qwen2.5:7b

# Database
DATABASE_URL=postgresql+asyncpg://propia:propia@db:5432/propia

# RAG
PGOU_FAST_MODE=false            # true when AI_PROVIDER=ollama
PGOU_FAST_TOP_K=6

# Server
ALLOWED_ORIGINS=http://localhost:5173
STORAGE_PATH=./storage/docs
MAX_PDF_SIZE_MB=100
```

---

## Development commands

```bash
# Live logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Restart backend only after Python changes
docker-compose restart backend
# (frontend has HMR — React changes reload automatically)

# Migrations
docker-compose exec backend alembic upgrade head
docker-compose exec backend alembic revision --autogenerate -m "..."
docker-compose exec backend alembic downgrade -1

# PostgreSQL
docker-compose exec db psql -U propia -d propia

# Tests
docker-compose exec backend pytest
docker-compose exec backend pytest tests/test_catastro.py -v
```

---

## Test data

| Concept | Value |
|---|---|
| Cadastral reference | `6646704UP8064N0001ST` |
| Province | `CANTABRIA` |
| Municipality | `SAN VICENTE DE LA BARQUERA` |
| PGOU URL | `https://aytosanvicentedelabarquera.es/urbanismo/` |
| Priority document | `4a_Normativa.pdf` |

---

## Critical rules — Cadastre (OVC)

> Validated in Postman. Do not change without re-validating.

- **Always POST** form-urlencoded. GET with empty parameters returns HTTP 400.
- `Provincia` and `Municipio` are **always mandatory** and **UPPERCASE**.

```python
await client.post(
    ".../OVCCallejero.asmx/Consulta_DNPRC",
    data={
        "Provincia": "CANTABRIA",
        "Municipio": "SAN VICENTE DE LA BARQUERA",
        "RC": "6646704UP8064N0001ST",
    },
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)
```
