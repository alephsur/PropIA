"""Endpoints del módulo Planeamiento / PGOU."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import PgouMunicipio
from app.ai.pgou_index import buscar_pgou
from app.services.ai_synthesis import consultar_pgou
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/urbanismo", tags=["Urbanismo"])

# Consultas predefinidas agrupadas por categoría.
# Diseñadas con vocabulario técnico del PGOU para maximizar la recuperación RAG.
CONSULTAS_TIPO = [
    {
        "categoria": "Clasificación y usos del suelo",
        "consultas": [
            {"titulo": "Clasificación del suelo", "consulta": "clasificación suelo urbano urbanizable no urbanizable"},
            {"titulo": "Usos permitidos zona residencial", "consulta": "usos permitidos zona residencial vivienda unifamiliar"},
            {"titulo": "Usos prohibidos", "consulta": "usos prohibidos incompatibles"},
            {"titulo": "Uso global y pormenorizado", "consulta": "uso global pormenorizado residencial comercial industrial"},
        ],
    },
    {
        "categoria": "Edificabilidad y parámetros",
        "consultas": [
            {"titulo": "Edificabilidad máxima", "consulta": "índice edificabilidad máxima m2 techo m2 suelo coeficiente"},
            {"titulo": "Altura máxima", "consulta": "altura máxima plantas metros cornisa cumbrera"},
            {"titulo": "Ocupación máxima", "consulta": "ocupación máxima parcela porcentaje"},
            {"titulo": "Retranqueos y separaciones", "consulta": "retranqueos separación linderos frente fondo"},
            {"titulo": "Parcela mínima", "consulta": "parcela mínima superficie frente mínimo"},
        ],
    },
    {
        "categoria": "Coeficientes y valores",
        "consultas": [
            {"titulo": "Coeficientes de ponderación", "consulta": "coeficiente ponderación usos vivienda residencial tabla valores"},
            {"titulo": "Aprovechamiento tipo", "consulta": "aprovechamiento tipo medio área reparto unidades"},
            {"titulo": "Cesiones obligatorias", "consulta": "cesiones obligatorias dotaciones zonas verdes equipamiento"},
        ],
    },
    {
        "categoria": "Condiciones generales",
        "consultas": [
            {"titulo": "Condiciones estéticas", "consulta": "condiciones estéticas fachada materiales cubierta color"},
            {"titulo": "Aparcamientos", "consulta": "dotación aparcamiento plazas garaje vivienda"},
            {"titulo": "Protección patrimonial", "consulta": "protección patrimonio catalogado BIC grado intervención"},
            {"titulo": "Zonas verdes y espacios libres", "consulta": "zonas verdes espacios libres dotaciones locales"},
        ],
    },
    {
        "categoria": "Procedimientos",
        "consultas": [
            {"titulo": "Licencia de obra", "consulta": "licencia obra mayor menor comunicación previa requisitos"},
            {"titulo": "Segregación y parcelación", "consulta": "segregación parcelación división parcela condiciones"},
            {"titulo": "Régimen de fuera de ordenación", "consulta": "fuera ordenación régimen transitorio volumen disconforme"},
        ],
    },
]


class ConsultaUrbanismo(BaseModel):
    provincia: str
    municipio: str
    rc: str | None = None
    consulta: str = "Clasificación del suelo, zonificación y usos permitidos"


@router.post("/informe")
async def informe_urbanismo(body: ConsultaUrbanismo, db: AsyncSession = Depends(get_db)):
    """Consulta el PGOU por RAG y genera informe urbanístico."""
    try:
        chunks = await buscar_pgou(db, body.municipio, body.provincia, body.consulta)
        resultado = await consultar_pgou(chunks, body.consulta, body.municipio)
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error informe urbanismo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/consultas-tipo")
async def consultas_tipo():
    """Devuelve consultas predefinidas agrupadas por categoría."""
    return CONSULTAS_TIPO


@router.get("/municipios")
async def listar_municipios_indexados(
    ccaa: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Lista municipios con documentos PGOU indexados."""
    query = select(PgouMunicipio)
    if ccaa:
        query = query.where(PgouMunicipio.ccaa == ccaa.lower())
    result = await db.execute(query.order_by(PgouMunicipio.municipio))
    municipios = result.scalars().all()
    return [
        {
            "municipio": m.municipio,
            "provincia": m.provincia,
            "ccaa": m.ccaa,
            "total_chunks": m.total_chunks,
            "ultimo_indexado": m.ultimo_indexado.isoformat() if m.ultimo_indexado else None,
        }
        for m in municipios
    ]
