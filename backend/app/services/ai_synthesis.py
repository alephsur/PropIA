"""Síntesis de informes con el proveedor LLM configurado."""
import json
import re
from app.ai import llm_client
from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _parse_json_response(texto: str, fallback_tipo: str = "documento") -> dict:
    """
    Extrae y parsea JSON de la respuesta del modelo.
    Maneja: JSON limpio, bloques ```json ... ```, JSON embebido en texto,
    y respuestas en texto plano (modelos que ignoran la instrucción JSON).
    """
    texto = texto.strip()
    if not texto:
        raise ValueError("El modelo devolvió una respuesta vacía")

    # 1. Bloque de código markdown: ```json ... ``` o ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", texto)
    if match:
        candidato = match.group(1).strip()
        try:
            return json.loads(candidato)
        except json.JSONDecodeError:
            pass

    # 2. Intentar parsear directamente
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass

    # 3. Buscar el primer objeto JSON válido en el texto
    match = re.search(r"\{[\s\S]+\}", texto)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # 4. El modelo respondió en texto plano — envolver en estructura estándar
    logger.warning("Respuesta del modelo no es JSON, envolviendo en estructura estándar")
    return {
        "tipo_documento": fallback_tipo,
        "datos_principales": {},
        "referencias_catastrales": [],
        "referencias_registrales": [],
        "superficies": {},
        "titulares": [],
        "cargas": [],
        "condiciones_relevantes": [],
        "fechas_relevantes": {},
        "alertas": [{"nivel": "info", "texto": "Análisis generado en texto libre por el modelo"}],
        "resumen": texto,
    }

SYSTEM_INFORME = """
Eres un experto en derecho inmobiliario y urbanismo español especializado en
Cantabria (Ley del Suelo Ley 2/2001, BOC) y Asturias (TRLOTUA DL 1/2004, BOPA).
Recibes datos de Catastro OVC, PGOU indexado y BOC/BOPA/BOE.
Generas informes profesionales para agentes inmobiliarios no juristas.

REGLAS:
1. Responde ÚNICAMENTE con JSON válido. Sin texto fuera del JSON.
2. Solo datos proporcionados. Si falta un dato: null.
3. Si PGOU de Cantabria/Asturias con confianza baja: alerta warning "Confirmar con técnico municipal de {municipio}".
4. Resumen: máximo 3 frases en lenguaje de agente.

JSON:
{
  "status": "ok|warning|error",
  "datos_principales": {
    "referencia_catastral": "...", "direccion_completa": "...",
    "superficie_construida_m2": "...", "superficie_parcela_m2": "...",
    "uso_actual": "...", "clasificacion_suelo": "...",
    "zonificacion": "...", "usos_permitidos": "...",
    "edificabilidad": "...", "altura_maxima": "...",
    "valor_catastral_eur": "...", "ano_construccion": "...",
    "plan_vigente": "...", "boletin": "BOC|BOPA|BOE + fecha"
  },
  "alertas": [{ "nivel": "info|warning|danger|success", "texto": "..." }],
  "checklist": [{ "item": "...", "estado": "ok|warning|bad|unknown", "detalle": "..." }],
  "resumen": "máximo 3 frases",
  "recomendaciones": ["acción 1", "acción 2", "acción 3"],
  "fuentes_usadas": ["catastro_ovc", "pgou_indexado", "boc"]
}
"""

