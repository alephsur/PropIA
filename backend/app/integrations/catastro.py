"""
Integración con la API del Catastro OVC.
VALIDADO: POST form-urlencoded. GET con parámetros vacíos → HTTP 400.
Provincia y Municipio siempre obligatorios.
"""
import httpx
import xml.etree.ElementTree as ET
from pydantic import BaseModel
from app.utils.logger import get_logger

logger = get_logger(__name__)

OVC_BASE = "https://ovc.catastro.meh.es/ovcservweb/ovcswlocalizacionrc"
_NS = {"c": "http://www.catastro.meh.es/"}

_CLASE = {"UR": "Urbano", "RU": "Rústico", "BI": "Bien Inmueble"}


class DatosCatastro(BaseModel):
    referencia_catastral: str | None = None
    clase: str | None = None
    direccion: str | None = None
    municipio: str | None = None
    provincia: str | None = None
    codigo_postal: str | None = None
    uso: str | None = None
    superficie_construida_m2: float | None = None
    superficie_parcela_m2: float | None = None
    ano_construccion: int | None = None
    valor_catastral: float | None = None
    coeficiente_participacion: str | None = None
    latitud: float | None = None
    longitud: float | None = None


def _parse_dnprc_xml(xml_text: str) -> DatosCatastro:
    """Parsea la respuesta XML de Consulta_DNPRC y devuelve DatosCatastro."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning(f"Error parseando XML catastro: {e}")
        return DatosCatastro()

    bi = root.find(".//c:bi", _NS)
    if bi is None:
        return DatosCatastro()

    # Referencia catastral
    rc_el = bi.find(".//c:rc", _NS)
    rc = None
    if rc_el is not None:
        pc1 = rc_el.findtext("c:pc1", "", _NS)
        pc2 = rc_el.findtext("c:pc2", "", _NS)
        car = rc_el.findtext("c:car", "", _NS)
        cc1 = rc_el.findtext("c:cc1", "", _NS)
        cc2 = rc_el.findtext("c:cc2", "", _NS)
        rc = f"{pc1}{pc2}{car}{cc1}{cc2}" or None

    # Clase
    cn = bi.findtext(".//c:cn", "", _NS)
    clase = _CLASE.get(cn, cn) or None

    # Localización textual completa
    ldt = bi.findtext("c:ldt", "", _NS) or None

    # Municipio, provincia y código postal
    dt = bi.find("c:dt", _NS)
    municipio = dt.findtext("c:nm", "", _NS) or None if dt is not None else None
    provincia = dt.findtext("c:np", "", _NS) or None if dt is not None else None
    codigo_postal = bi.findtext(".//c:dp", "", _NS) or None

    # Uso y coeficiente de participación
    debi = bi.find("c:debi", _NS)
    uso = debi.findtext("c:luso", "", _NS) or None if debi is not None else None
    cpt = debi.findtext("c:cpt", "", _NS) or None if debi is not None else None

    return DatosCatastro(
        referencia_catastral=rc,
        clase=clase,
        direccion=ldt,
        municipio=municipio,
        provincia=provincia,
        codigo_postal=codigo_postal,
        uso=uso,
        coeficiente_participacion=cpt,
    )


async def post_dnprc(provincia: str, municipio: str, rc: str) -> DatosCatastro:
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
        return _parse_dnprc_xml(resp.text)


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
