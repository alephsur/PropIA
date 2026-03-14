"""Utilidades para comunidades autónomas y municipios."""

CCAA_MAP = {
    "cantabria": {"codigo": "39", "boletin": "BOC", "nombre": "Cantabria"},
    "asturias": {"codigo": "33", "boletin": "BOPA", "nombre": "Asturias"},
}

PROVINCIAS_CCAA = {
    "cantabria": "cantabria",
    "asturias": "asturias",
}

MUNICIPIOS_CODIGOS = {
    "cantabria": {
        "san vicente de la barquera": "078",
        "santander": "075",
        "torrelavega": "174",
        "castro urdiales": "019",
    },
    "asturias": {
        "oviedo": "044",
        "gijon": "024",
        "aviles": "004",
        "mieres": "039",
        "langreo": "033",
    },
}


def get_ccaa_from_provincia(provincia: str) -> str | None:
    return PROVINCIAS_CCAA.get(provincia.lower())


def get_codigo_provincia(ccaa: str) -> str | None:
    info = CCAA_MAP.get(ccaa.lower())
    return info["codigo"] if info else None


def get_codigo_municipio(ccaa: str, municipio: str) -> str | None:
    municipios = MUNICIPIOS_CODIGOS.get(ccaa.lower(), {})
    return municipios.get(municipio.lower())


def slug(texto: str) -> str:
    """Convierte texto a slug para rutas de ficheros."""
    import unicodedata
    import re
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = texto.lower()
    texto = re.sub(r"[^\w\s-]", "", texto)
    texto = re.sub(r"[\s_-]+", "_", texto)
    return texto.strip("_")
