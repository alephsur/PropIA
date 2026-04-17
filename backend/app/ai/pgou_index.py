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
from app.db.models import PgouChunk, PgouMunicipio, PgouFichaAA, PgouRefCatastral
from app.ai.embeddings import embed_texto, embed_batch, _mean_pool
from app.ai.fichas_aa_parser import parsear_fichas_pdf, rc_a_manzana_parcela
from app.ai import llm_client
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ── Configuración ─────────────────────────────────────────────
# Tamaño máximo del prefijo para embedding del chunk.
# Con sliding window en embeddings.py, textos largos se ventanean y promedian:
# aquí enviamos el título + contenido completo (hasta 4000 chars) para capturar
# semántica de todo el artículo, no solo del inicio.
_MAX_EMBED_CHARS = 4000

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
    """Extrae texto de un PDF página a página. Devuelve [(nº_página, texto), ...].

    Además del flujo de texto que produce `extract_text()`, se anexan las tablas
    de cada página como pares "Etiqueta: Valor". Esto es crítico para fichas AA,
    donde los parámetros urbanísticos (edificabilidad, viviendas, cesiones,
    instrumentos, plazos) viven en tablas de 2 columnas que `extract_text()`
    aplana y desordena — perdiendo la relación etiqueta↔valor.
    """
    try:
        with pdfplumber.open(io.BytesIO(contenido)) as pdf:
            paginas = []
            for i, pagina in enumerate(pdf.pages, start=1):
                texto = pagina.extract_text() or ""
                tablas_texto = _extraer_tablas_pagina(pagina)
                if tablas_texto:
                    texto = f"{texto}\n\n[TABLAS]\n{tablas_texto}"
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


