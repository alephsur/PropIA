"""Endpoints del módulo Catastro."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from app.integrations.catastro import post_dnprc, post_dnploc, post_cpmrc, post_rccoor
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/catastro", tags=["Catastro"])


class ConsultaRC(BaseModel):
    provincia: str
    municipio: str
    rc: str

    @field_validator("provincia", "municipio", "rc")
    @classmethod
    def no_vacio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("El campo no puede estar vacío")
        return v.strip()


class ConsultaDireccion(BaseModel):
    provincia: str
    municipio: str
    tipo_via: str
    nom_via: str
    numero: str = ""
    bloque: str = ""
    escalera: str = ""
    planta: str = ""
    puerta: str = ""


class ConsultaCoordenadas(BaseModel):
    lat: float
    lon: float


@router.post("/dnprc")
async def consulta_dnprc(body: ConsultaRC):
    """Consulta datos catastrales por Referencia Catastral."""
    try:
        return await post_dnprc(body.provincia, body.municipio, body.rc)
    except Exception as e:
        logger.error(f"Error Catastro DNPRC: {e}")
        raise HTTPException(status_code=502, detail=f"Error consultando Catastro: {str(e)}")


@router.post("/dnploc")
async def consulta_dnploc(body: ConsultaDireccion):
    """Consulta datos catastrales por dirección."""
    try:
        return await post_dnploc(
            body.provincia, body.municipio, body.tipo_via, body.nom_via,
            body.numero, body.bloque, body.escalera, body.planta, body.puerta
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/cpmrc")
async def consulta_cpmrc(body: ConsultaRC):
    """Obtiene coordenadas de una RC."""
    try:
        return await post_cpmrc(body.provincia, body.municipio, body.rc)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/rccoor")
async def consulta_rccoor(body: ConsultaCoordenadas):
    """Obtiene RC a partir de coordenadas."""
    try:
        return await post_rccoor(body.lat, body.lon)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
