"""Indexación y consulta RAG del PGOU.

Chunking semántico: respeta los límites de artículos/secciones del texto legal.
Cada chunk almacena el artículo completo (para el LLM) pero embebe solo un prefijo
(título + inicio) para respetar la ventana de 512 tokens de mxbai-embed-large.
"""
import re
import pdfplumber
import io
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.db.models import PgouChunk, PgouMunicipio
from app.ai.embeddings import embed_texto, embed_batch
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ── Configuración ─────────────────────────────────────────────
# mxbai-embed-large: 512 tokens. Español legal ~1.5-2 tok/char.
_MAX_EMBED_CHARS = 400

# Límites para chunks semánticos (artículos/secciones)
_MAX_CHUNK_CHARS = 1500   # Artículos > esto se subdividen por párrafos
_MIN_CHUNK_CHARS = 80     # Fragmentos menores se fusionan con el siguiente

# Fallback para texto sin estructura legal (memorias, estudios, etc.)
_FALLBACK_CHUNK_SIZE = 800
_FALLBACK_OVERLAP = 150

# Regex para límites de artículos en texto legal español
_ARTICULO_RE = re.compile(
    r'(?:^|\n)\s*'
    r'('
    r'Art(?:ículo|\.)\s*[\d]+(?:[\.\-]\d+)*'       # Artículo 1, Art. 4.3.1
    r'|CAPÍTULO\s+[IVXLCDM\d]+[\.\-ºª]?'          # CAPÍTULO I, CAPÍTULO 1
    r'|SECCIÓN\s+[IVXLCDM\d\.\-ºª]+'              # SECCIÓN 1ª
    r'|TÍTULO\s+[IVXLCDM\d]+[\.\-ºª]?'            # TÍTULO I
    r'|Disposición\s+(?:adicional|transitoria|final|derogatoria)\s+\w+'
    r')',
    re.IGNORECASE
)


# ── Extracción de texto ──────────────────────────────────────

def _extraer_texto_por_pagina(contenido: bytes) -> list[tuple[int, str]]:
    """Extrae texto de un PDF página a página. Devuelve [(nº_página, texto), ...]."""
    try:
        with pdfplumber.open(io.BytesIO(contenido)) as pdf:
            paginas = []
            for i, pagina in enumerate(pdf.pages, start=1):
                texto = pagina.extract_text() or ""
                paginas.append((i, texto))

            total_chars = sum(len(t) for _, t in paginas)
            chars_por_pag = total_chars / max(len(pdf.pages), 1)
            if chars_por_pag < 80:
                logger.info("PDF con poco texto, activando OCR")
                return _ocr_pdf_por_pagina(contenido)

            return paginas
    except Exception as e:
        logger.error(f"Error extrayendo texto PDF: {e}")
        return []


def _ocr_pdf_por_pagina(contenido: bytes) -> list[tuple[int, str]]:
    """OCR página a página para PDFs escaneados."""
    try:
        import pytesseract
        import fitz
        from PIL import Image
        doc = fitz.open(stream=contenido, filetype="pdf")
        paginas = []
        for i, pagina in enumerate(doc, start=1):
            pix = pagina.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            texto = pytesseract.image_to_string(img, lang="spa")
            paginas.append((i, texto))
        return paginas
    except Exception as e:
        logger.error(f"Error en OCR: {e}")
        return []


# ── Chunking semántico ────────────────────────────────────────

def _pagina_en_offset(offset: int, page_offsets: list[tuple[int, int]]) -> int:
    """Dado un offset de carácter en el texto completo, devuelve el nº de página."""
    pagina = 1
    for start, pag in page_offsets:
        if start <= offset:
            pagina = pag
        else:
            break
    return pagina


def _extraer_titulo(texto: str) -> str:
    """Extrae la primera línea significativa como título del chunk."""
    for linea in texto.split("\n"):
        linea = linea.strip()
        if len(linea) > 5:
            return linea[:150]
    return ""


