"""Indexación y consulta RAG del PGOU."""
import pdfplumber
import io
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.db.models import PgouChunk, PgouMunicipio, DocumentoBiblioteca
from app.ai.embeddings import embed_texto, embed_batch
from app.utils.logger import get_logger
import uuid

logger = get_logger(__name__)

# mxbai-embed-large tiene contexto de 512 tokens.
# Texto legal en español ~ 1,5-2 tokens/carácter → límite seguro ~400 chars.
CHUNK_SIZE = 400
CHUNK_OVERLAP = 80


def _chunk_texto(texto: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Divide texto en chunks con solapamiento."""
    chunks = []
    inicio = 0
    while inicio < len(texto):
        fin = min(inicio + size, len(texto))
        chunks.append(texto[inicio:fin])
        inicio += size - overlap
    return chunks


def _extraer_texto_pdf(contenido: bytes) -> str:
    """Extrae texto de un PDF, con fallback a OCR."""
    try:
        with pdfplumber.open(io.BytesIO(contenido)) as pdf:
            textos = []
            for pagina in pdf.pages:
                texto = pagina.extract_text() or ""
                textos.append(texto)
            texto_total = "\n".join(textos)

            # Si muy poco texto, intentar OCR
            chars_por_pagina = len(texto_total) / max(len(pdf.pages), 1)
            if chars_por_pagina < 80:
                logger.info("PDF con poco texto, activando OCR")
                texto_total = _ocr_pdf(contenido)

            return texto_total
    except Exception as e:
        logger.error(f"Error extrayendo texto PDF: {e}")
        return ""


def _ocr_pdf(contenido: bytes) -> str:
    """OCR para PDFs escaneados usando pytesseract."""
    try:
        import pytesseract
        import fitz  # pymupdf
        doc = fitz.open(stream=contenido, filetype="pdf")
        textos = []
        for pagina in doc:
            pix = pagina.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
            from PIL import Image
            img = Image.open(io.BytesIO(img_bytes))
            texto = pytesseract.image_to_string(img, lang="spa")
            textos.append(texto)
        return "\n".join(textos)
    except Exception as e:
        logger.error(f"Error en OCR: {e}")
        return ""


async def indexar_pdf(
    db: AsyncSession,
    documento_id: uuid.UUID,
    contenido: bytes,
    municipio: str,
    provincia: str,
    seccion: str = "Otros",
) -> int:
    """Indexa un PDF y guarda los chunks en la BD. Devuelve número de chunks."""
    texto = _extraer_texto_pdf(contenido)
    if not texto.strip():
        logger.warning(f"PDF vacío o sin texto: documento {documento_id}")
        return 0

    chunks = _chunk_texto(texto)
    if not chunks:
        return 0

    # Generar embeddings en batch
    embeddings = await embed_batch(chunks)

    # Guardar chunks
    for chunk_texto, embedding in zip(chunks, embeddings):
        chunk = PgouChunk(
            municipio=municipio,
            provincia=provincia,
            documento_id=documento_id,
            seccion=seccion,
            contenido=chunk_texto,
            metadatos={"seccion": seccion},
        )
        db.add(chunk)
        await db.flush()
        # Actualizar embedding con pgvector
        await db.execute(
            text("UPDATE pgou_chunks SET embedding = CAST(:emb AS vector) WHERE id = :id"),
            {"emb": str(embedding), "id": str(chunk.id)}
        )

    await db.commit()

    # Actualizar/crear registro de municipio indexado
    result = await db.execute(
        select(PgouMunicipio).where(
            PgouMunicipio.municipio == municipio,
            PgouMunicipio.provincia == provincia,
        )
    )
    municipio_obj = result.scalar_one_or_none()
    if municipio_obj:
        municipio_obj.total_chunks += len(chunks)
        from datetime import datetime
        municipio_obj.ultimo_indexado = datetime.utcnow()
    else:
        ccaa = provincia.lower()
        db.add(PgouMunicipio(
            municipio=municipio,
            provincia=provincia,
            ccaa=ccaa,
            total_chunks=len(chunks),
        ))

    await db.commit()
    logger.info(f"Indexados {len(chunks)} chunks para {municipio}, {provincia}")
    return len(chunks)


async def buscar_pgou(
    db: AsyncSession,
    municipio: str,
    provincia: str,
    pregunta: str,
    top_k: int = 6,
) -> list[dict]:
    """Búsqueda semántica en el índice PGOU."""
    # Verificar que existe índice
    result = await db.execute(
        select(PgouMunicipio).where(
            PgouMunicipio.municipio == municipio,
            PgouMunicipio.provincia == provincia,
        )
    )
    if not result.scalar_one_or_none():
        raise ValueError(f"No hay documentos indexados para {municipio}. "
                         f"Añade los documentos desde el módulo Biblioteca.")

    # Embedding de la pregunta
    embedding = await embed_texto(pregunta)

    # Búsqueda por similitud coseno
    rows = await db.execute(
        text("""
            SELECT id, contenido, seccion, articulo, metadatos,
                   1 - (embedding <=> CAST(:emb AS vector)) as similitud
            FROM pgou_chunks
            WHERE municipio = :municipio AND provincia = :provincia
            ORDER BY embedding <=> CAST(:emb AS vector)
            LIMIT :k
        """),
        {"emb": str(embedding), "municipio": municipio, "provincia": provincia, "k": top_k}
    )

    return [
        {
            "contenido": row.contenido,
            "seccion": row.seccion,
            "articulo": row.articulo,
            "similitud": float(row.similitud),
            "metadatos": row.metadatos,
        }
        for row in rows
    ]
