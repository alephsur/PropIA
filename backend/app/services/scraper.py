"""Scraping de páginas de urbanismo de ayuntamientos."""
import httpx
from bs4 import BeautifulSoup
from pathlib import Path
from pydantic import BaseModel
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DocumentoEncontrado(BaseModel):
    nombre: str
    url_origen: str
    seccion: str
    extension: str = "pdf"
    tamanio_kb: int | None = None


def _detectar_seccion(href: str, nombre: str) -> str:
    h = (href + nombre).lower()
    if any(x in h for x in ["normativa", "ordenanza"]): return "Normativa"
    if any(x in h for x in ["memoria"]): return "Memoria"
    if any(x in h for x in ["plano", "planos", "o.1", "o.2", "o.3", "o.4", "o.5",
                              "o.6", "o.7", "o.8", "o.9"]): return "Planos"
    if any(x in h for x in ["ficha", "fichas"]): return "Fichas"
    if any(x in h for x in ["pepri", "casco"]): return "PEPRI"
    if any(x in h for x in ["catalogo", "cesr"]): return "Catálogo"
    if any(x in h for x in ["criterio", "crit"]): return "Criterios"
    if any(x in h for x in ["estudio", "detalle"]): return "Estudio Detalle"
    if any(x in h for x in ["boc", "bopa", "anuncio"]): return "Boletín"
    return "Otros"


async def scrape_documentos_url(
    url: str,
    municipio: str,
    provincia: str,
) -> list[DocumentoEncontrado]:
    """
    Hace scraping de una URL de ayuntamiento y devuelve todos los PDFs encontrados.
    """
    logger.info(f"Scraping {url} para {municipio}, {provincia}")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9",
    }
    async with httpx.AsyncClient(follow_redirects=True, timeout=20, headers=headers) as client:
        logger.info(f"Obteniendo {url}")
        resp = await client.get(url)
        logger.info(f"Respuesta: {resp.status_code}")
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    base_url = f"{resp.url.scheme}://{resp.url.host}"

    docs = []
    seen_urls = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.lower().endswith(".pdf"):
            continue

        url_completa = href if href.startswith("http") else base_url + href

        if url_completa in seen_urls:
            continue
        seen_urls.add(url_completa)

        nombre = a.get_text(strip=True) or Path(href).stem
        if not nombre:
            nombre = Path(href).name

        seccion = _detectar_seccion(href, nombre)

        docs.append(DocumentoEncontrado(
            nombre=nombre,
            url_origen=url_completa,
            seccion=seccion,
            extension="pdf",
        ))

    logger.info(f"Scraping {url}: {len(docs)} PDFs encontrados para {municipio}, {provincia}")
    return docs