def _subdividir_articulo(
    texto: str,
    titulo_base: str,
    pag_inicio: int,
    pag_fin: int,
) -> list[dict]:
    """Subdivide un artículo largo en chunks por párrafos, manteniendo el título."""
    parrafos = re.split(r'\n\s*\n', texto)

    chunks = []
    buffer = ""
    for parrafo in parrafos:
        parrafo = parrafo.strip()
        if not parrafo:
            continue

        if len(buffer) + len(parrafo) > _MAX_CHUNK_CHARS and buffer:
            num = len(chunks) + 1
            chunks.append({
                "titulo": f"{titulo_base} (parte {num})",
                "contenido": buffer.strip(),
                "pagina_inicio": pag_inicio,
                "pagina_fin": pag_fin,
            })
            buffer = parrafo + "\n\n"
        else:
            buffer += parrafo + "\n\n"

    if buffer.strip():
        num = len(chunks) + 1
        titulo = f"{titulo_base} (parte {num})" if chunks else titulo_base
        chunks.append({
            "titulo": titulo,
            "contenido": buffer.strip(),
            "pagina_inicio": pag_inicio,
            "pagina_fin": pag_fin,
        })

    return chunks


def _chunk_por_articulos(paginas: list[tuple[int, str]]) -> list[dict]:
    """Divide el texto respetando límites de artículos/secciones.

    Retorna lista de dicts con claves: titulo, contenido, pagina_inicio, pagina_fin.
    """
    if not paginas:
        return []

    # Construir texto completo con mapa de offsets por página
    texto_completo = ""
    page_offsets: list[tuple[int, int]] = []
    for page_num, page_text in paginas:
        page_offsets.append((len(texto_completo), page_num))
        texto_completo += page_text + "\n"

    if not texto_completo.strip():
        return []

    # Detectar artículos
    matches = list(_ARTICULO_RE.finditer(texto_completo))

    if len(matches) < 3:
        logger.info(f"Solo {len(matches)} artículos detectados, usando chunking por párrafos")
        return _chunk_por_parrafos(texto_completo, page_offsets)

    logger.info(f"Detectados {len(matches)} artículos/secciones en el documento")

    chunks: list[dict] = []

    # Si hay texto antes del primer artículo (preámbulo), crear un chunk
    if matches[0].start(1) > _MIN_CHUNK_CHARS:
        preambulo = texto_completo[:matches[0].start(1)].strip()
        if preambulo:
            pag = _pagina_en_offset(0, page_offsets)
            chunks.append({
                "titulo": _extraer_titulo(preambulo) or "Preámbulo",
                "contenido": preambulo,
                "pagina_inicio": pag,
                "pagina_fin": pag,
            })

    for i, match in enumerate(matches):
        inicio = match.start(1)
        fin = matches[i + 1].start(1) if i + 1 < len(matches) else len(texto_completo)
        texto_seccion = texto_completo[inicio:fin].strip()

        if not texto_seccion:
            continue

        titulo = _extraer_titulo(texto_seccion)
        pag_inicio = _pagina_en_offset(inicio, page_offsets)
        pag_fin = _pagina_en_offset(max(inicio, fin - 1), page_offsets)

        if len(texto_seccion) > _MAX_CHUNK_CHARS:
            sub_chunks = _subdividir_articulo(texto_seccion, titulo, pag_inicio, pag_fin)
            chunks.extend(sub_chunks)
        elif len(texto_seccion) < _MIN_CHUNK_CHARS and chunks:
            chunks[-1]["contenido"] += "\n\n" + texto_seccion
            chunks[-1]["pagina_fin"] = pag_fin
        else:
            chunks.append({
                "titulo": titulo,
                "contenido": texto_seccion,
                "pagina_inicio": pag_inicio,
                "pagina_fin": pag_fin,
            })

    return chunks


