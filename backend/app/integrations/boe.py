"""Integración con BOE, BOC (Cantabria) y BOPA (Asturias)."""
import httpx
from bs4 import BeautifulSoup
from datetime import datetime
from pydantic import BaseModel
from app.utils.logger import get_logger

logger = get_logger(__name__)


class NormativaItem(BaseModel):
    titulo: str
    fecha: str | None = None
    url: str | None = None
    resumen: str | None = None
    fuente: str  # BOE|BOC|BOPA


async def buscar_boe(q: str, fecha_desde: str | None = None) -> list[NormativaItem]:
    """Búsqueda en API REST del BOE."""
    params = {"q": q, "_type": "json"}
    if fecha_desde:
        params["fechaDesde"] = fecha_desde

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            "https://www.boe.es/datosabiertos/api/boe/buscar",
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

    resultados = []
    for item in data.get("response", {}).get("results", {}).get("result", []):
        resultados.append(NormativaItem(
            titulo=item.get("titulo", ""),
            fecha=item.get("fecha_publicacion"),
            url=item.get("url_pdf"),
            resumen=item.get("texto"),
            fuente="BOE",
        ))
    return resultados


async def buscar_boc(q: str, fecha_desde: str | None = None) -> list[NormativaItem]:
    """Scraping del BOC de Cantabria."""
    url = "https://boc.cantabria.es/boces/busquedaAvanzadaAction.do"
    params = {"texto": q}

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

    resultados = []
    # Parse BOC results - structure may vary
    for item in soup.select(".resultado-busqueda, .boletin-item")[:10]:
        titulo_el = item.select_one("h3, .titulo, a")
        if titulo_el:
            resultados.append(NormativaItem(
                titulo=titulo_el.get_text(strip=True),
                url=titulo_el.get("href"),
                fuente="BOC",
            ))
    
    logger.info(f"BOC búsqueda '{q}': {len(resultados)} resultados")
    return resultados


async def buscar_bopa(q: str, fecha_desde: str | None = None) -> list[NormativaItem]:
    """Scraping del BOPA de Asturias."""
    url = "https://sede.asturias.es/bopa"
    params = {"q": q}

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

    resultados = []
    for item in soup.select(".resultado, .bopa-item, article")[:10]:
        titulo_el = item.select_one("h3, h2, .titulo, a")
        if titulo_el:
            resultados.append(NormativaItem(
                titulo=titulo_el.get_text(strip=True),
                url=titulo_el.get("href"),
                fuente="BOPA",
            ))

    logger.info(f"BOPA búsqueda '{q}': {len(resultados)} resultados")
    return resultados
