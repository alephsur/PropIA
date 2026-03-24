"""Endpoints del módulo Análisis de Documentos."""
import base64
import io
import pdfplumber
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.services.ai_synthesis import analizar_documento, analizar_documento_texto
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/documentos", tags=["Documentos"])

TIPOS_PERMITIDOS = {"application/pdf", "image/jpeg", "image/png", "image/webp"}


def _extraer_texto_pdf(contenido: bytes) -> str:
    """Extrae texto de un PDF. Devuelve texto concatenado de todas las páginas."""
    paginas = []
    with pdfplumber.open(io.BytesIO(contenido)) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text() or ""
            if texto.strip():
                paginas.append(texto)
    return "\n\n".join(paginas)


@router.post("/analizar")
async def analizar(
    documento: UploadFile = File(...),
    consulta: str | None = Form(None),
):
    """Analiza un documento (PDF o imagen) con el LLM configurado."""
    if documento.content_type not in TIPOS_PERMITIDOS:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de fichero no soportado. Use: {', '.join(TIPOS_PERMITIDOS)}"
        )

    contenido = await documento.read()

    try:
        if documento.content_type == "application/pdf":
            # PDFs: extraer texto y enviar como string — compatible con todos los proveedores
            texto = _extraer_texto_pdf(contenido)
            if not texto.strip():
                raise HTTPException(
                    status_code=422,
                    detail="No se pudo extraer texto del PDF. El documento puede ser un escaneado sin OCR."
                )
            resultado = await analizar_documento_texto(texto, consulta)
        else:
            # Imágenes: enviar como bloques multimodal (requiere modelo de visión)
            contenido_b64 = base64.standard_b64encode(contenido).decode()
            resultado = await analizar_documento(contenido_b64, documento.content_type, consulta)

        return resultado
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analizando documento: {e}")
        raise HTTPException(status_code=500, detail=str(e))
