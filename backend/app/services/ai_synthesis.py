"""Síntesis de informes con el proveedor LLM configurado."""
import json
from app.ai import llm_client
from app.utils.logger import get_logger

logger = get_logger(__name__)

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
Recibes fragmentos de documentos PGOU y contestas preguntas concretas.
Responde ÚNICAMENTE con JSON válido:
{
  "clasificacion_suelo": "...",
  "zonificacion": "...",
  "uso_global": "Residencial|Comercial|Industrial|Equipamiento|...",
  "usos_permitidos": ["uso1"],
  "usos_prohibidos": ["uso1"],
  "edificabilidad": "... m²/m²",
  "altura_maxima": "... plantas / ... metros",
  "retranqueos": "...",
  "ocupacion_maxima": "...",
  "plan_vigente": "PGOU ... año",
  "articulos_referencia": ["Artículo X — PGOU 2015"],
  "confianza": "alta|media|baja",
  "nota": "si hay ambigüedad o fragmentos insuficientes"
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
    return json.loads(texto)


async def consultar_pgou(chunks: list[dict], pregunta: str, municipio: str) -> dict:
    """Responde una pregunta sobre el PGOU usando los chunks recuperados."""
    contexto = f"""
MUNICIPIO: {municipio}
PREGUNTA: {pregunta}

FRAGMENTOS PGOU RELEVANTES:
{json.dumps(chunks, ensure_ascii=False, indent=2)}
"""
    texto = llm_client.complete(SYSTEM_PGOU, contexto, max_tokens=1000)
    return json.loads(texto)


async def analizar_documento(contenido_base64: str, media_type: str, consulta: str | None = None) -> dict:
    """Analiza un documento con visión. Usa bloques de contenido multimodal."""
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

    texto = llm_client.complete(SYSTEM_DOCUMENTOS, bloques, max_tokens=2000)
    return json.loads(texto)
