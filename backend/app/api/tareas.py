"""Endpoint de estado de tareas background."""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid
from app.db.session import get_db
from app.db.models import TareaBackground

router = APIRouter(tags=["Tareas"])


@router.get("/tareas/{tarea_id}")
async def get_tarea(tarea_id: str, db: AsyncSession = Depends(get_db)):
    """Devuelve el estado de una tarea background."""
    try:
        uid = uuid.UUID(tarea_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de tarea inválido")

    result = await db.execute(
        select(TareaBackground).where(TareaBackground.id == uid)
    )
    tarea = result.scalar_one_or_none()
    if not tarea:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    return {
        "id": str(tarea.id),
        "tipo": tarea.tipo,
        "status": tarea.status,
        "municipio": tarea.municipio,
        "provincia": tarea.provincia,
        "mensaje": tarea.mensaje,
        "detalle": tarea.detalle,
        "created_at": tarea.created_at.isoformat() if tarea.created_at else None,
        "updated_at": tarea.updated_at.isoformat() if tarea.updated_at else None,
    }
