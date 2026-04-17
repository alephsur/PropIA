"""Parser de Fichas de Desarrollo del PGOU.

Extrae datos estructurados del Volumen de Fichas (AA, URB, etc.) de cualquier PGOU.
Las referencias catastrales se normalizan en pares (manzana, parcela) individuales
para permitir cruce directo desde la RC del Catastro.

Cruce RC → manzana/parcela (catastro urbano):
  RC '6646704UP8064N0001ST'
       ^^^^^  ^^
       66467  04  → manzana='66467', parcela='04'

El texto de cada ficha en el PDF sigue un patrón tabular consistente en todos los
ayuntamientos que aplican LOTRUSCa (Cantabria) y legislación autonómica similar.
"""
import re
from dataclasses import dataclass, field
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ── Estructuras de datos ──────────────────────────────────────────────────────

@dataclass
class RefCatastral:
    """Referencia catastral normalizada: una fila en pgou_refs_catastrales."""
    manzana: str          # ej. '66467', '67441', '97391'
    parcela: str          # ej. '04', '13', '14' — siempre 2 chars con cero a la izquierda
    tipo_catastro: str    # 'urbano' | 'rustico'
    texto_original: str   # frase exacta del documento para auditoría


@dataclass
class FichaAA:
    """Ficha de Desarrollo del PGOU completamente parseada."""
    id_ambito: str                          # 'AA V1', 'AA BA', 'URB SM'
    localizacion: str = ""
    uso_predominante: str = ""
    tipologia_edificatoria: str = ""
    ordenanza_referencia: str = ""
    sup_ambito_m2: float | None = None
    edificabilidad_m2c: float | None = None
    num_viviendas_estimado: int | None = None
    condiciones: str = ""
    texto_ficha: str = ""                   # texto completo de la ficha (para auditoría)
    pagina_inicio: int | None = None        # página del PDF (para deep-link en Biblioteca)
    refs_catastrales: list[RefCatastral] = field(default_factory=list)


# ── Patrones de extracción ────────────────────────────────────────────────────

# Cabecera de ficha en el PDF: "DESARROLLO URBANO CONSOLIDADO   AA V1"
# Puede aparecer en una o dos líneas dependiendo del layout del PDF
_CABECERA_FICHA_RE = re.compile(
    r'DESARROLLO\s+URBANO\s+CONSOLIDADO\s+(AA\s+\w+)',
    re.IGNORECASE,
)

# Referencia catastral urbana: "Parcelas 13 y 14 de la MANZANA 67441 del CATASTRO URBANO"
# Variantes: "Parcela 7", "Parcialmente Parcela 7", "Parcelas 1, 3 a 6"
_REF_URBANA_RE = re.compile(
    r'(?:Parcialmente\s+)?Parcelas?\s+'
    r'([\d][0-9,\s]*(?:y\s+\d+)?(?:\s+a\s+\d+)?)'  # "13 y 14", "1, 3 a 6", "7"
    r'\s+de\s+la\s+MANZANA\s+(\d+)'
    r'\s+del\s+CATASTRO\s+URBANO',
    re.IGNORECASE,
)

# Referencia catastral rústica: "Parcelas 297 y 302 del Polígono 2 del Catastro Rústico"
_REF_RUSTICA_RE = re.compile(
    r'Parcelas?\s+([\d][0-9,\s]*(?:y\s+\d+)?(?:\s+a\s+\d+)?)'
    r'\s+del\s+Pol[íi]gono\s+(\d+)'
    r'\s+del\s+Catastro\s+R[uú]stico',
    re.IGNORECASE,
)

# Campo "Condiciones:" seguido de texto hasta el siguiente campo o fin de ficha
_CONDICIONES_RE = re.compile(
    r'Condiciones?:\s*\n?(.*?)(?=\n\s*(?:Localización|Catastro|Conexión|Los artículos|$))',
    re.IGNORECASE | re.DOTALL,
)

# Superficie del ámbito: "S. ámbito:  440 m2"
_SUP_AMBITO_RE = re.compile(
    r'S\.\s*[áa]mbito:\s*([\d.,]+)\s*m2',
    re.IGNORECASE,
)

# Edificabilidad: "1.759,73 m2c"
_EDIFICABILIDAD_RE = re.compile(
    r'([\d.,]+)\s*m2c',
    re.IGNORECASE,
)

# Nº viviendas: "Nº estimado de viviendas:\n17" o "N.º estimado de viviendas: 17"
_VIVIENDAS_RE = re.compile(
    r'N[ºo°]\.?\s*estimado\s+de\s+viviendas[:\s]+(\d+)',
    re.IGNORECASE,
)

# Uso predominante
_USO_RE = re.compile(
    r'Uso\s+predominante:\s*\n?\s*(.+?)(?=\n)',
    re.IGNORECASE,
)

