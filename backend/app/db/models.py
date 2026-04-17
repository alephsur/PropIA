import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, Integer, Float, Text, DateTime,
    ForeignKey, UniqueConstraint, func
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    pass


class DocumentoBiblioteca(Base):
    __tablename__ = "documentos_biblioteca"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    municipio = Column(Text, nullable=False)
    provincia = Column(Text, nullable=False)
    ccaa = Column(Text, nullable=False)
    nombre = Column(Text, nullable=False)
    seccion = Column(Text)  # Normativa|Memoria|Fichas|PEPRI|...
    ruta_local = Column(Text, nullable=False)
    url_origen = Column(Text)
    tamanio_bytes = Column(Integer)
    indexado = Column(Boolean, default=False)
    descargado_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("municipio", "provincia", "nombre", name="uq_doc_municipio_nombre"),
    )


class TareaBackground(Base):
    __tablename__ = "tareas_background"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tipo = Column(Text, nullable=False)  # descarga_pdf|indexar_pdf|scraping_url
    status = Column(Text, nullable=False, default="pending")  # pending|running|done|error
    municipio = Column(Text)
    provincia = Column(Text)
    url_origen = Column(Text)
    detalle = Column(JSONB, default=dict)
    mensaje = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PgouMunicipio(Base):
    __tablename__ = "pgou_municipios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    municipio = Column(Text, nullable=False)
    provincia = Column(Text, nullable=False)
    ccaa = Column(Text, nullable=False)
    total_chunks = Column(Integer, default=0)
    ultimo_indexado = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("municipio", "provincia", name="uq_pgou_municipio"),
    )


class PgouChunk(Base):
    __tablename__ = "pgou_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    municipio = Column(Text, nullable=False)
    provincia = Column(Text, nullable=False)
    documento_id = Column(UUID(as_uuid=True))     # FK blanda a documentos_biblioteca
    seccion = Column(Text)
    articulo = Column(Text)
    contenido = Column(Text, nullable=False)
    embedding = Column(Vector(1024))
    pagina = Column(Integer, nullable=True)        # página del PDF fuente (para deep-link)
    metadatos = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class NormativaCache(Base):
    __tablename__ = "normativa_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clave = Column(Text, unique=True, nullable=False)  # "{ccaa}:{terminos}:{fecha_desde}"
    resultado = Column(JSONB, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PgouFichaAA(Base):
    """Ficha de Desarrollo del PGOU: un ámbito de actuación (AA V1, AA BA, URB SM…).

    Cada ficha describe un ámbito concreto del plan con sus condiciones urbanísticas.
    Las referencias catastrales se almacenan normalizadas en PgouRefCatastral (1:N).
    """
    __tablename__ = "pgou_fichas_aa"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # FK blanda a pgou_municipios (mismo patrón que documento_id en pgou_chunks)
    municipio_id = Column(UUID(as_uuid=True), nullable=False)
    # FK blanda a documentos_biblioteca — el PDF donde se encontró esta ficha
    documento_id = Column(UUID(as_uuid=True), nullable=True)
    # Identificador del ámbito tal como aparece en el PGOU: 'AA V1', 'AA BA', 'URB SM'
    id_ambito = Column(String(30), nullable=False)
    # Núcleo / zona geográfica: 'La Villa', 'El Barcenal', 'Santa Marina'…
    localizacion = Column(Text, nullable=True)
    # Uso predominante según el PGOU: Residencial, Viario, Industrial…
    uso_predominante = Column(Text, nullable=True)
    tipologia_edificatoria = Column(Text, nullable=True)
    ordenanza_referencia = Column(Text, nullable=True)
    # Datos numéricos del ámbito
    sup_ambito_m2 = Column(Float, nullable=True)
    edificabilidad_m2c = Column(Float, nullable=True)
    num_viviendas_estimado = Column(Integer, nullable=True)
    # Texto del campo "Condiciones" — obligaciones del propietario, retranqueos, etc.
    condiciones = Column(Text, nullable=True)
    # Texto completo de la ficha tal como se extrajo del PDF
    texto_ficha = Column(Text, nullable=True)
    # Página del PDF donde empieza esta ficha (para deep-link en Biblioteca)
    pagina_inicio = Column(Integer, nullable=True)
    # Todos los campos extraídos por Claude durante la indexación (schema completo):
    # localizacion, objetivos, uso_predominante, tipologia_edificatoria,
    # ordenanza_referencia, sup_ambito_m2, sup_redes_publicas_m2, sup_computable_m2,
    # edificabilidad_m2c, num_viviendas_estimado, cesiones (dict), instrumento_gestion,
    # instrumento_ejecucion, instrumento_planeamiento, plazos, prioridades,
    # condiciones (array de strings), referencias_catastrales_texto
    datos_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relación con las referencias catastrales normalizadas
    refs_catastrales = relationship(
        "PgouRefCatastral",
        back_populates="ficha",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PgouRefCatastral(Base):
    """Referencia catastral normalizada extraída de una ficha del PGOU.

    Una fila por cada parcela individual. Ejemplo:
      "Parcelas 13 y 14 de la MANZANA 67441 del CATASTRO URBANO."
      → fila 1: manzana='67441', parcela='13'
      → fila 2: manzana='67441', parcela='14'

    Cruce con RC urbana (ej. 6646704UP8064N0001ST):
      manzana = rc[0:5]  → '66467'
      parcela = rc[5:7]  → '04'   (con cero a la izquierda si es dígito único)
    """
    __tablename__ = "pgou_refs_catastrales"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ficha_id = Column(
        UUID(as_uuid=True),
        ForeignKey("pgou_fichas_aa.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Manzana (catastro urbano) o Polígono (catastro rústico), sin ceros a la izquierda
    manzana = Column(String(20), nullable=False)
    # Parcela con cero a la izquierda para coincidir con chars 6-7 de la RC urbana
    parcela = Column(String(10), nullable=False)
    # 'urbano' | 'rustico' — el Catastro Rústico usa polígono/parcela con distinta RC
    tipo_catastro = Column(String(10), nullable=False, default="urbano")
    # Frase original del documento de la que se extrajo esta referencia (para auditoría)
    texto_original = Column(Text, nullable=True)

    ficha = relationship("PgouFichaAA", back_populates="refs_catastrales")
