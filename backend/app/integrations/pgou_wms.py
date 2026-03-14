"""
Integración WMS/WFS para CCAA con soporte.
NOTA: Cantabria y Asturias NO tienen WMS/WFS de planeamiento.
Se usa exclusivamente el índice IA de PDFs para estas CCAA.
"""
from app.utils.logger import get_logger

logger = get_logger(__name__)

CCAA_SIN_WMS = {"cantabria", "asturias"}


def tiene_wms(ccaa: str) -> bool:
    return ccaa.lower() not in CCAA_SIN_WMS


async def consultar_wms(ccaa: str, municipio: str, lat: float, lon: float) -> dict | None:
    """Consulta WMS si la CCAA lo soporta."""
    if not tiene_wms(ccaa):
        logger.info(f"{ccaa} no tiene WMS/WFS - usar índice IA de PDFs")
        return None
    # TODO: Implementar para otras CCAA
    raise NotImplementedError(f"WMS no implementado para {ccaa}")