# Tipología edificatoria
_TIPOLOGIA_RE = re.compile(
    r'Tipolog[íi]a\s+edificatoria:\s*\n?\s*(.+?)(?=\n)',
    re.IGNORECASE,
)

# Ordenanza de referencia
_ORDENANZA_RE = re.compile(
    r'Ordenanza\s+de\s+referencia:\s*\n?\s*(.+?)(?=\n)',
    re.IGNORECASE,
)

# Localización (primera línea de valor del campo)
_LOCALIZACION_RE = re.compile(
    r'Localizaci[oó]n:\s*\n?\s*(.+?)(?=\n)',
    re.IGNORECASE,
)


# ── Funciones auxiliares ──────────────────────────────────────────────────────

def rc_a_manzana_parcela(rc: str) -> tuple[str, str] | None:
    """Extrae manzana y parcela de una referencia catastral urbana española.

    Formato RC urbana (20 chars): MMMMMPPXXXXXX QQQQ CC
      - Chars 0-4 (5 chars): manzana catastral
      - Chars 5-6 (2 chars): parcela catastral (con cero a la izquierda)

    Ejemplo:
      '6646704UP8064N0001ST' → ('66467', '04')
      '6744113UP8064S0001YT' → ('67441', '13')

    Devuelve None si la RC no tiene formato urbano reconocible.
    """
    rc_clean = rc.strip().upper().replace(" ", "")
    if len(rc_clean) < 7:
        logger.warning(f"RC demasiado corta para extraer manzana/parcela: '{rc}'")
        return None
    manzana = rc_clean[0:5]
    parcela = rc_clean[5:7]
    # Validar que sean dígitos (RC urbana)
    if not manzana.isdigit() or not parcela.isdigit():
        logger.warning(f"RC no parece urbana (chars no numéricos en posición 0-6): '{rc}'")
        return None
    return manzana, parcela


def _expandir_parcelas(texto_parcelas: str) -> list[str]:
    """Normaliza y expande una lista de parcelas con rangos.

    Entrada:  '13 y 14'       → ['13', '14']
    Entrada:  '1, 3 a 6'      → ['01', '03', '04', '05', '06']
    Entrada:  '8 a 11 y 30'   → ['08', '09', '10', '11', '30']
    Entrada:  '7'             → ['07']
    Entrada:  '297 y 302'     → ['297', '302']  (rústico, > 2 dígitos)
    """
    texto = texto_parcelas.strip()
    # Normalizar "y" como separador a coma
    texto = re.sub(r'\s+y\s+', ',', texto)
    partes = re.split(r',', texto)

    parcelas: list[str] = []
    for parte in partes:
        parte = parte.strip()
        if not parte:
            continue
        # Detectar rango "N a M"
        rango = re.match(r'^(\d+)\s+a\s+(\d+)$', parte)
        if rango:
            inicio, fin = int(rango.group(1)), int(rango.group(2))
            if fin < inicio or fin - inicio > 200:
                # Rango sospechoso: guardar solo los extremos
                logger.warning(f"Rango de parcelas sospechoso: '{parte}', guardando extremos")
                parcelas.append(str(inicio).zfill(2))
                parcelas.append(str(fin).zfill(2))
            else:
                parcelas.extend(str(i).zfill(2) for i in range(inicio, fin + 1))
        else:
            num = re.match(r'^(\d+)', parte)
            if num:
                parcelas.append(str(int(num.group(1))).zfill(2))

    return parcelas


def _extraer_refs_catastrales(texto: str) -> list[RefCatastral]:
    """Extrae todas las referencias catastrales de un bloque de texto.

    Maneja catastro urbano (MANZANA) y rústico (Polígono).
    Expande rangos de parcelas en referencias individuales.
    """
    refs: list[RefCatastral] = []

    # Catastro urbano
    for match in _REF_URBANA_RE.finditer(texto):
        texto_parcelas, manzana = match.group(1), match.group(2)
        texto_original = match.group(0).strip()
        parcelas = _expandir_parcelas(texto_parcelas)
        for parcela in parcelas:
            refs.append(RefCatastral(
                manzana=manzana.lstrip('0') or '0',
                parcela=parcela,
                tipo_catastro='urbano',
                texto_original=texto_original,
            ))
        if parcelas:
            logger.debug(
                f"Refs urbanas extraídas: MANZANA {manzana} → parcelas {parcelas}"
            )

    # Catastro rústico (polígono/parcela)
    for match in _REF_RUSTICA_RE.finditer(texto):
        texto_parcelas, poligono = match.group(1), match.group(2)
        texto_original = match.group(0).strip()
        parcelas = _expandir_parcelas(texto_parcelas)
        for parcela in parcelas:
            refs.append(RefCatastral(
                manzana=poligono,          # en rústico, el "manzana" equivale al polígono
                parcela=parcela,
                tipo_catastro='rustico',
                texto_original=texto_original,
            ))

    return refs


