"""Integración con BOE, BOC (Cantabria) y BOPA (Asturias).

Estrategias verificadas:
- BOC: AJAX busquedaBoletines.do (JSON) → verBoletin.do (HTML) → buscar títulos
- BOE: GET buscar/boe.php con parámetros de formulario correctos → parsear li.resultado-busqueda
- BOPA: AJAX SedeBopaSearchDateWeb (calendar HTML) → bopa-sumario (HTML) → buscar títulos
"""
import asyncio
import json
import re
from datetime import datetime, timedelta
from urllib.parse import urlencode, urljoin, quote

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel

from app.utils.logger import get_logger

logger = get_logger(__name__)

BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

BOC_BASE = "https://boc.cantabria.es"
BOE_BASE = "https://www.boe.es"
BOPA_BASE = "https://miprincipado.asturias.es"

# Límite de boletines a procesar por búsqueda
_MAX_BOLETINES = 45  # ~1.5 meses de boletines
_MAX_RESULTADOS = 15


class NormativaItem(BaseModel):
    titulo: str
    fecha: str | None = None
    url: str | None = None
    resumen: str | None = None
    fuente: str  # BOE | BOC | BOPA


# ── Utilidades ────────────────────────────────────────────────

def _meses_recientes(fecha_desde: str | None, max_meses: int = 3) -> list[tuple[int, int]]:
    """Devuelve lista de (mes, año) desde fecha_desde hasta hoy, máximo max_meses."""
    hoy = datetime.today()
    if fecha_desde:
        try:
            inicio = datetime.strptime(fecha_desde, "%Y-%m-%d")
        except ValueError:
            try:
                inicio = datetime.strptime(fecha_desde, "%d/%m/%Y")
            except ValueError:
                inicio = hoy - timedelta(days=max_meses * 30)
    else:
        inicio = hoy - timedelta(days=max_meses * 30)

    meses = []
    current = hoy
    while current >= inicio and len(meses) < max_meses:
        meses.append((current.month, current.year))
        # Retroceder un mes
        if current.month == 1:
            current = current.replace(year=current.year - 1, month=12)
        else:
            current = current.replace(month=current.month - 1)

    return meses


def _contiene_query(texto: str, q: str) -> bool:
    """Comprueba si el texto contiene todas las palabras de la query."""
    palabras = [p.lower().strip() for p in q.split() if len(p.strip()) > 2]
    texto_lower = texto.lower()
    return all(p in texto_lower for p in palabras)


# ── BOC ──────────────────────────────────────────────────────