SYSTEM_PGOU = """
Eres un arquitecto urbanista experto en PGOU de Cantabria y Asturias.
Recibes fragmentos reales de documentos de planeamiento y debes responder la pregunta con precisión.

INSTRUCCIONES CRÍTICAS:
1. Responde ÚNICAMENTE basándote en los fragmentos proporcionados. NUNCA inventes datos.
2. La pregunta puede ser de dos tipos:
   A) Consulta sobre una parcela concreta → rellena los campos urbanísticos (clasificacion_suelo, etc.)
   B) Consulta normativa o técnica (coeficientes, índices, parámetros, procedimientos) →
      rellena "respuesta_directa" y "datos_encontrados" con los valores EXACTOS del texto.
3. "fragmentos_clave": copia LITERALMENTE las frases o párrafos del PGOU que responden la pregunta.
4. "datos_encontrados": úsalo para tablas, listas de valores, coeficientes, porcentajes, etc.
5. Si los fragmentos no contienen la respuesta → confianza="baja" y en "nota" explica qué falta.

Responde ÚNICAMENTE con JSON válido:
{
  "respuesta_directa": "respuesta clara en 1-3 frases en lenguaje de agente inmobiliario (SIEMPRE rellenar)",
  "datos_encontrados": {
    "descripción del dato": "valor exacto copiado del documento"
  },
  "clasificacion_suelo": null,
  "zonificacion": null,
  "uso_global": null,
  "usos_permitidos": [],
  "usos_prohibidos": [],
  "edificabilidad": null,
  "altura_maxima": null,
  "retranqueos": null,
  "ocupacion_maxima": null,
  "plan_vigente": null,
  "articulos_referencia": ["Artículo X — PGOU año"],
  "fragmentos_clave": ["cita literal del texto que responde la pregunta"],
  "confianza": "alta|media|baja",
  "nota": "aclaración si hay ambigüedad, datos insuficientes o recomendación al agente"
}
"""

SYSTEM_URBANISMO = """
Eres un arquitecto urbanista experto en PGOU de Cantabria y Asturias.
Recibes datos estructurados de una ficha de desarrollo del PGOU y fragmentos de normativa.

REGLAS:
1. Responde ÚNICAMENTE con los datos proporcionados. NUNCA inventes valores.
2. Copia los valores de la ficha EXACTAMENTE como aparecen — no parafrasees.
3. "condiciones_clave": usa el array "CONDICIONES" de la ficha, una condición por ítem.
4. "fragmentos_clave": citas literales del PGOU o la ficha que justifican la respuesta.
5. confianza="alta" si la ficha tiene datos completos, "media" si faltan campos, "baja" si solo hay fragmentos RAG.

Responde ÚNICAMENTE con JSON válido:
{
  "respuesta_directa": "2-3 frases con uso, edificabilidad y viviendas — usar valores exactos de la ficha",
  "ambito_plan": "código del ámbito tal como aparece (ej: AA V3)",
  "localizacion": "valor de Localización en la ficha",
  "clasificacion_suelo": "si aparece en la ficha o fragmentos",
  "uso_predominante": "valor de Uso predominante en la ficha",
  "tipologia_edificatoria": "valor de Tipología edificatoria en la ficha",
  "edificabilidad_m2c": 0.0,
  "num_viviendas_max": 0,
  "altura_maxima": null,
  "retranqueos": null,
  "condiciones_clave": ["condición 1 literal", "condición 2 literal"],
  "instrumentos": {
    "gestion": "instrumento de gestión",
    "ejecucion": "instrumento de ejecución",
    "planeamiento": "instrumento de planeamiento"
  },
  "cesiones": {
    "espacios_libres_m2": null,
    "plazas_aparcamiento": null,
    "viario_m2": null
  },
  "fragmentos_clave": ["cita literal del PGOU que justifica"],
  "confianza": "alta|media|baja",
  "nota": null
}
"""

SYSTEM_EXTRACTOR_FICHA = """
Eres un extractor de datos urbanísticos. Se te proporciona el texto extraído de una ficha
de desarrollo del PGOU (Plan General de Ordenación Urbana).

Extrae TODOS los campos que encuentres y devuelve ÚNICAMENTE JSON válido, sin texto adicional.
Si un campo no aparece en el texto usa null. Los números deben ser números (no strings).
Las condiciones deben ser un array donde cada elemento es UNA condición completa con su número.

{
  "localizacion": "descripción completa del ámbito tal como aparece",
  "objetivos": "texto del campo Objetivos",
  "uso_predominante": "texto del campo Uso predominante",
  "tipologia_edificatoria": "texto del campo Tipología edificatoria",
  "ordenanza_referencia": "texto completo del campo Ordenanza de referencia",
  "sup_ambito_m2": 0.0,
  "sup_redes_publicas_m2": 0.0,
  "sup_computable_m2": 0.0,
  "edificabilidad_m2c": 0.0,
  "num_viviendas_estimado": 0,
  "cesiones": {
    "espacios_libres_m2": null,
    "plazas_aparcamiento_total": null,
    "plazas_aparcamiento_publicas": null,
    "plazas_pmr": null,
    "viario_m2": null,
    "otros": []
  },
  "instrumento_gestion": "artículo o texto del instrumento de gestión",
  "instrumento_ejecucion": "tipo de instrumento de ejecución",
  "instrumento_planeamiento": "tipo de instrumento de planeamiento",
  "plazos": "texto del campo Plazos",
  "prioridades": "texto del campo Prioridades",
  "condiciones": [
    "1. texto completo de la primera condición",
    "2. texto completo de la segunda condición"
  ],
  "referencias_catastrales_texto": "texto literal de las referencias catastrales"
}
"""