def _chunk_por_parrafos(texto: str, page_offsets: list[tuple[int, int]]) -> list[dict]:
    """Fallback: chunking por párrafos para texto sin estructura legal clara."""
    parrafos = re.split(r'\n\s*\n', texto)

    chunks: list[dict] = []
    buffer = ""
    buffer_start = 0

    for parrafo in parrafos:
        parrafo = parrafo.strip()
        if not parrafo:
            continue

        if len(buffer) + len(parrafo) > _FALLBACK_CHUNK_SIZE and buffer:
            pag_inicio = _pagina_en_offset(buffer_start, page_offsets)
            pag_fin = _pagina_en_offset(buffer_start + len(buffer), page_offsets)
            chunks.append({
                "titulo": _extraer_titulo(buffer),
                "contenido": buffer.strip(),
                "pagina_inicio": pag_inicio,
                "pagina_fin": pag_fin,
            })
            # Solapamiento: incluir el último párrafo del chunk anterior
            overlap_text = buffer.rsplit("\n\n", 1)[-1] if "\n\n" in buffer else ""
            buffer_start = buffer_start + len(buffer) - len(overlap_text)
            buffer = overlap_text + "\n\n" + parrafo + "\n\n" if overlap_text else parrafo + "\n\n"
        else:
            if not buffer:
                pos = texto.find(parrafo, buffer_start)
                if pos >= 0:
                    buffer_start = pos
            buffer += parrafo + "\n\n"

    if buffer.strip():
        pag_inicio = _pagina_en_offset(buffer_start, page_offsets)
        pag_fin = _pagina_en_offset(buffer_start + len(buffer), page_offsets)
        chunks.append({
            "titulo": _extraer_titulo(buffer),
            "contenido": buffer.strip(),
            "pagina_inicio": pag_inicio,
            "pagina_fin": pag_fin,
        })

    return chunks


def _texto_para_embedding(chunk: dict) -> str:
    """Texto optimizado para embedding: título + inicio del contenido.

    El embedding captura la semántica del título (muy discriminativo en texto legal)
    más el inicio del artículo. El LLM recibe el contenido completo por separado.
    """
    titulo = chunk.get("titulo", "")
    contenido = chunk.get("contenido", "")

    if titulo and titulo != contenido[:len(titulo)]:
        prefijo = titulo + "\n\n"
        chars_contenido = max(_MAX_EMBED_CHARS - len(prefijo), 100)
        return prefijo + contenido[:chars_contenido]
    return contenido[:_MAX_EMBED_CHARS]


# ── Indexación ────────────────────────────────────────────────

async def indexar_pdf(
    db: AsyncSession,
    documento_id: uuid.UUID,
    contenido: bytes,
    municipio: str,
    provincia: str,
    seccion: str = "Otros",
) -> int:
    """Indexa un PDF: extrae artículos, genera embeddings, guarda en BD.

    Devuelve número de chunks creados.
    """
    paginas = _extraer_texto_por_pagina(contenido)
    if not paginas:
        logger.warning(f"PDF vacío o sin texto: documento {documento_id}")
        return 0

    chunks_estructurados = _chunk_por_articulos(paginas)
    if not chunks_estructurados:
        logger.warning(f"No se generaron chunks: documento {documento_id}")
        return 0

    logger.info(
        f"Documento {seccion}: {len(chunks_estructurados)} chunks "
        f"(de {sum(len(t) for _, t in paginas)} chars totales)"
    )

    # Generar embeddings del texto optimizado (título + inicio)
    textos_embed = [_texto_para_embedding(c) for c in chunks_estructurados]
    embeddings = await embed_batch(textos_embed)

    # Guardar chunks con metadatos enriquecidos
    for posicion, (chunk_data, embedding) in enumerate(zip(chunks_estructurados, embeddings)):
        chunk = PgouChunk(
            municipio=municipio,
            provincia=provincia,
            documento_id=documento_id,
            seccion=seccion,
            articulo=chunk_data["titulo"] or None,
            contenido=chunk_data["contenido"],
            metadatos={
                "seccion": seccion,
                "posicion": posicion,
                "total_chunks": len(chunks_estructurados),
                "pagina_inicio": chunk_data["pagina_inicio"],
                "pagina_fin": chunk_data["pagina_fin"],
            },
        )
        db.add(chunk)
        await db.flush()
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
        municipio_obj.total_chunks += len(chunks_estructurados)
        from datetime import datetime
        municipio_obj.ultimo_indexado = datetime.utcnow()
    else:
        ccaa = provincia.lower()
        db.add(PgouMunicipio(
            municipio=municipio,
            provincia=provincia,
            ccaa=ccaa,
            total_chunks=len(chunks_estructurados),
        ))

    await db.commit()
    logger.info(f"Indexados {len(chunks_estructurados)} chunks para {municipio}, {provincia}")
    return len(chunks_estructurados)


