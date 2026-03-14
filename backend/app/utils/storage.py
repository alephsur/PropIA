"""Gestión de almacenamiento de PDFs."""
import aiofiles
from pathlib import Path
from app.config import get_settings
from app.utils.ccaa import slug

settings = get_settings()


def get_ruta_municipio(provincia: str, municipio: str) -> Path:
    """Devuelve la ruta base para documentos de un municipio."""
    base = Path(settings.storage_path)
    return base / slug(provincia) / slug(municipio)


async def guardar_pdf(contenido: bytes, provincia: str, municipio: str, nombre: str) -> Path:
    """Guarda un PDF en el sistema de ficheros y devuelve la ruta."""
    ruta_base = get_ruta_municipio(provincia, municipio)
    ruta_base.mkdir(parents=True, exist_ok=True)
    nombre_fichero = slug(nombre) + ".pdf"
    ruta = ruta_base / nombre_fichero
    async with aiofiles.open(ruta, "wb") as f:
        await f.write(contenido)
    return ruta


async def leer_pdf(ruta: str) -> bytes:
    """Lee un PDF del sistema de ficheros."""
    async with aiofiles.open(ruta, "rb") as f:
        return await f.read()


def eliminar_pdf(ruta: str) -> bool:
    """Elimina un PDF del sistema de ficheros."""
    path = Path(ruta)
    if path.exists():
        path.unlink()
        return True
    return False
