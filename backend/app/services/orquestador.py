"""
Orquestador: coordina Catastro + PGOU + Normativa para generar informes completos.

Flujo principal para una RC:
  1. Catastro OVC  → datos registrales (superficie, titular, uso actual)
  2. buscar_por_rc → ficha del PGOU por manzana/parcela (si hay fichas indexadas)
  3. buscar_pgou   → RAG sobre normativa general del municipio
  4. Claude        → sintetiza todo en respuesta estructurada con fuentes
"""
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def generar_informe(req, db: AsyncSession) -> dict:
    """Informe completo: Catastro + ficha PGOU estructurada + RAG normativa + síntesis Claude.

    El resultado incluye un array 'fuentes' con documento_id y página
    para que el frontend muestre botones "Ver en Biblioteca".
    """
    from app.integrations.catastro import post_dnprc
    from app.ai.pgou_index import buscar_por_rc, buscar_pgou
    from app.services.ai_synthesis import sintetizar_informe

    # Ejecutar Catastro y PGOU en paralelo cuando sea posible
    datos_catastro: dict = {}
    ficha_aa: dict | None = None
    chunks_pgou: list[dict] = []

    # 1. Catastro — siempre si hay RC
    if req.rc:
        try:
            datos_catastro = await post_dnprc(req.provincia, req.municipio, req.rc)
        except Exception as e:
            logger.error(f"Catastro error: {e}")
            datos_catastro = {"error": str(e)}

    # 2. Búsqueda PGOU (paralela: ficha estructurada + RAG)
    if req.municipio and req.provincia:
        pregunta_rag = req.consulta or _pregunta_por_defecto(req.rc, datos_catastro)

        # Ejecutar secuencialmente: AsyncSession no admite operaciones concurrentes
        if req.rc:
            try:
                ficha_aa = await _buscar_ficha(db, req.municipio, req.provincia, req.rc)
            except Exception as e:
                logger.warning(f"buscar_por_rc falló: {e}")

        if pregunta_rag:
            try:
                chunks_pgou = await _buscar_rag(db, req.municipio, req.provincia, pregunta_rag)
            except Exception as e:
                logger.warning(f"buscar_pgou falló: {e}")

    # 3. Síntesis Claude
    informe = await sintetizar_informe(datos_catastro, chunks_pgou, [], ficha_aa=ficha_aa)
    return informe



async def comprobar_normativa(req, db: AsyncSession) -> dict:
    """Comprueba requisitos normativos para una operación (BOC/BOPA/BOE)."""
    from app.integrations.boe import buscar_boc, buscar_bopa
    from app.utils.ccaa import get_ccaa

    ccaa = get_ccaa(req.provincia)
    resultados = {}

    try:
        if ccaa == "cantabria":
            resultados["boc"] = await buscar_boc(req.tipo_operacion, None, db)
        elif ccaa == "asturias":
            resultados["bopa"] = await buscar_bopa(req.tipo_operacion, None, db)
    except Exception as e:
        logger.error(f"Normativa error: {e}")
        resultados["error"] = str(e)

    return {
        "municipio": req.municipio,
        "provincia": req.provincia,
        "tipo_operacion": req.tipo_operacion,
        "normativa": resultados,
        "status": "ok",
    }


# ── Helpers internos ──────────────────────────────────────────────────────────

async def _noop() -> None:
    """Placeholder para mantener el índice de asyncio.gather."""
    return None


async def _buscar_ficha(
    db: AsyncSession,
    municipio: str,
    provincia: str,
    rc: str,
) -> dict | None:
    from app.ai.pgou_index import buscar_por_rc
    return await buscar_por_rc(db, municipio, provincia, rc)


async def _buscar_rag(
    db: AsyncSession,
    municipio: str,
    provincia: str,
    pregunta: str,
) -> list[dict]:
    from app.ai.pgou_index import buscar_pgou
    try:
        return await buscar_pgou(db, municipio, provincia, pregunta)
    except ValueError:
        # municipio sin documentos indexados — no es un error grave
        return []


def _pregunta_por_defecto(rc: str | None, datos_catastro: dict) -> str:
    """Genera una pregunta RAG razonable cuando el usuario no especificó consulta."""
    uso = datos_catastro.get("uso") or datos_catastro.get("uso_actual") or ""
    if uso:
        return f"Clasificación de suelo, usos permitidos y edificabilidad para uso {uso}"
    if rc:
        return "Clasificación de suelo, usos permitidos, edificabilidad y condiciones urbanísticas"
    return ""