SYSTEM_DOCUMENTOS = """
Eres un notario y registrador de la propiedad español especializado en
Cantabria y Asturias. Analiza el documento y extrae toda la información.
Responde ÚNICAMENTE con JSON válido:
{
  "tipo_documento": "escritura|cedula_habitabilidad|licencia|nota_simple|plano|contrato|otro",
  "datos_principales": { "campo": "valor" },
  "referencias_catastrales": ["RC1"],
  "referencias_registrales": [{"tomo":"...","libro":"...","folio":"...","finca":"..."}],
  "superficies": {"construida_m2":"...","parcela_m2":"...","util_m2":"..."},
  "titulares": [{"nombre":"...","nif":"...","porcentaje_propiedad":"..."}],
  "cargas": [{"tipo":"hipoteca|embargo|servidumbre|anotacion|otro",
    "acreedor":"...","importe_eur":"...","descripcion":"..."}],
  "condiciones_relevantes": ["..."],
  "fechas_relevantes": {"otorgamiento":"...","inscripcion":"...","caducidad":"..."},
  "alertas": [{"nivel":"info|warning|danger","texto":"..."}],
  "resumen": "2-3 frases ejecutivas"
}
"""


async def sintetizar_informe(
    datos_catastro: dict,
    chunks_pgou: list[dict],
    normativa: list[dict],
    ficha_aa: dict | None = None,
) -> dict:
    """Genera informe completo combinando todas las fuentes."""
    partes = ["DATOS CATASTRO:", json.dumps(datos_catastro, ensure_ascii=False, indent=2), ""]

    if ficha_aa:
        partes += [
            "FICHA DE DESARROLLO DEL PGOU (datos exactos del ámbito):",
            _formatear_ficha_para_llm(ficha_aa),
            "",
        ]

    partes += [
        "FRAGMENTOS PGOU:",
        _formatear_chunks_para_llm(chunks_pgou),
        "",
        "NORMATIVA BOC/BOPA/BOE:",
        json.dumps(normativa, ensure_ascii=False, indent=2),
    ]

    contexto = "\n".join(partes)
    texto = llm_client.complete(SYSTEM_INFORME, contexto, max_tokens=2000)
    resultado = _parse_json_response(texto)

    # Inyectar fuentes para el frontend
    resultado["fuentes"] = _construir_fuentes(ficha_aa, chunks_pgou)
    return resultado


def _formatear_chunks_para_llm(chunks: list[dict]) -> str:
    """Formatea los chunks como texto limpio agrupado por artículo.

    En vez de pasar JSON crudo, el LLM recibe texto legible con referencias
    a páginas y artículos, lo que mejora significativamente la calidad de respuesta.
    """
    if not chunks:
        return "(Sin fragmentos disponibles)"

    bloques = []
    for i, chunk in enumerate(chunks, 1):
        articulo = chunk.get("articulo") or ""
        seccion = chunk.get("seccion") or ""
        metadatos = chunk.get("metadatos") or {}
        # Usar el campo 'pagina' directo (migration 002) con fallback a metadatos
        pagina = chunk.get("pagina") or metadatos.get("pagina_inicio")
        pag_fin = metadatos.get("pagina_fin")
        similitud = chunk.get("similitud", 0)

        cabecera_parts = []
        if articulo:
            cabecera_parts.append(articulo)
        if seccion:
            cabecera_parts.append(f"[{seccion}]")
        if pagina:
            if pag_fin and pag_fin != pagina:
                cabecera_parts.append(f"(págs. {pagina}-{pag_fin})")
            else:
                cabecera_parts.append(f"(pág. {pagina})")
        if similitud > 0:
            cabecera_parts.append(f"relevancia: {similitud:.0%}")

        cabecera = " — ".join(cabecera_parts) if cabecera_parts else f"Fragmento {i}"
        bloques.append(f"--- {cabecera} ---\n{chunk['contenido']}")

    return "\n\n".join(bloques)


