# PropIA v3.0 · Sistema de Automatización Inmobiliaria
**Cantabria & Asturias** — Extensible al resto de España

## Arranque rápido

```bash
# 1. Clonar y configurar variables de entorno
cp .env.example .env
# Edita .env con tus API keys: ANTHROPIC_API_KEY y VOYAGE_API_KEY

# 2. Levantar servicios
docker-compose up -d

# 3. Aplicar migraciones (primera vez)
docker-compose exec backend alembic upgrade head

# 4. Acceder
# Frontend: http://localhost:5173
# API docs: http://localhost:8000/docs
# Health:   http://localhost:8000/health
```

## Arquitectura

| Componente | Tecnología |
|---|---|
| Backend | Python 3.12 · FastAPI 0.115 |
| Base de datos | PostgreSQL 16 + pgvector |
| ORM | SQLAlchemy 2.0 async + Alembic |
| IA síntesis | claude-sonnet-4-20250514 |
| Embeddings | Voyage AI voyage-3 (1024 dims) |
| Frontend | React 18 · Vite · Tailwind CSS · Zustand · TanStack Query v5 |
| Tareas async | FastAPI BackgroundTasks + polling a PostgreSQL |
| **Sin Redis** | Cache de normativa en tabla PostgreSQL con expires_at |

## Módulos

1. **Catastro** — POST form-urlencoded a OVC. RC validada: `6646704UP8064N0001ST`
2. **Planeamiento PGOU** — Índice RAG con pgvector (Cantabria/Asturias no tienen WMS)
3. **Normativa** — Scraping BOC + BOPA + API REST BOE
4. **Análisis de documentos** — Claude vision para escrituras, notas simples, etc.
5. **Biblioteca** — Scraping ayuntamientos → confirmación → descarga → indexación → visor PDF

## Estructura de directorios

```
propia/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + CORS + routers
│   │   ├── config.py            # Settings con pydantic-settings
│   │   ├── api/                 # Routers: catastro, urbanismo, normativa, documentos, biblioteca, tareas
│   │   ├── services/            # scraper.py, ai_synthesis.py
│   │   ├── integrations/        # catastro.py, boe.py (BOC+BOPA+BOE), pgou_wms.py
│   │   ├── ai/                  # embeddings.py, pgou_index.py (RAG)
│   │   ├── db/                  # models.py, session.py, migrations/
│   │   └── utils/               # ccaa.py, logger.py, storage.py
│   ├── storage/docs/            # PDFs descargados (volumen Docker persistente)
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/modules/  # CatastroPanel, UrbanismoPanel, NormativaPanel, DocumentosPanel, BibliotecaPanel
│       ├── components/shared/   # Sidebar, PdfViewer, ConfirmDialog, ProgressTracker
│       ├── stores/              # appStore.ts (Zustand)
│       └── api/                 # client.ts (axios + API helpers tipados)
└── docker-compose.yml           # db + backend + frontend (sin Redis)
```

## Variables de entorno (.env)

```env
ANTHROPIC_API_KEY=sk-ant-...
VOYAGE_API_KEY=pa-...
DATABASE_URL=postgresql+asyncpg://propia:propia@db:5432/propia
ALLOWED_ORIGINS=http://localhost:5173
STORAGE_PATH=./storage/docs
```

## RC de prueba (Catastro)
- **RC**: `6646704UP8064N0001ST`  
- **Provincia**: `CANTABRIA`  
- **Municipio**: `SAN VICENTE DE LA BARQUERA`

## URL PGOU de prueba (Biblioteca)
- https://aytosanvicentedelabarquera.es/urbanismo/
