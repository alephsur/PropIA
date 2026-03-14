"""PropIA v3.0 - Sistema de Automatización Inmobiliaria."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.db.session import engine
from app.db.models import Base
from app.api.catastro import router as catastro_router
from app.api.urbanismo import router as urbanismo_router
from app.api.normativa import router as normativa_router
from app.api.documentos import router as documentos_router
from app.api.biblioteca import router as biblioteca_router
from app.api.tareas import router as tareas_router
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 PropIA v3.0 arrancando...")
    # Las migraciones se aplican con Alembic, no aquí
    yield
    logger.info("👋 PropIA v3.0 cerrando...")
    await engine.dispose()


app = FastAPI(
    title="PropIA v3.0",
    description="Sistema de Automatización Inmobiliaria · Cantabria & Asturias",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(catastro_router)
app.include_router(urbanismo_router)
app.include_router(normativa_router)
app.include_router(documentos_router)
app.include_router(biblioteca_router)
app.include_router(tareas_router)


@app.get("/health", tags=["Health"])
async def health():
    """Verifica el estado de todos los servicios."""
    estado = {"db": "error", "claude": "error", "voyage": "error"}

    # DB
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        estado["db"] = "ok"
    except Exception as e:
        logger.error(f"DB health check failed: {e}")

    # Claude
    try:
        if settings.anthropic_api_key and settings.anthropic_api_key.startswith("sk-ant"):
            estado["claude"] = "ok"
        else:
            estado["claude"] = "no_key"
    except Exception:
        pass

    # Voyage
    try:
        if settings.voyage_api_key:
            estado["voyage"] = "ok"
        else:
            estado["voyage"] = "no_key"
    except Exception:
        pass

    return estado


@app.get("/", tags=["Root"])
async def root():
    return {
        "app": "PropIA",
        "version": "3.0.0",
        "ccaa_priority": ["Cantabria", "Asturias"],
        "docs": "/docs",
    }