def _formatear_ficha_para_llm(ficha: dict) -> str:
    """Formatea los datos de una ficha AA para el LLM.

    Prioridad de fuentes:
    1. datos_json (extraído por Claude durante indexación) — más completo y fiable
    2. Campos estructurados del modelo (parseados por regex, pueden estar vacíos)
    3. texto_ficha (texto crudo del PDF) — fallback final
    """
    lineas = [f"ÁMBITO: {ficha.get('id_ambito', '?')}"]

    # Fuente 1: datos_json extraídos por Claude — siempre preferida
    datos = ficha.get("datos_json") or {}

    def _val(key: str):
        """Devuelve datos_json[key] si existe, sino el campo directo de la ficha."""
        return datos.get(key) or ficha.get(key)

    if _val("localizacion"):
        lineas.append(f"Localización: {_val('localizacion')}")
    if _val("objetivos"):
        lineas.append(f"Objetivos: {_val('objetivos')}")
    if _val("uso_predominante"):
        lineas.append(f"Uso predominante: {_val('uso_predominante')}")
    if _val("tipologia_edificatoria"):
        lineas.append(f"Tipología edificatoria: {_val('tipologia_edificatoria')}")
    if _val("ordenanza_referencia"):
        lineas.append(f"Ordenanza de referencia: {_val('ordenanza_referencia')}")

    # Superficies
    sup = _val("sup_ambito_m2") or datos.get("sup_ambito_m2")
    if sup:
        partes_sup = [f"S. ámbito: {sup} m²"]
        if datos.get("sup_redes_publicas_m2"):
            partes_sup.append(f"S. redes públicas: {datos['sup_redes_publicas_m2']} m²")
        if datos.get("sup_computable_m2"):
            partes_sup.append(f"S. computable: {datos['sup_computable_m2']} m²")
        lineas.append("Superficie estimada: " + " | ".join(partes_sup))

    edif = _val("edificabilidad_m2c")
    if edif:
        lineas.append(f"Edificabilidad lucrativa: {edif} m²c")

    viv = _val("num_viviendas_estimado")
    if viv:
        lineas.append(f"Nº estimado de viviendas: {viv}")

    # Cesiones mínimas (solo en datos_json)
    cesiones = datos.get("cesiones") or {}
    if cesiones:
        lineas.append("\nCESIONES MÍNIMAS:")
        if cesiones.get("espacios_libres_m2"):
            lineas.append(f"  Espacios Libres: {cesiones['espacios_libres_m2']} m²")
        if cesiones.get("plazas_aparcamiento_total"):
            lineas.append(f"  Plazas aparcamiento totales: {cesiones['plazas_aparcamiento_total']}")
        if cesiones.get("plazas_aparcamiento_publicas"):
            lineas.append(f"  Plazas aparcamiento públicas: {cesiones['plazas_aparcamiento_publicas']}")
        if cesiones.get("plazas_pmr"):
            lineas.append(f"  Plazas PMR: {cesiones['plazas_pmr']}")
        if cesiones.get("viario_m2"):
            lineas.append(f"  Viario: {cesiones['viario_m2']} m²")
        for otro in (cesiones.get("otros") or []):
            lineas.append(f"  {otro}")

    # Instrumentos y plazos
    if datos.get("instrumento_gestion"):
        lineas.append(f"\nInstrumento gestión: {datos['instrumento_gestion']}")
    if datos.get("instrumento_ejecucion"):
        lineas.append(f"Instrumento ejecución: {datos['instrumento_ejecucion']}")
    if datos.get("instrumento_planeamiento"):
        lineas.append(f"Instrumento planeamiento: {datos['instrumento_planeamiento']}")
    if datos.get("plazos"):
        lineas.append(f"Plazos: {datos['plazos']}")
    if datos.get("prioridades"):
        lineas.append(f"Prioridades: {datos['prioridades']}")

    # Condiciones — array en datos_json, string en campo estructurado
    condiciones_lista = datos.get("condiciones") or []
    condiciones_str = ficha.get("condiciones") or ""
    if condiciones_lista:
        lineas.append("\nCONDICIONES:")
        for c in condiciones_lista:
            lineas.append(f"  {c}")
    elif condiciones_str:
        lineas.append(f"\nCONDICIONES:\n{condiciones_str}")

    # Fuente 3: texto crudo — fallback si datos_json está vacío
    if not datos and not condiciones_str:
        texto_ficha = (ficha.get("texto_ficha") or "").strip()
        if texto_ficha:
            lineas.append(
                "\n── TEXTO COMPLETO DE LA FICHA (fuente primaria — extraer todos los datos) ──"
            )
            lineas.append(texto_ficha[:4000])

    return "\n".join(lineas)