def _extraer_tablas_pagina(pagina) -> str:
    """Formatea las tablas de una página como texto recuperable por regex/LLM.

    - Tabla de 2 columnas → una línea "clave: valor" por fila (caso típico de fichas).
    - Tablas con más columnas → filas unidas por " | ".
    Devuelve "" si no hay tablas o falla la extracción.
    """
    try:
        tablas = pagina.extract_tables() or []
    except Exception:
        return ""
    lineas: list[str] = []
    for tabla in tablas:
        for fila in tabla or []:
            celdas = [(c or "").strip().replace("\n", " ") for c in fila]
            celdas = [c for c in celdas if c]
            if not celdas:
                continue
            if len(celdas) == 2:
                lineas.append(f"{celdas[0]}: {celdas[1]}")
            else:
                lineas.append(" | ".join(celdas))
    return "\n".join(lineas)


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
    """Texto para embedding: título + contenido completo (hasta _MAX_EMBED_CHARS).

    El ventaneo/pooling lo hace embeddings.embed_batch — aquí enviamos el
    contenido íntegro para que todas las secciones del artículo queden
    representadas en el vector final, no solo el prefijo.
    """
    titulo = chunk.get("titulo", "")
    contenido = chunk.get("contenido", "")

    if titulo and titulo != contenido[:len(titulo)]:
        texto = f"{titulo}\n\n{contenido}"
    else:
        texto = contenido
    return texto[:_MAX_EMBED_CHARS]


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

    Si la sección es de fichas de desarrollo, también ejecuta el parser estructurado
    y guarda los datos en pgou_fichas_aa + pgou_refs_catastrales.

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

    # Guardar chunks con metadatos enriquecidos, poblando 'pagina' directamente
    for posicion, (chunk_data, embedding) in enumerate(zip(chunks_estructurados, embeddings)):
        chunk = PgouChunk(
            municipio=municipio,
            provincia=provincia,
            documento_id=documento_id,
            seccion=seccion,
            articulo=chunk_data["titulo"] or None,
            contenido=chunk_data["contenido"],
            pagina=chunk_data["pagina_inicio"],
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

    # Obtener/crear el municipio y guardar su ID
    municipio_obj = await _obtener_o_crear_municipio(db, municipio, provincia, len(chunks_estructurados))

    # Si es un documento de fichas de desarrollo, parsear y almacenar estructura catastral
    if _es_seccion_fichas(seccion):
        await _indexar_fichas_aa(db, paginas, documento_id, municipio_obj.id, municipio, provincia)

    logger.info(f"Indexados {len(chunks_estructurados)} chunks para {municipio}, {provincia}")
    return len(chunks_estructurados)


def _es_seccion_fichas(seccion: str) -> bool:
    """Determina si la sección contiene fichas de desarrollo del PGOU."""
    seccion_lower = seccion.lower()
    return any(
        kw in seccion_lower
        for kw in ("ficha", "actuacion", "actuación", "desarrollo")
    )


async def _obtener_o_crear_municipio(
    db: AsyncSession,
    municipio: str,
    provincia: str,
    nuevos_chunks: int,
) -> PgouMunicipio:
    """Obtiene o crea el registro de municipio y actualiza el contador de chunks."""
    from datetime import datetime
    result = await db.execute(
        select(PgouMunicipio).where(
            PgouMunicipio.municipio == municipio,
            PgouMunicipio.provincia == provincia,
        )
    )
    municipio_obj = result.scalar_one_or_none()
    if municipio_obj:
        municipio_obj.total_chunks += nuevos_chunks
        municipio_obj.ultimo_indexado = datetime.utcnow()
    else:
        municipio_obj = PgouMunicipio(
            municipio=municipio,
            provincia=provincia,
            ccaa=provincia.lower(),
            total_chunks=nuevos_chunks,
        )
        db.add(municipio_obj)
        await db.flush()  # necesitamos el ID antes de usarlo en fichas

    await db.commit()
    return municipio_obj


async def _indexar_fichas_aa(
    db: AsyncSession,
    paginas: list[tuple[int, str]],
    documento_id: uuid.UUID,
    municipio_id: uuid.UUID,
    municipio: str = "",
    provincia: str = "",
) -> int:
    """Parsea las fichas AA del documento y las persiste con sus referencias catastrales.

    Para cada ficha:
    1. Extrae campos básicos con regex (rápido, sin coste)
    2. Usa Claude para extraer todos los campos del texto completo (fiable, una vez)
    3. Guarda datos estructurados + datos_json completo + refs catastrales

    Elimina fichas anteriores del mismo documento antes de insertar (re-indexación segura).
    Devuelve el número de fichas guardadas.
    """
    from app.services.ai_synthesis import extraer_datos_ficha

    # Borrar fichas previas del mismo documento (re-indexación idempotente)
    await db.execute(
        text("DELETE FROM pgou_fichas_aa WHERE documento_id = :doc_id"),
        {"doc_id": str(documento_id)},
    )
    # Borrar chunks semánticos de fichas del mismo documento
    await db.execute(
        text("DELETE FROM pgou_chunks WHERE documento_id = :doc_id AND seccion = 'Fichas'"),
        {"doc_id": str(documento_id)},
    )

    fichas = parsear_fichas_pdf(paginas)
    if not fichas:
        logger.info(f"No se encontraron fichas AA en documento {documento_id}")
        return 0

    for ficha in fichas:
        # Extraer datos completos con Claude (bloqueante pero ocurre solo en indexación)
        datos_json: dict = {}
        if ficha.texto_ficha:
            try:
                datos_json = extraer_datos_ficha(ficha.texto_ficha, id_ambito=ficha.id_ambito)
                logger.info(
                    f"  {ficha.id_ambito}: Claude extrajo {len(datos_json)} campos "
                    f"(regex: loc={bool(ficha.localizacion)}, uso={bool(ficha.uso_predominante)})"
                )
            except Exception as e:
                logger.warning(f"  {ficha.id_ambito}: extracción Claude falló: {e}")

        # Priorizar datos de Claude sobre regex para los campos estructurados
        localizacion = datos_json.get("localizacion") or ficha.localizacion or None
        uso_predominante = datos_json.get("uso_predominante") or ficha.uso_predominante or None
        tipologia = datos_json.get("tipologia_edificatoria") or ficha.tipologia_edificatoria or None
        ordenanza = datos_json.get("ordenanza_referencia") or ficha.ordenanza_referencia or None
        edificabilidad = datos_json.get("edificabilidad_m2c") or ficha.edificabilidad_m2c
        num_viviendas = datos_json.get("num_viviendas_estimado") or ficha.num_viviendas_estimado
        sup_ambito = datos_json.get("sup_ambito_m2") or ficha.sup_ambito_m2
        # condiciones: preferir array de Claude (más completo) pero guardar como string también
        condiciones_lista = datos_json.get("condiciones") or []
        condiciones_str = "\n".join(condiciones_lista) if condiciones_lista else ficha.condiciones or None

        ficha_obj = PgouFichaAA(
            municipio_id=municipio_id,
            documento_id=documento_id,
            id_ambito=ficha.id_ambito,
            localizacion=localizacion,
            uso_predominante=uso_predominante,
            tipologia_edificatoria=tipologia,
            ordenanza_referencia=ordenanza,
            sup_ambito_m2=sup_ambito,
            edificabilidad_m2c=edificabilidad,
            num_viviendas_estimado=num_viviendas,
            condiciones=condiciones_str,
            texto_ficha=ficha.texto_ficha or None,
            pagina_inicio=ficha.pagina_inicio,
            datos_json=datos_json or None,
        )
        db.add(ficha_obj)
        await db.flush()

        for ref in ficha.refs_catastrales:
            db.add(PgouRefCatastral(
                ficha_id=ficha_obj.id,
                manzana=ref.manzana,
                parcela=ref.parcela,
                tipo_catastro=ref.tipo_catastro,
                texto_original=ref.texto_original,
            ))

        # Chunk semántico dedicado: permite recuperar esta ficha por búsqueda de condiciones
        # sin necesidad de conocer la RC. Un chunk por ficha con toda su información.
        texto_chunk = _texto_chunk_ficha(ficha.id_ambito, datos_json, ficha)
        if texto_chunk:
            embedding_chunk = await embed_texto(_texto_para_embedding_ficha(ficha.id_ambito, datos_json))
            chunk_ficha = PgouChunk(
                municipio=municipio,
                provincia=provincia,
                documento_id=documento_id,
                seccion="Fichas",
                articulo=f"Ficha {ficha.id_ambito}",
                contenido=texto_chunk,
                pagina=ficha.pagina_inicio,
                metadatos={
                    "tipo": "ficha_aa",
                    "id_ambito": ficha.id_ambito,
                    "posicion": 0,
                    "total_chunks": 1,
                    "pagina_inicio": ficha.pagina_inicio,
                    "pagina_fin": ficha.pagina_inicio,
                },
            )
            db.add(chunk_ficha)
            await db.flush()
            await db.execute(
                text("UPDATE pgou_chunks SET embedding = CAST(:emb AS vector) WHERE id = :id"),
                {"emb": str(embedding_chunk), "id": str(chunk_ficha.id)}
            )

    await db.commit()
    logger.info(
        f"Fichas AA indexadas: {len(fichas)} fichas con "
        f"{sum(len(f.refs_catastrales) for f in fichas)} refs catastrales + {len(fichas)} chunks semánticos"
    )
    return len(fichas)


def _texto_chunk_ficha(id_ambito: str, datos: dict, ficha) -> str:
    """Genera el texto completo del chunk semántico de una ficha AA.

    Incluye todos los campos relevantes en texto plano para que el embedding
    capture condiciones, instrumentos, cesiones y otros términos buscables.
    """
    d = datos or {}
    lineas = [f"FICHA DE DESARROLLO {id_ambito}"]

    if d.get("localizacion") or ficha.localizacion:
        lineas.append(f"Localización: {d.get('localizacion') or ficha.localizacion}")
    if d.get("objetivos"):
        lineas.append(f"Objetivos: {d['objetivos']}")
    if d.get("uso_predominante") or ficha.uso_predominante:
        lineas.append(f"Uso predominante: {d.get('uso_predominante') or ficha.uso_predominante}")
    if d.get("tipologia_edificatoria") or ficha.tipologia_edificatoria:
        lineas.append(f"Tipología edificatoria: {d.get('tipologia_edificatoria') or ficha.tipologia_edificatoria}")
    if d.get("ordenanza_referencia") or ficha.ordenanza_referencia:
        lineas.append(f"Ordenanza de referencia: {d.get('ordenanza_referencia') or ficha.ordenanza_referencia}")

    edif = d.get("edificabilidad_m2c") or ficha.edificabilidad_m2c
    if edif:
        lineas.append(f"Edificabilidad lucrativa: {edif} m2c")
    viv = d.get("num_viviendas_estimado") or ficha.num_viviendas_estimado
    if viv:
        lineas.append(f"Número estimado de viviendas: {viv}")

    sup = d.get("sup_ambito_m2") or ficha.sup_ambito_m2
    if sup:
        partes = [f"Superficie ámbito: {sup} m2"]
        if d.get("sup_computable_m2"):
            partes.append(f"computable: {d['sup_computable_m2']} m2")
        lineas.append(", ".join(partes))

    cesiones = d.get("cesiones") or {}
    if cesiones:
        lineas.append("Cesiones mínimas:")
        if cesiones.get("espacios_libres_m2"):
            lineas.append(f"  Espacios libres: {cesiones['espacios_libres_m2']} m2")
        if cesiones.get("plazas_aparcamiento_total"):
            lineas.append(f"  Plazas aparcamiento: {cesiones['plazas_aparcamiento_total']}")
        if cesiones.get("viario_m2"):
            lineas.append(f"  Viario: {cesiones['viario_m2']} m2")
        for otro in (cesiones.get("otros") or []):
            lineas.append(f"  {otro}")

    if d.get("instrumento_gestion"):
        lineas.append(f"Instrumento gestión: {d['instrumento_gestion']}")
    if d.get("instrumento_ejecucion"):
        lineas.append(f"Instrumento ejecución: {d['instrumento_ejecucion']}")
    if d.get("instrumento_planeamiento"):
        lineas.append(f"Instrumento planeamiento: {d['instrumento_planeamiento']}")
    if d.get("plazos"):
        lineas.append(f"Plazos: {d['plazos']}")

    condiciones = d.get("condiciones") or []
    if condiciones:
        lineas.append("Condiciones:")
        for c in condiciones:
            lineas.append(f"  {c}")
    elif ficha.condiciones:
        lineas.append(f"Condiciones:\n  {ficha.condiciones}")

    if d.get("referencias_catastrales_texto"):
        lineas.append(f"Referencias catastrales: {d['referencias_catastrales_texto']}")

    return "\n".join(lineas)


def _texto_para_embedding_ficha(id_ambito: str, datos: dict) -> str:
    """Texto optimizado para el embedding de una ficha: ámbito + uso + condiciones (inicio).

    El embedding captura los términos más discriminativos para búsqueda semántica:
    el código del ámbito, el uso y las primeras condiciones.
    """
    d = datos or {}
    partes = [f"Ficha {id_ambito}"]
    if d.get("uso_predominante"):
        partes.append(d["uso_predominante"])
    if d.get("localizacion"):
        partes.append(d["localizacion"][:100])
    condiciones = d.get("condiciones") or []
    if condiciones:
        partes.append("Condiciones: " + " | ".join(condiciones[:2]))
    return " — ".join(partes)[:400]


# ── Búsqueda RAG híbrida ─────────────────────────────────────

# Reciprocal Rank Fusion: constante estándar que suaviza el peso del top absoluto.
# Ver Cormack et al. 2009 "Reciprocal Rank Fusion outperforms Condorcet".
_RRF_K = 60

# Candidatos por método antes de fusionar. 20 es suficiente: el ruido se filtra
# en el paso de re-ranking.
_POOL_SIZE = 20

# Tras RRF, top que pasa al re-ranker LLM. Más alto → mejor recall, más coste.
_PRE_RERANK_TOP = 15


# ── Query expansion (HyDE ligero) ─────────────────────────────

_SYSTEM_EXPAND = """Eres experto en PGOU español. El usuario hace una pregunta en lenguaje
coloquial. Genera 2 reformulaciones usando vocabulario técnico del planeamiento
urbanístico (artículo, ordenanza, clasificación, aprovechamiento, coeficiente,
zonificación, retranqueo, edificabilidad, etc.), manteniendo la intención original.

Responde SOLO con JSON:
{"variantes": ["reformulación 1 con vocabulario técnico", "reformulación 2 distinta"]}"""


async def _expand_pregunta(pregunta: str) -> list[str]:
    """Devuelve [pregunta_original, variante1, variante2] con vocabulario técnico.

    Si el LLM falla o devuelve formato inválido, degrada a [pregunta_original]
    para no bloquear la búsqueda.
    """
    try:
        texto = llm_client.complete(_SYSTEM_EXPAND, pregunta, max_tokens=250)
        import json
        import re
        match = re.search(r"\{[\s\S]+\}", texto)
        if not match:
            return [pregunta]
        data = json.loads(match.group(0))
        variantes = [v for v in (data.get("variantes") or []) if isinstance(v, str) and v.strip()]
        return [pregunta] + variantes[:2]
    except Exception as e:
        logger.debug(f"expand_pregunta falló, usando solo original: {e}")
        return [pregunta]


# ── Re-ranker LLM ─────────────────────────────────────────────

_SYSTEM_RERANK = """Evalúa la relevancia de fragmentos del PGOU para responder una pregunta.
Para cada fragmento marcado [N], asigna un score 0-10 según cuánto ayuda a responder
la pregunta concreta. Un fragmento sobre el tema general pero sin datos específicos
recibe score bajo; uno con valores, artículos o condiciones directamente aplicables
recibe score alto.

Responde SOLO con JSON válido, sin texto adicional:
{"scores": [{"id": 0, "score": 8}, {"id": 1, "score": 3}, ...]}"""


async def _rerank_con_llm(pregunta: str, chunks: list[dict], top_n: int) -> list[dict]:
    """Re-ordena chunks por relevancia real usando un LLM. Devuelve top_n."""
    if len(chunks) <= top_n:
        return chunks

    # Construir input compacto: truncamos el contenido para ahorrar tokens
    items = []
    for i, c in enumerate(chunks):
        cabecera = c.get("articulo") or c.get("seccion") or ""
        contenido = (c.get("contenido") or "")[:500]
        items.append(f"[{i}] {cabecera}\n{contenido}")

    user = f"PREGUNTA: {pregunta}\n\nFRAGMENTOS:\n\n" + "\n\n".join(items)

    import json
    import re
    texto = llm_client.complete(_SYSTEM_RERANK, user, max_tokens=600)
    match = re.search(r"\{[\s\S]+\}", texto)
    if not match:
        raise ValueError("Respuesta del re-ranker sin JSON")
    data = json.loads(match.group(0))

    scores_por_id = {
        item["id"]: float(item.get("score", 0))
        for item in (data.get("scores") or [])
        if isinstance(item, dict) and "id" in item
    }

    # Chunks no puntuados por el LLM reciben score 0 y quedan al final
    ordenados = sorted(
        enumerate(chunks),
        key=lambda pair: -scores_por_id.get(pair[0], 0.0),
    )
    return [c for _, c in ordenados[:top_n]]


# ── Búsqueda principal ───────────────────────────────────────

async def buscar_pgou(
    db: AsyncSession,
    municipio: str,
    provincia: str,
    pregunta: str,
    top_k: int = 10,
    rerank: bool = True,
    expand_query: bool = True,
) -> list[dict]:
    """Búsqueda híbrida en el índice PGOU.

    Pipeline:
    1. (opcional) Expansión de la pregunta con variantes técnicas (HyDE)
    2. Embedding promediado de todas las variantes
    3. Búsqueda semántica (top _POOL_SIZE por coseno)
    4. Búsqueda lexical (top _POOL_SIZE por ts_rank con diccionario español)
    5. Fusión RRF → top _PRE_RERANK_TOP
    6. (opcional) Re-ranking por LLM → top_k
    7. Expansión ±1 posición (chunks adyacentes del mismo documento para contexto)
    8. Orden secuencial por (documento, posición) para el LLM final
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

    # 1-2. Query expansion + embedding promediado
    preguntas = await _expand_pregunta(pregunta) if expand_query else [pregunta]
    if len(preguntas) > 1:
        logger.debug(f"Query expandida a {len(preguntas)} variantes")
    embeddings_q = await embed_batch(preguntas)
    embedding_final = _mean_pool(embeddings_q)

    # 3. Búsqueda semántica
    semantic_rows = (await db.execute(
        text("""
            SELECT id, contenido, seccion, articulo, metadatos, documento_id, pagina,
                   1 - (embedding <=> CAST(:emb AS vector)) AS similitud
            FROM pgou_chunks
            WHERE municipio = :municipio AND provincia = :provincia
            ORDER BY embedding <=> CAST(:emb AS vector)
            LIMIT :k
        """),
        {"emb": str(embedding_final), "municipio": municipio,
         "provincia": provincia, "k": _POOL_SIZE}
    )).fetchall()

    # 4. Búsqueda lexical (ts_rank con diccionario español)
    # Concatenamos todas las variantes: websearch_to_tsquery las unirá con OR implícito
    q_lexical = " ".join(preguntas)
    lexical_rows = (await db.execute(
        text("""
            SELECT id, contenido, seccion, articulo, metadatos, documento_id, pagina,
                   ts_rank(tsv, websearch_to_tsquery('spanish', :q)) AS ts_score
            FROM pgou_chunks
            WHERE municipio = :municipio AND provincia = :provincia
              AND tsv @@ websearch_to_tsquery('spanish', :q)
            ORDER BY ts_score DESC
            LIMIT :k
        """),
        {"q": q_lexical, "municipio": municipio,
         "provincia": provincia, "k": _POOL_SIZE}
    )).fetchall()

    logger.debug(
        f"RAG híbrido: {len(semantic_rows)} semánticos + {len(lexical_rows)} lexicales"
    )

    # 5. Fusión RRF
    def _row_a_dict(row, similitud: float) -> dict:
        return {
            "id": str(row.id),
            "contenido": row.contenido,
            "seccion": row.seccion,
            "articulo": row.articulo,
            "metadatos": row.metadatos or {},
            "_doc_id": str(row.documento_id),
            "_posicion": (row.metadatos or {}).get("posicion", 0),
            "_pagina": row.pagina,
            "similitud": similitud,
            "_rrf": 0.0,
        }

    fused: dict[str, dict] = {}
    for rank, row in enumerate(semantic_rows, start=1):
        cid = str(row.id)
        if cid not in fused:
            fused[cid] = _row_a_dict(row, float(row.similitud))
        fused[cid]["_rrf"] += 1.0 / (_RRF_K + rank)

    for rank, row in enumerate(lexical_rows, start=1):
        cid = str(row.id)
        if cid not in fused:
            fused[cid] = _row_a_dict(row, 0.0)
        fused[cid]["_rrf"] += 1.0 / (_RRF_K + rank)

    ranked = sorted(fused.values(), key=lambda r: -r["_rrf"])
    top = ranked[:_PRE_RERANK_TOP]

    # 6. Re-ranking LLM (filtra falsos positivos de similitud)
    if rerank and len(top) > top_k:
        try:
            top = await _rerank_con_llm(pregunta, top, top_n=top_k)
            logger.debug(f"Re-ranker aplicado: {len(top)} chunks tras re-rank")
        except Exception as e:
            logger.warning(f"Re-ranker falló ({type(e).__name__}: {e}); siguiendo con RRF")
            top = top[:top_k]
    else:
        top = top[:top_k]

    # 7. Expansión ±1 posición
    seen_ids = {r["id"] for r in top}
    existing_keys = {(r["_doc_id"], r["_posicion"]) for r in top}
    expansion_needed: list[tuple[str, int]] = []
    for r in top:
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
                SELECT id, contenido, seccion, articulo, metadatos, documento_id, pagina
                FROM pgou_chunks
                WHERE municipio = :municipio AND provincia = :provincia
                AND ({' OR '.join(conditions)})
            """),
            params,
        )
        for row in adj_rows:
            if str(row.id) not in seen_ids:
                top.append({
                    "id": str(row.id),
                    "contenido": row.contenido,
                    "seccion": row.seccion,
                    "articulo": row.articulo,
                    "metadatos": row.metadatos or {},
                    "_doc_id": str(row.documento_id),
                    "_posicion": (row.metadatos or {}).get("posicion", 0),
                    "_pagina": row.pagina,
                    "similitud": 0.0,
                })

    # 8. Orden secuencial por documento + posición
    top.sort(key=lambda r: (r["_doc_id"], r["_posicion"]))

    return [
        {
            "contenido": r["contenido"],
            "seccion": r["seccion"],
            "articulo": r["articulo"],
            "similitud": r["similitud"],
            "metadatos": r["metadatos"],
            "documento_id": r["_doc_id"],
            "pagina": r.get("_pagina"),
        }
        for r in top
    ]


