"""Endpoints del módulo Normativa."""
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.integrations.boe import buscar_boe, buscar_boc, buscar_bopa
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/normativa", tags=["Normativa"])

# TTL de caché en horas (los boletines se publican una vez al día)
_CACHE_TTL_HORAS = 6

# URLs de búsqueda manual como fallback para el frontend
_URLS_BUSQUEDA = {
    "boc": "https://boc.cantabria.es/boces/inicioBusquedaAnuncios.do",
    "bopa": "https://miprincipado.asturias.es/bopa",
    "boe": "https://www.boe.es/buscar/",
}


async def _get_from_cache(db: AsyncSession, clave: str) -> list | None:
    """Devuelve resultado cacheado si no ha expirado."""
    try:
        result = await db.execute(
            text("SELECT resultado FROM normativa_cache WHERE clave = :clave AND expires_at > NOW()"),
            {"clave": clave},
        )
        row = result.fetchone()
        return row.resultado if row else None
    except Exception:
        return None


async def _save_to_cache(db: AsyncSession, clave: str, resultado: list, ttl_horas: int = _CACHE_TTL_HORAS) -> None:
    """Guarda resultado en caché."""
    try:
        expires_at = datetime.utcnow() + timedelta(hours=ttl_horas)
        await db.execute(
            text("""
                INSERT INTO normativa_cache (clave, resultado, expires_at)
                VALUES (:clave, CAST(:resultado AS jsonb), :expires_at)
                ON CONFLICT (clave) DO UPDATE
                SET resultado = CAST(:resultado AS jsonb), expires_at = :expires_at
            """),
            {
                "clave": clave,
                "resultado": __import__("json").dumps([r.model_dump() if hasattr(r, "model_dump") else r for r in resultado], ensure_ascii=False),
                "expires_at": expires_at,
            },
        )
        await db.commit()
    except Exception as e:
        logger.warning(f"No se pudo guardar caché normativa: {e}")


def _respuesta_con_meta(resultados: list, fuente: str, query: str) -> dict:
    """Envuelve los resultados con metadatos útiles para el frontend."""
    return {
        "fuente": fuente,
        "query": query,
        "total": len(resultados),
        "url_busqueda_manual": _URLS_BUSQUEDA.get(fuente.lower(), ""),
        "resultados": resultados,
    }


@router.get("/boc")
async def normativa_boc(q: str, fecha_desde: str | None = None):
    """Búsqueda en el BOC de Cantabria."""
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        clave = f"boc:{q}:{fecha_desde or ''}"
        cached = await _get_from_cache(db, clave)
        if cached is not None:
            logger.info(f"BOC cache hit: '{q}'")
            return _respuesta_con_meta(cached, "BOC", q)

        try:
            items = await buscar_boc(q, fecha_desde)
            datos = [i.model_dump() for i in items]
            await _save_to_cache(db, clave, items)
            return _respuesta_con_meta(datos, "BOC", q)
        except Exception as e:
            logger.error(f"Error BOC '{q}': {e}")
            raise HTTPException(
                status_code=502,
                detail={
                    "error": str(e),
                    "url_busqueda_manual": _URLS_BUSQUEDA["boc"],
                    "mensaje": "Error al consultar el BOC. Puedes buscar manualmente en la URL indicada.",
                },
            )


@router.get("/bopa")
async def normativa_bopa(q: str, fecha_desde: str | None = None):
    """Búsqueda en el BOPA de Asturias."""
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        clave = f"bopa:{q}:{fecha_desde or ''}"
        cached = await _get_from_cache(db, clave)
        if cached is not None:
            logger.info(f"BOPA cache hit: '{q}'")
            return _respuesta_con_meta(cached, "BOPA", q)

        try:
            items = await buscar_bopa(q, fecha_desde)
            datos = [i.model_dump() for i in items]
            await _save_to_cache(db, clave, items)
            return _respuesta_con_meta(datos, "BOPA", q)
        except Exception as e:
            logger.error(f"Error BOPA '{q}': {e}")
            raise HTTPException(
                status_code=502,
                detail={
                    "error": str(e),
                    "url_busqueda_manual": _URLS_BUSQUEDA["bopa"],
                    "mensaje": "Error al consultar el BOPA. Puedes buscar manualmente en la URL indicada.",
                },
            )


@router.get("/boe")
async def normativa_boe(q: str, fecha_desde: str | None = None):
    """Búsqueda en el BOE."""
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        clave = f"boe:{q}:{fecha_desde or ''}"
        cached = await _get_from_cache(db, clave)
        if cached is not None:
            logger.info(f"BOE cache hit: '{q}'")
            return _respuesta_con_meta(cached, "BOE", q)

        try:
            items = await buscar_boe(q, fecha_desde)
            datos = [i.model_dump() for i in items]
            await _save_to_cache(db, clave, items)
            return _respuesta_con_meta(datos, "BOE", q)
        except Exception as e:
            logger.error(f"Error BOE '{q}': {e}")
            raise HTTPException(
                status_code=502,
                detail={
                    "error": str(e),
                    "url_busqueda_manual": _URLS_BUSQUEDA["boe"],
                    "mensaje": "Error al consultar el BOE. Puedes buscar manualmente en la URL indicada.",
                },
            )
