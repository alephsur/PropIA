"""
Orquestador: coordina Catastro + PGOU + Normativa para generar informes completos.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.logger import get_logger

logger = get_logger(__name__)


async def generar_informe(req, db: AsyncSession) -> dict:
    """
    Informe completo: consulta Catastro, PGOU y Normativa en paralelo,
    luego sintetiza con Claude.
    """
    from app.integrations.catastro import post_dnprc
    from app.ai.pgou_index import consultar_pgou
    from app.services.ai_synthesis import sintetizar_informe

    datos_catastro = {}
    datos_pgou = {}
    datos_normativa = {}

    # 1. Catastro
    if req.rc:
        try:
            datos_catastro = await post_dnprc(req.provincia, req.municipio, req.rc)
        except Exception as e:
            logger.error(f"Catastro error: {e}")
            datos_catastro = {"error": str(e)}

    # 2. PGOU (si hay consulta)
    if req.consulta:
        try:
            datos_pgou = await consultar_pgou(
                req.municipio, req.provincia, req.consulta, db
            )
        except Exception as e:
            logger.warning(f"PGOU error (no indexado?): {e}")
            datos_pgou = {"error": str(e), "confianza": "baja"}

    # 3. Síntesis Claude
    informe = await sintetizar_informe(datos_catastro, datos_pgou, datos_normativa)
    return informe


async def comprobar_normativa(req, db: AsyncSession) -> dict:
    """Comprueba requisitos normativos para una operación."""
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
