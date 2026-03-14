"""Endpoints del módulo Análisis de Documentos."""
import base64
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.services.ai_synthesis import analizar_documento
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/documentos", tags=["Documentos"])

TIPOS_PERMITIDOS = {"application/pdf", "image/jpeg", "image/png", "image/webp"}


@router.post("/analizar")
async def analizar(
    documento: UploadFile = File(...),
    consulta: str | None = Form(None),
):
    """Analiza un documento (PDF o imagen) con Claude vision."""
    if documento.content_type not in TIPOS_PERMITIDOS:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de fichero no soportado. Use: {', '.join(TIPOS_PERMITIDOS)}"
        )

    contenido = await documento.read()
    contenido_b64 = base64.standard_b64encode(contenido).decode()

    try:
        resultado = await analizar_documento(contenido_b64, documento.content_type, consulta)
        return resultado
    except Exception as e:
        logger.error(f"Error analizando documento: {e}")
        raise HTTPException(status_code=500, detail=str(e))