async def consultar_pgou(chunks: list[dict], pregunta: str, municipio: str) -> dict:
    """Responde una pregunta sobre el PGOU usando los chunks recuperados."""
    fragmentos_texto = _formatear_chunks_para_llm(chunks)
    contexto = f"""MUNICIPIO: {municipio}
PREGUNTA: {pregunta}

FRAGMENTOS DEL PGOU ({len(chunks)} encontrados):

{fragmentos_texto}"""
    texto = llm_client.complete(SYSTEM_PGOU, contexto, max_tokens=2000)
    return _parse_json_response(texto)


async def consultar_urbanismo(
    ficha_aa: dict | None,
    chunks: list[dict],
    pregunta: str,
    municipio: str,
) -> dict:
    """Síntesis urbanística combinando ficha estructurada (RC) y RAG (normativa).

    Flujo:
    - Si hay ficha_aa: Claude recibe los datos exactos del ámbito + fragmentos normativos
    - Si no hay ficha_aa: solo RAG, como consultar_pgou pero con el prompt enriquecido

    Devuelve la respuesta de Claude con 'fuentes' inyectadas desde los metadatos del sistema
    (no generadas por Claude, para garantizar precisión del deep-link).
    """
    # Construir el contexto para Claude
    partes = [f"MUNICIPIO: {municipio}", f"PREGUNTA: {pregunta}", ""]

    if ficha_aa:
        partes.append("── FICHA DE DESARROLLO (datos exactos del ámbito) ──")
        partes.append(_formatear_ficha_para_llm(ficha_aa))
        partes.append("")

    if chunks:
        partes.append(f"── FRAGMENTOS DEL PGOU ({len(chunks)} encontrados) ──")
        partes.append(_formatear_chunks_para_llm(chunks))
    else:
        partes.append("── FRAGMENTOS DEL PGOU: ninguno encontrado ──")

    contexto = "\n".join(partes)
    texto = llm_client.complete(SYSTEM_URBANISMO, contexto, max_tokens=2000)
    resultado = _parse_json_response(texto)

    # Inyectar fuentes desde los metadatos del sistema (no de Claude)
    # El frontend usa esto para mostrar botones "Ver en Biblioteca"
    resultado["fuentes"] = _construir_fuentes(ficha_aa, chunks)

    return resultado