# ── Búsqueda por referencia catastral ────────────────────────────────────────

async def buscar_por_rc(
    db: AsyncSession,
    municipio: str,
    provincia: str,
    rc: str,
) -> dict | None:
    """Busca la ficha de desarrollo correspondiente a una referencia catastral.

    Extrae manzana y parcela de la RC, hace lookup en pgou_refs_catastrales
    con índice B-tree (O log n), y devuelve la ficha con todos sus datos.

    Devuelve None si no hay fichas indexadas o la parcela no pertenece a ningún ámbito.
    """
    par = rc_a_manzana_parcela(rc)
    if par is None:
        return None
    manzana, parcela = par

    logger.debug(f"Buscando RC {rc!r} → manzana={manzana!r}, parcela={parcela!r}")

    # Primero comprobamos que el municipio tiene fichas indexadas
    _SELECT_FICHA = """
        SELECT f.id, f.id_ambito, f.localizacion, f.uso_predominante,
               f.tipologia_edificatoria, f.ordenanza_referencia,
               f.sup_ambito_m2, f.edificabilidad_m2c, f.num_viviendas_estimado,
               f.condiciones, f.texto_ficha, f.datos_json, f.pagina_inicio, f.documento_id,
               r.manzana, r.parcela, r.tipo_catastro, r.texto_original
        FROM pgou_fichas_aa f
        JOIN pgou_refs_catastrales r ON r.ficha_id = f.id
        JOIN pgou_municipios m ON m.id = f.municipio_id
        WHERE m.municipio = :municipio
          AND m.provincia = :provincia
    """

    rows = await db.execute(
        text(_SELECT_FICHA + " AND r.manzana = :manzana AND r.parcela = :parcela LIMIT 1"),
        {"municipio": municipio, "provincia": provincia, "manzana": manzana, "parcela": parcela},
    )
    row = rows.fetchone()
    if not row:
        # Segundo intento: buscar solo por manzana (la parcela puede tener distinto formato)
        rows_manzana = await db.execute(
            text(_SELECT_FICHA + " AND r.manzana = :manzana LIMIT 1"),
            {"municipio": municipio, "provincia": provincia, "manzana": manzana},
        )
        row = rows_manzana.fetchone()
        if not row:
            return None

    return {
        "encontrado": True,
        "rc": rc,
        "manzana": manzana,
        "parcela": parcela,
        "id_ambito": row.id_ambito,
        "localizacion": row.localizacion,
        "uso_predominante": row.uso_predominante,
        "tipologia_edificatoria": row.tipologia_edificatoria,
        "ordenanza_referencia": row.ordenanza_referencia,
        "sup_ambito_m2": row.sup_ambito_m2,
        "edificabilidad_m2c": row.edificabilidad_m2c,
        "num_viviendas_estimado": row.num_viviendas_estimado,
        "condiciones": row.condiciones,
        "texto_ficha": row.texto_ficha,
        # datos_json: todos los campos extraídos por Claude durante la indexación
        "datos_json": row.datos_json,
        # Datos para el deep-link en la Biblioteca
        "fuente": {
            "documento_id": str(row.documento_id) if row.documento_id else None,
            "pagina": row.pagina_inicio,
            "ref_catastral_original": row.texto_original,
        },
    }
