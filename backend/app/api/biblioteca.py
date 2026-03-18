"""Endpoints del módulo Biblioteca de Documentos."""
import uuid
import json
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import DocumentoBiblioteca, TareaBackground
from app.services.scraper import scrape_documentos_url, DocumentoEncontrado
from app.ai.pgou_index import indexar_pdf
from app.utils.storage import guardar_pdf, leer_pdf, eliminar_pdf
from app.utils.ccaa import slug
from app.utils.logger import get_logger
import httpx

logger = get_logger(__name__)
router = APIRouter(prefix="/biblioteca", tags=["Biblioteca"])

SECCIONES_NO_INDEXAR = {"Planos", "Boletín"}


class ExplorarRequest(BaseModel):
    url: str
    municipio: str
    provincia: str


class DocumentoRequest(BaseModel):
    nombre: str
    url_origen: str
    seccion: str


class DescargarRequest(BaseModel):
    municipio: str
    provincia: str
    documentos: list[DocumentoRequest]


async def _update_tarea(db: AsyncSession, tarea_id: str, status: str, mensaje: str, detalle: dict = None):
    from sqlalchemy import text
    await db.execute(
        text("""
            UPDATE tareas_background 
            SET status = :status, mensaje = :mensaje, detalle = :detalle, updated_at = NOW()
            WHERE id = :id
        """),
        {"status": status, "mensaje": mensaje,
         "detalle": json.dumps(detalle or {}), "id": tarea_id}
    )
    await db.commit()


async def descargar_e_indexar(
    tarea_id: str,
    municipio: str,
    provincia: str,
    documentos: list[DocumentoRequest],
):
    """Tarea background: descarga e indexa documentos."""
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        procesados = 0
        errores: list[dict] = []
        total = len(documentos)

        for i, doc in enumerate(documentos):
            logger.info(f"Descargando {doc.nombre} ({i+1}/{total})")
            await _update_tarea(
                db, tarea_id, "running",
                f"Descargando {doc.nombre} ({i+1}/{total})",
                {"procesados": procesados, "total": total, "errores": errores}
            )

            # — Descarga —
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": doc.url_origen.rsplit("/", 1)[0] + "/",
                    "Accept": "application/pdf,*/*",
                }
                async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                    r = await client.get(doc.url_origen, headers=headers)
                    r.raise_for_status()
            except Exception as e:
                logger.error(f"Error descargando {doc.nombre}: {e}")
                errores.append({"nombre": doc.nombre, "fase": "descarga", "error": str(e)})
                await _update_tarea(
                    db, tarea_id, "running",
                    f"Error descargando {doc.nombre}",
                    {"procesados": procesados, "total": total, "errores": errores}
                )
                continue

            # — Guardar en disco y BD —
            try:
                ruta = await guardar_pdf(r.content, provincia, municipio, doc.nombre)
                ccaa = provincia.lower()
                doc_bd = DocumentoBiblioteca(
                    municipio=municipio,
                    provincia=provincia,
                    ccaa=ccaa,
                    nombre=doc.nombre,
                    seccion=doc.seccion,
                    ruta_local=str(ruta),
                    url_origen=doc.url_origen,
                    tamanio_bytes=len(r.content),
                    indexado=False,
                )
                db.add(doc_bd)
                await db.commit()
                await db.refresh(doc_bd)
                procesados += 1
            except Exception as e:
                logger.error(f"Error guardando {doc.nombre}: {e}")
                errores.append({"nombre": doc.nombre, "fase": "almacenamiento", "error": str(e)})
                await _update_tarea(
                    db, tarea_id, "running",
                    f"Error guardando {doc.nombre}",
                    {"procesados": procesados, "total": total, "errores": errores}
                )
                continue

            # — Indexación (fallo no impide marcar el doc como descargado) —
            if doc.seccion not in SECCIONES_NO_INDEXAR:
                await _update_tarea(
                    db, tarea_id, "running",
                    f"Indexando {doc.nombre} ({i+1}/{total})",
                    {"procesados": procesados, "total": total, "errores": errores}
                )
                try:
                    logger.info(f"Indexando {doc.nombre}")
                    await indexar_pdf(db, doc_bd.id, r.content, municipio, provincia, doc.seccion)
                    doc_bd.indexado = True
                    await db.commit()
                except Exception as e:
                    logger.error(f"Error indexando {doc.nombre}: {e}")
                    errores.append({"nombre": doc.nombre, "fase": "indexación", "error": str(e)})

        status_final = "done_with_errors" if errores else "done"
        msg_final = (
            f"Completado con {len(errores)} error{'es' if len(errores) != 1 else ''} — "
            f"{procesados}/{total} documentos descargados"
            if errores else f"Completado — {procesados}/{total} documentos descargados"
        )
        await _update_tarea(
            db, tarea_id, status_final, msg_final,
            {"procesados": procesados, "total": total, "errores": errores}
        )