def _extraer_numero(texto: str, patron: re.Pattern) -> float | None:
    """Extrae el primer número de un patrón en el texto."""
    match = patron.search(texto)
    if not match:
        return None
    try:
        return float(match.group(1).replace('.', '').replace(',', '.'))
    except (ValueError, IndexError):
        return None


def _extraer_campo(texto: str, patron: re.Pattern) -> str:
    """Extrae el primer grupo del patrón, limpiando espacios."""
    match = patron.search(texto)
    if not match:
        return ""
    return match.group(1).strip()


# ── Parser principal ──────────────────────────────────────────────────────────

def parsear_fichas_pdf(
    paginas: list[tuple[int, str]],
) -> list[FichaAA]:
    """Parsea un documento de Fichas de Desarrollo del PGOU.

    Entrada: lista de (nº_página, texto) como produce _extraer_texto_por_pagina
    en pgou_index.py.

    Retorna: lista de FichaAA con datos estructurados y refs catastrales normalizadas.
    """
    if not paginas:
        return []

    fichas: list[FichaAA] = []

    # Construir texto completo con mapa de offset → página
    texto_completo = ""
    page_offsets: list[tuple[int, int]] = []
    for page_num, page_text in paginas:
        page_offsets.append((len(texto_completo), page_num))
        texto_completo += page_text + "\n"

    # Localizar todas las cabeceras de fichas
    cabeceras_raw = list(_CABECERA_FICHA_RE.finditer(texto_completo))

    # Fusionar cabeceras consecutivas del mismo ámbito: cuando una ficha continúa
    # en la siguiente página, el ayuntamiento repite "DESARROLLO URBANO CONSOLIDADO
    # AA Xn" como encabezado de página. Sin esta fusión, el parser crearía dos
    # FichaAA parciales (cada una con la mitad del contenido).
    cabeceras: list[tuple[re.Match, str]] = []
    for match in cabeceras_raw:
        id_ambito = match.group(1).strip().upper()
        if cabeceras and cabeceras[-1][1] == id_ambito:
            continue  # continuación del mismo ámbito, no abrir nueva ficha
        cabeceras.append((match, id_ambito))

    if not cabeceras:
        logger.warning("No se encontraron fichas AA en el documento")
        return []

    duplicadas = len(cabeceras_raw) - len(cabeceras)
    logger.info(
        f"Fichas AA detectadas: {len(cabeceras)} "
        f"(de {len(cabeceras_raw)} cabeceras; {duplicadas} continuaciones fusionadas)"
    )

    for i, (match, id_ambito) in enumerate(cabeceras):
        inicio = match.start()
        fin = cabeceras[i + 1][0].start() if i + 1 < len(cabeceras) else len(texto_completo)
        texto_ficha = texto_completo[inicio:fin].strip()

        # Página de inicio (para deep-link en Biblioteca)
        pagina_inicio = _offset_a_pagina(inicio, page_offsets)

        # Extraer campos estructurados
        ficha = FichaAA(
            id_ambito=id_ambito,
            localizacion=_extraer_campo(texto_ficha, _LOCALIZACION_RE),
            uso_predominante=_extraer_campo(texto_ficha, _USO_RE),
            tipologia_edificatoria=_extraer_campo(texto_ficha, _TIPOLOGIA_RE),
            ordenanza_referencia=_extraer_campo(texto_ficha, _ORDENANZA_RE),
            sup_ambito_m2=_extraer_numero(texto_ficha, _SUP_AMBITO_RE),
            edificabilidad_m2c=_extraer_numero(texto_ficha, _EDIFICABILIDAD_RE),
            num_viviendas_estimado=_extraer_viviendas(texto_ficha),
            condiciones=_extraer_condiciones(texto_ficha),
            texto_ficha=texto_ficha,
            pagina_inicio=pagina_inicio,
            refs_catastrales=_extraer_refs_catastrales(texto_ficha),
        )

        fichas.append(ficha)
        logger.debug(
            f"  {id_ambito}: {ficha.localizacion!r}, "
            f"{len(ficha.refs_catastrales)} refs catastrales, "
            f"pág. {pagina_inicio}"
        )

    return fichas


def _offset_a_pagina(offset: int, page_offsets: list[tuple[int, int]]) -> int:
    """Devuelve el nº de página dado un offset de carácter en el texto completo."""
    pagina = 1
    for start, pag in page_offsets:
        if start <= offset:
            pagina = pag
        else:
            break
    return pagina


def _extraer_viviendas(texto: str) -> int | None:
    match = _VIVIENDAS_RE.search(texto)
    if not match:
        return None
    try:
        n = int(match.group(1))
        return n if n > 0 else None
    except ValueError:
        return None


def _extraer_condiciones(texto: str) -> str:
    """Extrae el bloque de condiciones de la ficha."""
    match = _CONDICIONES_RE.search(texto)
    if not match:
        return ""
    return re.sub(r'\s+', ' ', match.group(1)).strip()
