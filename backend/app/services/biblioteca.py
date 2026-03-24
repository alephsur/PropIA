"""
Servicio de la Biblioteca de Documentos.
Gestiona descarga, indexación y consulta de PDFs por municipio.
"""
import uuid
from typing import Optional

import httpx
from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentoBiblioteca, TareaBackground
from app.utils.ccaa import get_ccaa, slug
from app.utils.logger import get_logger
from app.utils.storage import save_pdf, read_pdf, delete_pdf

logger = get_logger(__name__)

# Secciones que NO se indexan para IA
SECCIONES_NO_INDEXAR = {"Planos", "Boletín"}


async def _update_tarea(
    db: AsyncSession,
    tarea_id: uuid.UUID,
    status: str,
    mensaje: str,
    detalle: Optional[dict] = None,
):
    result = await db.execute(
        select(TareaBackground).where(TareaBackground.id == tarea_id)
    )
    tarea = result.scalar_one_or_none()
    if tarea:
        tarea.status = status
        tarea.mensaje = mensaje
        if detalle:
            tarea.detalle = detalle
        await db.commit()


async def iniciar_descarga(req, background_tasks: BackgroundTasks, db: AsyncSession) -> uuid.UUID:
    """Crea la tarea en BD y la encola como BackgroundTask."""
    tarea = TareaBackground(
        tipo="descarga_pdf",
        status="pending",
        municipio=req.municipio,
        provincia=req.provincia,
        detalle={"total": len(req.documentos), "procesados": 0},
    )
    db.add(tarea)
    await db.commit()
    await db.refresh(tarea)

    background_tasks.add_task(
        descargar_e_indexar,
        tarea_id=tarea.id,
        municipio=req.municipio,
        provincia=req.provincia,
        documentos=req.documentos,
    )
    return tarea.id


async def descargar_e_indexar(
    tarea_id: uuid.UUID,
    municipio: str,
    provincia: str,
    documentos: list,
):
    """
    Tarea background: descarga PDFs, los registra en BD y los indexa.
    Usa su propia sesión DB (no puede recibir sesión de la request).
    """
    from app.db.session import AsyncSessionLocal
    from app.ai.pgou_index import indexar_pdf

    async with AsyncSessionLocal() as db:
        try:
            await _update_tarea(db, tarea_id, "running", "Iniciando descarga...",
                                {"total": len(documentos), "procesados": 0})

            ccaa = get_ccaa(provincia)
            procesados = 0

            for i, doc in enumerate(documentos):
                await _update_tarea(
                    db, tarea_id, "running",
                    f"Descargando {doc.nombre} ({i + 1}/{len(documentos)})",
                    {"total": len(documentos), "procesados": i},
                )

                try:
                    # Check if already downloaded
                    existing = await db.execute(
                        select(DocumentoBiblioteca).where(
                            DocumentoBiblioteca.municipio == municipio,
                            DocumentoBiblioteca.provincia == provincia,
                            DocumentoBiblioteca.nombre == doc.nombre,
                        )
                    )
                    if existing.scalar_one_or_none():
                        logger.info(f"Documento ya existe, omitiendo: {doc.nombre}")
                        procesados += 1
                        continue

                    # Download PDF
                    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                        r = await client.get(doc.url_origen)
                        r.raise_for_status()
                        content = r.content

                    # Save to storage
                    ruta = await save_pdf(content, provincia, municipio, doc.nombre)

                    # Register in DB
                    doc_bd = DocumentoBiblioteca(
                        municipio=municipio,
                        provincia=provincia,
                        ccaa=ccaa,
                        nombre=doc.nombre,
                        seccion=doc.seccion,
                        ruta_local=str(ruta),
                        url_origen=doc.url_origen,
                        tamanio_bytes=len(content),
                        indexado=False,
                    )
                    db.add(doc_bd)
                    await db.commit()
                    await db.refresh(doc_bd)

                    # Index if semantically valuable
                    if doc.seccion not in SECCIONES_NO_INDEXAR:
                        await _update_tarea(
                            db, tarea_id, "running",
                            f"Indexando {doc.nombre}...",
                            {"total": len(documentos), "procesados": i},
                        )
                        await indexar_pdf(db, doc_bd.id, content, municipio, provincia, doc.seccion)
                        doc_bd.indexado = True
                        await db.commit()

                    procesados += 1

                except Exception as e:
                    logger.error(f"Error procesando {doc.nombre}: {e}")
                    await db.rollback()
                    await _update_tarea(
                        db, tarea_id, "running",
                        f"Error en {doc.nombre}: {str(e)[:100]}",
                        {"total": len(documentos), "procesados": i, "ultimo_error": str(e)},
                    )
                    continue

            await _update_tarea(
                db, tarea_id, "done",
                f"Completado: {procesados}/{len(documentos)} documentos procesados",
                {"total": len(documentos), "procesados": procesados},
            )

        except Exception as e:
            logger.error(f"Error fatal en tarea background {tarea_id}: {e}")
            try:
                await db.rollback()
                await _update_tarea(db, tarea_id, "error", f"Error fatal: {str(e)[:200]}")
            except Exception:
                pass


async def listar_documentos_municipio(
    municipio: str, provincia: str, db: AsyncSession
) -> list[DocumentoBiblioteca]:
    result = await db.execute(
        select(DocumentoBiblioteca)
        .where(
            DocumentoBiblioteca.municipio == municipio,
            DocumentoBiblioteca.provincia == provincia,
        )
        .order_by(DocumentoBiblioteca.descargado_at.desc())
    )
    return list(result.scalars().all())


async def get_documento_stream(doc_id: uuid.UUID, db: AsyncSession) -> StreamingResponse:
    result = await db.execute(
        select(DocumentoBiblioteca).where(DocumentoBiblioteca.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    content = read_pdf(doc.ruta_local)
    nombre_safe = doc.nombre.replace('"', "").replace("'", "")

    return StreamingResponse(
        iter([content]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{nombre_safe}.pdf"',
            "Content-Length": str(len(content)),
        },
    )


async def eliminar_documento(doc_id: uuid.UUID, db: AsyncSession):
    result = await db.execute(
        select(DocumentoBiblioteca).where(DocumentoBiblioteca.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    # Delete from pgou_chunks if indexed
    if doc.indexado:
        from sqlalchemy import delete
        from app.db.models import PgouChunk
        await db.execute(
            delete(PgouChunk).where(PgouChunk.documento_id == doc_id)
        )

    # Delete from filesystem
    delete_pdf(doc.ruta_local)

    # Delete from DB
    await db.delete(doc)
    await db.commit()
