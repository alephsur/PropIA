"""Endpoints del módulo Planeamiento / PGOU."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import PgouMunicipio
from app.ai.pgou_index import buscar_pgou
from app.services.ai_synthesis import consultar_pgou
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/urbanismo", tags=["Urbanismo"])


class ConsultaUrbanismo(BaseModel):
    provincia: str
    municipio: str
    rc: str | None = None
    consulta: str = "Clasificación del suelo, zonificación y usos permitidos"


@router.post("/informe")
async def informe_urbanismo(body: ConsultaUrbanismo, db: AsyncSession = Depends(get_db)):
    """Consulta el PGOU por RAG y genera informe urbanístico."""
    try:
        chunks = await buscar_pgou(db, body.municipio, body.provincia, body.consulta)
        resultado = await consultar_pgou(chunks, body.consulta, body.municipio)
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error informe urbanismo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/municipios")
async def listar_municipios_indexados(
    ccaa: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Lista municipios con documentos PGOU indexados."""
    query = select(PgouMunicipio)
    if ccaa:
        query = query.where(PgouMunicipio.ccaa == ccaa.lower())
    result = await db.execute(query.order_by(PgouMunicipio.municipio))
    municipios = result.scalars().all()
    return [
        {
            "municipio": m.municipio,
            "provincia": m.provincia,
            "ccaa": m.ccaa,
            "total_chunks": m.total_chunks,
            "ultimo_indexado": m.ultimo_indexado.isoformat() if m.ultimo_indexado else None,
        }
        for m in municipios
    ]
