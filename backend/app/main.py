"""PropIA v3.0 - Sistema de Automatización Inmobiliaria."""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

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


async def _init_db(retries: int = 10, delay: float = 3.0) -> None:
    """Inicializa la BD con reintentos para tolerar arranques lentos del contenedor db."""
    for attempt in range(1, retries + 1):
        try:
            async with engine.begin() as conn:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Tablas verificadas/creadas.")
            return
        except (OperationalError, OSError, Exception) as e:
            if attempt == retries:
                raise
            logger.warning(f"DB no disponible (intento {attempt}/{retries}): {e} — reintentando en {delay}s...")
            await asyncio.sleep(delay)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("PropIA v3.0 arrancando...")
    await _init_db()
    yield
    logger.info("PropIA v3.0 cerrando...")
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
    from app.ai.llm_client import get_provider_info
    provider_info = get_provider_info()
    provider = provider_info["provider"]

    estado = {"db": "error", "llm": "error", "voyage": "error", "llm_provider": provider}

    # DB
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        estado["db"] = "ok"
    except Exception as e:
        logger.error(f"DB health check failed: {e}")

    # LLM provider
    try:
        if provider == "anthropic":
            key_ok = bool(settings.anthropic_api_key)
        elif provider == "openrouter":
            key_ok = bool(settings.openrouter_api_key)
        elif provider == "groq":
            key_ok = bool(settings.groq_api_key)
        else:
            key_ok = False
        estado["llm"] = "ok" if key_ok else "no_key"
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


@app.get("/ai/provider", tags=["AI"])
async def ai_provider():
    """Devuelve el proveedor LLM activo y los modelos por defecto disponibles."""
    from app.ai.llm_client import get_provider_info
    return get_provider_info()


@app.get("/", tags=["Root"])
async def root():
    return {
        "app": "PropIA",
        "version": "3.0.0",
        "ccaa_priority": ["Cantabria", "Asturias"],
        "docs": "/docs",
    }