async def _boc_ids_mes(client: httpx.AsyncClient, mes: int, year: int) -> list[dict]:
    """Obtiene IDs de boletines para un mes/año via AJAX."""
    try:
        resp = await client.post(
            f"{BOC_BASE}/boces/busquedaBoletines.do",
            params={"mes": mes, "year": year},
            headers={
                **BASE_HEADERS,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": f"{BOC_BASE}/boces/inicioCargaInicialBoletines.do",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning(f"BOC busquedaBoletines mes={mes} year={year}: {e}")
        return []


async def _boc_buscar_boletin(
    client: httpx.AsyncClient,
    boletin_id: int,
    fecha_str: str,
    q: str,
) -> list[NormativaItem]:
    """Busca en un boletín del BOC los anuncios que coincidan con la query."""
    try:
        resp = await client.get(
            f"{BOC_BASE}/boces/verBoletin.do",
            params={"idBolOrd": boletin_id},
            headers={
                **BASE_HEADERS,
                "Referer": f"{BOC_BASE}/boces/inicioCargaInicialBoletines.do",
            },
            timeout=20,
        )
        resp.raise_for_status()
        # El BOC usa ISO-8859-1
        soup = BeautifulSoup(resp.content.decode("iso-8859-1", errors="replace"), "lxml")
    except Exception as e:
        logger.warning(f"BOC verBoletin id={boletin_id}: {e}")
        return []

    resultados = []
    contenido = soup.find("div", id="contenido")
    if not contenido:
        return []

    # Cada anuncio: <p>TITULO</p> seguido de <div class="enlacesDoc">
    parrafos = contenido.find_all("p")
    for p in parrafos:
        titulo = p.get_text(strip=True)
        if not titulo or len(titulo) < 10:
            continue
        if not _contiene_query(titulo, q):
            continue

        # Buscar el enlace al PDF/anuncio en el siguiente sibling
        url_anuncio = None
        siguiente = p.find_next_sibling()
        while siguiente and siguiente.name not in ("p", "span", "h1", "h2", "h3"):
            enlace = siguiente.find("a", href=lambda h: h and "verAnuncioAction" in h)
            if enlace:
                href = enlace["href"]
                url_anuncio = href if href.startswith("http") else f"{BOC_BASE}/boces/{href}"
                break
            siguiente = siguiente.find_next_sibling()

        resultados.append(NormativaItem(
            titulo=titulo,
            fecha=fecha_str,
            url=url_anuncio,
            fuente="BOC",
        ))

        if len(resultados) >= 5:  # Máximo 5 por boletín
            break

    return resultados


async def buscar_boc(q: str, fecha_desde: str | None = None) -> list[NormativaItem]:
    """Búsqueda en el BOC de Cantabria mediante scraping de boletines recientes."""
    meses = _meses_recientes(fecha_desde, max_meses=3)

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        # Obtener sesión del BOC (necesaria para acceder a verBoletin.do)
        try:
            await client.get(
                f"{BOC_BASE}/boces/inicioCargaInicialBoletines.do",
                headers=BASE_HEADERS,
            )
        except Exception:
            pass

        # Primero obtener IDs de todos los boletines de los meses a buscar
        id_tasks = [_boc_ids_mes(client, mes, year) for mes, year in meses]
        mes_resultados = await asyncio.gather(*id_tasks)

        # Aplanar y ordenar por fecha descendente
        todos_boletines = []
        for boletines_mes in mes_resultados:
            for b in boletines_mes:
                todos_boletines.append(b)

        # Ordenar por ID descendente (IDs más altos = más recientes)
        todos_boletines.sort(key=lambda x: x.get("id", 0), reverse=True)
        todos_boletines = todos_boletines[:_MAX_BOLETINES]

        if not todos_boletines:
            logger.warning(f"BOC: no se encontraron boletines para búsqueda '{q}'")
            return []

        # Buscar en boletines en lotes concurrentes
        resultados: list[NormativaItem] = []
        tam_lote = 5

        for i in range(0, len(todos_boletines), tam_lote):
            lote = todos_boletines[i:i + tam_lote]
            tasks = [
                _boc_buscar_boletin(client, b["id"], b.get("fecBolString", ""), q)
                for b in lote
            ]
            lote_resultados = await asyncio.gather(*tasks)
            for items in lote_resultados:
                resultados.extend(items)

            if len(resultados) >= _MAX_RESULTADOS:
                break

        logger.info(f"BOC búsqueda '{q}': {len(resultados)} resultados")
        return resultados[:_MAX_RESULTADOS]


# ── BOE ──────────────────────────────────────────────────────

async def buscar_boe(q: str, fecha_desde: str | None = None) -> list[NormativaItem]:
    """Búsqueda en el BOE usando el formulario HTML oficial."""
    # Parámetros correctos del formulario de búsqueda del BOE
    params: dict = {
        "campo[0]": "ORIS",
        "dato[0][1]": "1",
        "dato[0][2]": "2",
        "dato[0][3]": "3",
        "campo[1]": "TITULOS",
        "dato[1]": q,
        "accion": "Buscar",
        "lang": "es",
    }
    if fecha_desde:
        try:
            # BOE acepta fechas en campo6 (desde) con formato dd/mm/yyyy
            d = datetime.strptime(fecha_desde, "%Y-%m-%d")
            params["campo[6]"] = "PUBLI"
            params["dato[6][0]"] = d.strftime("%d/%m/%Y")
            params["dato[6][1]"] = datetime.today().strftime("%d/%m/%Y")
        except ValueError:
            pass

    url = f"{BOE_BASE}/buscar/boe.php"
    headers = {
        **BASE_HEADERS,
        "Referer": f"{BOE_BASE}/buscar/boe.php",
    }

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        # Primera petición para obtener cookie de sesión
        try:
            await client.get(url, headers=headers)
        except Exception:
            pass

        try:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Error BOE '{q}': {e}")
            raise

    soup = BeautifulSoup(resp.text, "lxml")
    resultados = _parsear_boe(soup)
    logger.info(f"BOE búsqueda '{q}': {len(resultados)} resultados")
    return resultados


def _parsear_boe(soup: BeautifulSoup) -> list[NormativaItem]:
    """Parsea los resultados HTML del BOE.

    Estructura: <li class="resultado-busqueda">
      <p class="linea-dem">Departamento</p>
      <p class="linea-pub">BOE 189 de 09/08/2006 - III. Otras disposiciones</p>
      <p>Descripción del texto</p>
      <a href="../buscar/doc.php?id=BOE-A-...">enlace</a>
    """
    resultados = []

    items = soup.select("li.resultado-busqueda")
    for item in items[:_MAX_RESULTADOS]:
        # Descripción (primer <p> sin clase específica)
        desc_p = item.find("p", class_=lambda c: not c)
        if not desc_p:
            # Intentar cualquier <p> que no sea linea-dem ni linea-pub
            for p in item.find_all("p"):
                classes = p.get("class", [])
                if not classes or not any(c in ["linea-dem", "linea-pub"] for c in classes):
                    desc_p = p
                    break

        titulo = desc_p.get_text(strip=True) if desc_p else ""
        if not titulo:
            continue

        # Fecha de publicación
        pub_p = item.find("p", class_="linea-pub")
        fecha = None
        if pub_p:
            pub_text = pub_p.get_text(strip=True)
            # Extraer fecha del formato "BOE 189 de 09/08/2006 - ..."
            fecha_match = re.search(r"\d{2}/\d{2}/\d{4}", pub_text)
            if fecha_match:
                fecha = fecha_match.group()

        # Departamento como resumen
        dep_p = item.find("p", class_="linea-dem")
        resumen = dep_p.get_text(strip=True) if dep_p else None

        # URL del documento
        enlace = item.find("a", href=True)
        url_doc = None
        if enlace:
            href = enlace["href"]
            # Resolver URL relativa
            if href.startswith("../"):
                url_doc = f"{BOE_BASE}/{href[3:]}"
            elif href.startswith("/"):
                url_doc = f"{BOE_BASE}{href}"
            elif href.startswith("http"):
                url_doc = href
            else:
                url_doc = urljoin(f"{BOE_BASE}/buscar/", href)

        resultados.append(NormativaItem(
            titulo=titulo,
            fecha=fecha,
            url=url_doc,
            resumen=resumen,
            fuente="BOE",
        ))

    return resultados


# ── BOPA ─────────────────────────────────────────────────────

_BOPA_PORTLET_SUMMARY = "pa_sede_bopa_web_portlet_SedeBopaSummaryWeb"
_BOPA_PORTLET_CALENDAR = "pa_sede_bopa_web_portlet_SedeBopaSearchDateWeb"


async def _bopa_fechas_mes(
    client: httpx.AsyncClient, mes: int, year: int
) -> list[str]:
    """Obtiene las fechas con boletín publicado para un mes/año."""
    portlet_id = _BOPA_PORTLET_CALENDAR
    params = {
        "p_p_id": portlet_id,
        "p_p_lifecycle": "2",
        "p_p_state": "normal",
        "p_p_mode": "view",
        "p_p_resource_id": "/searchdate/calendar",
    }
    try:
        resp = await client.post(
            f"{BOPA_BASE}/bopa",
            params=params,
            data={"mes": mes, "year": year},
            headers={
                **BASE_HEADERS,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": f"{BOPA_BASE}/bopa",
                "Accept": "application/json, text/html, */*",
            },
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"BOPA calendar mes={mes} year={year}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    # Extraer fechas de los enlaces del calendario
    # Los <td class="bopa-day"> contienen <a href="...summaryDate=DD%2FMM%2FYYYY...">
    fechas = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        # URL: .../bopa-sumario?...p_r_p_summaryDate=DD%2FMM%2FYYYY...
        fecha_match = re.search(r"summaryDate=(\d{2}%2F\d{2}%2F\d{4})", href)
        if fecha_match:
            fecha_encoded = fecha_match.group(1)
            fecha_decoded = fecha_encoded.replace("%2F", "/")
            fechas.append(fecha_decoded)

    # Ordenar descendentemente (más reciente primero)
    def parse_fecha(f: str) -> datetime:
        try:
            return datetime.strptime(f, "%d/%m/%Y")
        except ValueError:
            return datetime.min

    fechas.sort(key=parse_fecha, reverse=True)
    return fechas


async def _bopa_buscar_sumario(
    client: httpx.AsyncClient,
    fecha: str,
    q: str,
) -> list[NormativaItem]:
    """Busca en el sumario del BOPA de un día concreto."""
    summary_url = (
        f"{BOPA_BASE}/bopa-sumario"
        f"?p_p_id={_BOPA_PORTLET_SUMMARY}"
        f"&p_p_lifecycle=0"
        f"&p_r_p_summaryDate={quote(fecha, safe='')}"
        f"&p_r_p_summaryIsSearch=false"
    )
    try:
        resp = await client.get(
            summary_url,
            headers={**BASE_HEADERS, "Referer": f"{BOPA_BASE}/bopa"},
            timeout=25,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"BOPA sumario fecha={fecha}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    return _parsear_bopa_sumario(soup, fecha, q)


def _parsear_bopa_sumario(
    soup: BeautifulSoup, fecha: str, q: str
) -> list[NormativaItem]:
    """Parsea el HTML del sumario diario del BOPA."""
    resultados = []

    # Buscar el contenedor del portlet
    contenedor = soup.find(id=f"portlet_{_BOPA_PORTLET_SUMMARY}")
    if not contenedor:
        contenedor = soup  # fallback: buscar en toda la página

    # Estructura: <dl><dt>TÍTULO</dt><dd><a href="...">Texto</a></dd></dl>
    for dt in contenedor.find_all("dt"):
        titulo = dt.get_text(strip=True)
        if not titulo or len(titulo) < 10:
            continue
        if not _contiene_query(titulo, q):
            continue

        # URL en el <dd> siguiente
        dd = dt.find_next_sibling("dd")
        url_anuncio = None
        if dd:
            enlace = dd.find("a", href=True)
            if enlace:
                href = enlace["href"]
                url_anuncio = href if href.startswith("http") else urljoin(BOPA_BASE, href)

        resultados.append(NormativaItem(
            titulo=titulo,
            fecha=fecha,
            url=url_anuncio,
            fuente="BOPA",
        ))

        if len(resultados) >= 5:
            break

    return resultados


async def buscar_bopa(q: str, fecha_desde: str | None = None) -> list[NormativaItem]:
    """Búsqueda en el BOPA de Asturias mediante scraping de boletines recientes."""
    meses = _meses_recientes(fecha_desde, max_meses=3)

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        # Obtener sesión del BOPA
        try:
            await client.get(f"{BOPA_BASE}/bopa", headers=BASE_HEADERS)
        except Exception:
            pass

        # Obtener fechas con boletín publicado para los meses a buscar
        fecha_tasks = [_bopa_fechas_mes(client, mes, year) for mes, year in meses]
        mes_fechas = await asyncio.gather(*fecha_tasks)

        # Aplanar y ordenar descendentemente
        todas_fechas: list[str] = []
        for fechas_mes in mes_fechas:
            todas_fechas.extend(fechas_mes)

        def parse_fecha_bopa(f: str) -> datetime:
            try:
                return datetime.strptime(f, "%d/%m/%Y")
            except ValueError:
                return datetime.min

        todas_fechas.sort(key=parse_fecha_bopa, reverse=True)
        todas_fechas = list(dict.fromkeys(todas_fechas))[:_MAX_BOLETINES]  # dedup

        if not todas_fechas:
            logger.warning(f"BOPA: no se encontraron fechas para búsqueda '{q}'")
            return []

        # Buscar en sumarios concurrentemente
        resultados: list[NormativaItem] = []
        tam_lote = 5

        for i in range(0, len(todas_fechas), tam_lote):
            lote = todas_fechas[i:i + tam_lote]
            tasks = [_bopa_buscar_sumario(client, fecha, q) for fecha in lote]
            lote_resultados = await asyncio.gather(*tasks)
            for items in lote_resultados:
                resultados.extend(items)

            if len(resultados) >= _MAX_RESULTADOS:
                break

        logger.info(f"BOPA búsqueda '{q}': {len(resultados)} resultados")
        return resultados[:_MAX_RESULTADOS]
