"""Endpoints del módulo Normativa."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.integrations.boe import buscar_boe, buscar_boc, buscar_bopa
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/normativa", tags=["Normativa"])


@router.get("/boc")
async def normativa_boc(q: str, fecha_desde: str | None = None):
    """Búsqueda en el BOC de Cantabria."""
    try:
        return await buscar_boc(q, fecha_desde)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/bopa")
async def normativa_bopa(q: str, fecha_desde: str | None = None):
    """Búsqueda en el BOPA de Asturias."""
    try:
        return await buscar_bopa(q, fecha_desde)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/boe")
async def normativa_boe(q: str, fecha_desde: str | None = None):
    """Búsqueda en la API del BOE."""
    try:
        return await buscar_boe(q, fecha_desde)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