def _construir_fuentes(ficha_aa: dict | None, chunks: list[dict]) -> list[dict]:
    """Construye la lista de fuentes para el frontend.

    Los documentos se deduplicaron por documento_id para no repetir entradas.
    """
    fuentes: list[dict] = []
    vistas: set[str] = set()

    # Fuente 1: la ficha AA (si existe) — entrada prominente
    if ficha_aa:
        fuente_ficha = ficha_aa.get("fuente", {})
        doc_id = fuente_ficha.get("documento_id")
        if doc_id:
            localizacion = ficha_aa.get("localizacion") or ""
            descripcion = f"Ficha {ficha_aa.get('id_ambito')}"
            if localizacion:
                descripcion += f" — {localizacion}"
            fuentes.append({
                "tipo": "ficha_aa",
                "id_ambito": ficha_aa.get("id_ambito"),
                "documento_id": doc_id,
                "pagina": fuente_ficha.get("pagina"),
                "descripcion": descripcion,
            })
            vistas.add(doc_id)

    # Fuente 2: documentos únicos de los chunks RAG
    for chunk in chunks:
        doc_id = chunk.get("documento_id")
        if not doc_id or doc_id in vistas:
            continue
        vistas.add(doc_id)
        seccion = chunk.get("seccion") or "Normativa"
        pagina = chunk.get("pagina")
        fuentes.append({
            "tipo": "chunk_rag",
            "documento_id": doc_id,
            "pagina": pagina,
            "seccion": seccion,
            "descripcion": seccion,
        })

    return fuentes


def extraer_datos_ficha(texto_ficha: str, id_ambito: str = "") -> dict:
    """Extrae todos los campos de una ficha de desarrollo del PGOU usando Claude.

    Se llama una vez por ficha durante la indexación. El resultado se almacena en
    pgou_fichas_aa.datos_json para recuperación instantánea sin coste posterior.

    Usa el proveedor configurado en AI_PROVIDER. Con Ollama local (qwen2.5) funciona
    bien siempre que el texto llegue razonablemente estructurado (cabeceras únicas,
    tablas anexadas como pares 'Etiqueta: Valor'). La calidad es mayor con Claude
    en tablas muy complejas, pero no es imprescindible.
    """
    etiqueta = id_ambito or "?"
    if not texto_ficha or not texto_ficha.strip():
        logger.warning(f"extraer_datos_ficha [{etiqueta}] omitido: texto_ficha vacío")
        return {}

    # Limitar a 6000 chars — suficiente para cualquier ficha, evita costes innecesarios
    texto_truncado = texto_ficha[:6000]

    try:
        texto = llm_client.complete(
            SYSTEM_EXTRACTOR_FICHA,
            f"FICHA A EXTRAER:\n\n{texto_truncado}",
            max_tokens=1500,
        )
        datos = _parse_json_response(texto, fallback_tipo="ficha")
        datos = {k: v for k, v in datos.items() if v is not None and v != "" and v != [] and v != {}}
        if not datos:
            logger.warning(
                f"extraer_datos_ficha [{etiqueta}]: Claude devolvió JSON vacío "
                f"(texto_ficha={len(texto_ficha)} chars)"
            )
        return datos
    except Exception as e:
        logger.error(
            f"extraer_datos_ficha [{etiqueta}] falló: {type(e).__name__}: {e}"
        )
        return {}


def _provider_documentos() -> str:
    """Devuelve el proveedor a usar para documentos (ai_provider_documentos o el principal)."""
    settings = get_settings()
    return settings.ai_provider_documentos or settings.ai_provider


async def analizar_documento_texto(texto_pdf: str, consulta: str | None = None) -> dict:
    """Analiza texto extraído de un PDF. Compatible con todos los proveedores LLM."""
    provider = _provider_documentos()
    contenido = texto_pdf
    if consulta:
        contenido += f"\n\nConsulta específica: {consulta}"
    logger.debug(f"analizar_documento_texto → proveedor={provider}")
    texto = llm_client.complete(SYSTEM_DOCUMENTOS, contenido, max_tokens=2000, provider_override=provider)
    return _parse_json_response(texto)


async def analizar_documento(contenido_base64: str, media_type: str, consulta: str | None = None) -> dict:
    """Analiza una imagen con visión multimodal. Requiere modelo con capacidad de visión."""
    provider = _provider_documentos()
    bloques = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": contenido_base64,
            },
        }
    ]
    if consulta:
        bloques.append({"type": "text", "text": f"Consulta específica: {consulta}"})

    logger.debug(f"analizar_documento (visión) → proveedor={provider}")
    texto = llm_client.complete(SYSTEM_DOCUMENTOS, bloques, max_tokens=2000, provider_override=provider)
    return _parse_json_response(texto)