@router.post("/explorar", response_model=list[DocumentoEncontrado])
async def explorar_url(body: ExplorarRequest):
    """Scraping de una URL de ayuntamiento. Devuelve lista de PDFs encontrados."""
    logger.info(f"Explorando {body.url} para {body.municipio}, {body.provincia}")
    try:
        docs = await scrape_documentos_url(body.url, body.municipio, body.provincia)
        if not docs:
            raise HTTPException(
                status_code=404,
                detail="No se encontraron documentos PDF en la URL proporcionada. "
                       "Comprueba que la URL contiene enlaces a PDFs."
            )
        return docs
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"No se pudo acceder a la URL: {str(e)}")


@router.post("/descargar")
async def descargar_documentos(
    body: DescargarRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Inicia descarga e indexación en background. Devuelve tarea_id."""
    tarea = TareaBackground(
        tipo="descarga_pdf",
        status="pending",
        municipio=body.municipio,
        provincia=body.provincia,
        detalle={"total": len(body.documentos), "procesados": 0},
        mensaje=f"Iniciando descarga de {len(body.documentos)} documentos...",
    )
    db.add(tarea)
    await db.commit()
    await db.refresh(tarea)

    logger.info(f"Iniciando descarga de {len(body.documentos)} documentos para {body.municipio}, {body.provincia}")

    background_tasks.add_task(
        descargar_e_indexar,
        str(tarea.id),
        body.municipio,
        body.provincia,
        body.documentos,
    )

    return {"tarea_id": str(tarea.id)}


@router.get("/municipio")
async def listar_municipio(
    municipio: str,
    provincia: str,
    db: AsyncSession = Depends(get_db),
):
    """Lista todos los documentos descargados para un municipio."""
    result = await db.execute(
        select(DocumentoBiblioteca).where(
            DocumentoBiblioteca.municipio == municipio,
            DocumentoBiblioteca.provincia == provincia,
        ).order_by(DocumentoBiblioteca.seccion, DocumentoBiblioteca.nombre)
    )
    docs = result.scalars().all()
    return [
        {
            "id": str(d.id),
            "nombre": d.nombre,
            "seccion": d.seccion,
            "tamanio_bytes": d.tamanio_bytes,
            "indexado": d.indexado,
            "url_origen": d.url_origen,
            "descargado_at": d.descargado_at.isoformat() if d.descargado_at else None,
        }
        for d in docs
    ]


@router.get("/documento/{documento_id}")
async def servir_documento(documento_id: str, db: AsyncSession = Depends(get_db)):
    """Sirve un PDF como stream para el visor embebido."""
    result = await db.execute(
        select(DocumentoBiblioteca).where(DocumentoBiblioteca.id == uuid.UUID(documento_id))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    try:
        contenido = await leer_pdf(doc.ruta_local)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Fichero PDF no encontrado en el servidor")

    return StreamingResponse(
        iter([contenido]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc.nombre}.pdf"'},
    )


@router.delete("/documento/{documento_id}")
async def eliminar_documento(documento_id: str, db: AsyncSession = Depends(get_db)):
    """Elimina un documento de la biblioteca."""
    result = await db.execute(
        select(DocumentoBiblioteca).where(DocumentoBiblioteca.id == uuid.UUID(documento_id))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    # Eliminar chunks del índice si estaba indexado
    if doc.indexado:
        from sqlalchemy import text
        await db.execute(
            text("DELETE FROM pgou_chunks WHERE documento_id = :id"),
            {"id": documento_id}
        )

    eliminar_pdf(doc.ruta_local)
    await db.delete(doc)
    await db.commit()

    return {"ok": True}
