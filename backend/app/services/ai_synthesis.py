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


async def sintetizar_informe(datos_catastro: dict, chunks_pgou: list[dict], normativa: list[dict]) -> dict:
    """Genera informe completo combinando todas las fuentes."""
    contexto = f"""
DATOS CATASTRO:
{json.dumps(datos_catastro, ensure_ascii=False, indent=2)}

FRAGMENTOS PGOU:
{json.dumps(chunks_pgou, ensure_ascii=False, indent=2)}

NORMATIVA BOC/BOPA/BOE:
{json.dumps(normativa, ensure_ascii=False, indent=2)}
"""
    texto = llm_client.complete(SYSTEM_INFORME, contexto, max_tokens=2000)
    return _parse_json_response(texto)


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
        pag_inicio = metadatos.get("pagina_inicio", "?")
        pag_fin = metadatos.get("pagina_fin", "?")
        similitud = chunk.get("similitud", 0)

        # Cabecera del fragmento
        cabecera_parts = []
        if articulo:
            cabecera_parts.append(articulo)
        if seccion:
            cabecera_parts.append(f"[{seccion}]")
        if pag_inicio != "?":
            if pag_inicio == pag_fin:
                cabecera_parts.append(f"(pág. {pag_inicio})")
            else:
                cabecera_parts.append(f"(págs. {pag_inicio}-{pag_fin})")
        if similitud > 0:
            cabecera_parts.append(f"relevancia: {similitud:.0%}")

        cabecera = " — ".join(cabecera_parts) if cabecera_parts else f"Fragmento {i}"

        bloques.append(f"--- {cabecera} ---\n{chunk['contenido']}")

    return "\n\n".join(bloques)


async def consultar_pgou(chunks: list[dict], pregunta: str, municipio: str) -> dict:
    """Responde una pregunta sobre el PGOU usando los chunks recuperados."""
    fragmentos_texto = _formatear_chunks_para_llm(chunks)
    contexto = f"""MUNICIPIO: {municipio}
PREGUNTA: {pregunta}

FRAGMENTOS DEL PGOU ({len(chunks)} encontrados):

{fragmentos_texto}"""
    texto = llm_client.complete(SYSTEM_PGOU, contexto, max_tokens=2000)
    return _parse_json_response(texto)


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
