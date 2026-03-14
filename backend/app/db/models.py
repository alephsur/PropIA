import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, Integer, Text, DateTime,
    UniqueConstraint, func
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase
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
    documento_id = Column(UUID(as_uuid=True))
    seccion = Column(Text)
    articulo = Column(Text)
    contenido = Column(Text, nullable=False)
    embedding = Column(Vector(1024))
    metadatos = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class NormativaCache(Base):
    __tablename__ = "normativa_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clave = Column(Text, unique=True, nullable=False)  # "{ccaa}:{terminos}:{fecha_desde}"
    resultado = Column(JSONB, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
