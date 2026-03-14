"""
Integración con la API del Catastro OVC.
VALIDADO: POST form-urlencoded. GET con parámetros vacíos → HTTP 400.
Provincia y Municipio siempre obligatorios.
"""
import httpx
from pydantic import BaseModel
from app.utils.logger import get_logger

logger = get_logger(__name__)

OVC_BASE = "https://ovc.catastro.meh.es/ovcservweb/ovcswlocalizacionrc"


class DatosCatastro(BaseModel):
    referencia_catastral: str | None = None
    direccion: str | None = None
    municipio: str | None = None
    provincia: str | None = None
    superficie_construida_m2: float | None = None
    superficie_parcela_m2: float | None = None
    uso: str | None = None
    ano_construccion: int | None = None
    valor_catastral: float | None = None
    latitud: float | None = None
    longitud: float | None = None
    datos_raw: dict = {}


async def post_dnprc(provincia: str, municipio: str, rc: str) -> dict:
    """Consulta datos por Referencia Catastral."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{OVC_BASE}/OVCCallejero.asmx/Consulta_DNPRC",
            data={
                "Provincia": provincia.upper(),
                "Municipio": municipio.upper(),
                "RC": rc,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        logger.info(f"Catastro DNPRC OK: RC={rc}")
        return {"raw": resp.text, "status": resp.status_code}


async def post_dnploc(
    provincia: str, municipio: str, tipo_via: str, nom_via: str,
    numero: str = "", bloque: str = "", escalera: str = "",
    planta: str = "", puerta: str = ""
) -> dict:
    """Consulta datos por localización (dirección)."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{OVC_BASE}/OVCCallejero.asmx/Consulta_DNPLOC",
            data={
                "Provincia": provincia.upper(),
                "Municipio": municipio.upper(),
                "TipoVia": tipo_via,
                "NomVia": nom_via,
                "Numero": numero,
                "Bloque": bloque,
                "Escalera": escalera,
                "Planta": planta,
                "Puerta": puerta,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return {"raw": resp.text}


async def post_cpmrc(provincia: str, municipio: str, rc: str) -> dict:
    """Obtiene coordenadas de una RC."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{OVC_BASE}/OVCCoordenadas.asmx/Consulta_CPMRC",
            data={
                "Provincia": provincia.upper(),
                "Municipio": municipio.upper(),
                "SRS": "EPSG:4326",
                "RC": rc,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return {"raw": resp.text}


async def post_rccoor(lat: float, lon: float) -> dict:
    """Obtiene RC a partir de coordenadas."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{OVC_BASE}/OVCCoordenadas.asmx/Consulta_RCCOOR",
            data={
                "SRS": "EPSG:4326",
                "Coordenada_X": str(lon),
                "Coordenada_Y": str(lat),
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return {"raw": resp.text}