# ── Búsqueda RAG ─────────────────────────────────────────────

async def buscar_pgou(
    db: AsyncSession,
    municipio: str,
    provincia: str,
    pregunta: str,
    top_k: int = 10,
) -> list[dict]:
    """Búsqueda semántica en el índice PGOU con expansión de contexto adyacente.

    1. Recupera los top_k chunks más similares
    2. Para cada resultado, trae los chunks adyacentes (±1 posición) del mismo documento
    3. Ordena por documento + posición para que el LLM lea texto secuencial
    """
    result = await db.execute(
        select(PgouMunicipio).where(
            PgouMunicipio.municipio == municipio,
            PgouMunicipio.provincia == provincia,
        )
    )
    if not result.scalar_one_or_none():
        raise ValueError(f"No hay documentos indexados para {municipio}. "
                         f"Añade los documentos desde el módulo Biblioteca.")

    embedding = await embed_texto(pregunta)

    # 1. Top-k por similitud semántica
    rows = await db.execute(
        text("""
            SELECT id, contenido, seccion, articulo, metadatos, documento_id,
                   1 - (embedding <=> CAST(:emb AS vector)) AS similitud
            FROM pgou_chunks
            WHERE municipio = :municipio AND provincia = :provincia
            ORDER BY embedding <=> CAST(:emb AS vector)
            LIMIT :k
        """),
        {"emb": str(embedding), "municipio": municipio, "provincia": provincia, "k": top_k}
    )

    resultados = []
    seen_ids = set()
    for row in rows:
        seen_ids.add(str(row.id))
        resultados.append({
            "contenido": row.contenido,
            "seccion": row.seccion,
            "articulo": row.articulo,
            "similitud": float(row.similitud),
            "metadatos": row.metadatos or {},
            "_doc_id": str(row.documento_id),
            "_posicion": (row.metadatos or {}).get("posicion", 0),
        })

    # 2. Expandir con chunks adyacentes (±1 posición)
    existing_keys = {(r["_doc_id"], r["_posicion"]) for r in resultados}
    expansion_needed: list[tuple[str, int]] = []
    for r in resultados:
        for delta in (-1, 1):
            pos = r["_posicion"] + delta
            key = (r["_doc_id"], pos)
            if pos >= 0 and key not in existing_keys:
                expansion_needed.append(key)
                existing_keys.add(key)

    if expansion_needed:
        params: dict = {"municipio": municipio, "provincia": provincia}
        conditions = []
        for i, (doc_id, pos) in enumerate(expansion_needed):
            conditions.append(
                f"(documento_id = :doc_{i} AND (metadatos->>'posicion')::int = :pos_{i})"
            )
            params[f"doc_{i}"] = doc_id
            params[f"pos_{i}"] = pos

        adj_rows = await db.execute(
            text(f"""
                SELECT id, contenido, seccion, articulo, metadatos, documento_id
                FROM pgou_chunks
                WHERE municipio = :municipio AND provincia = :provincia
                AND ({' OR '.join(conditions)})
            """),
            params,
        )
        for row in adj_rows:
            if str(row.id) not in seen_ids:
                resultados.append({
                    "contenido": row.contenido,
                    "seccion": row.seccion,
                    "articulo": row.articulo,
                    "similitud": 0.0,
                    "metadatos": row.metadatos or {},
                    "_doc_id": str(row.documento_id),
                    "_posicion": (row.metadatos or {}).get("posicion", 0),
                })

    # 3. Ordenar por documento y posición → texto secuencial para el LLM
    resultados.sort(key=lambda r: (r["_doc_id"], r["_posicion"]))

    return [
        {
            "contenido": r["contenido"],
            "seccion": r["seccion"],
            "articulo": r["articulo"],
            "similitud": r["similitud"],
            "metadatos": r["metadatos"],
        }
        for r in resultados
    ]
