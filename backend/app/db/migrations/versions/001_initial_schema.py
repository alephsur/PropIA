"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # documentos_biblioteca
    op.create_table(
        "documentos_biblioteca",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("municipio", sa.Text, nullable=False),
        sa.Column("provincia", sa.Text, nullable=False),
        sa.Column("ccaa", sa.Text, nullable=False),
        sa.Column("nombre", sa.Text, nullable=False),
        sa.Column("seccion", sa.Text),
        sa.Column("ruta_local", sa.Text, nullable=False),
        sa.Column("url_origen", sa.Text),
        sa.Column("tamanio_bytes", sa.Integer),
        sa.Column("indexado", sa.Boolean, server_default="false"),
        sa.Column("descargado_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("municipio", "provincia", "nombre", name="uq_doc_municipio_nombre"),
    )

    # tareas_background
    op.create_table(
        "tareas_background",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tipo", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("municipio", sa.Text),
        sa.Column("provincia", sa.Text),
        sa.Column("url_origen", sa.Text),
        sa.Column("detalle", postgresql.JSONB, server_default="{}"),
        sa.Column("mensaje", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # pgou_municipios
    op.create_table(
        "pgou_municipios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("municipio", sa.Text, nullable=False),
        sa.Column("provincia", sa.Text, nullable=False),
        sa.Column("ccaa", sa.Text, nullable=False),
        sa.Column("total_chunks", sa.Integer, server_default="0"),
        sa.Column("ultimo_indexado", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("municipio", "provincia", name="uq_pgou_municipio"),
    )

    # pgou_chunks
    op.create_table(
        "pgou_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("municipio", sa.Text, nullable=False),
        sa.Column("provincia", sa.Text, nullable=False),
        sa.Column("documento_id", postgresql.UUID(as_uuid=True)),
        sa.Column("seccion", sa.Text),
        sa.Column("articulo", sa.Text),
        sa.Column("contenido", sa.Text, nullable=False),
        sa.Column("embedding", sa.Text),  # Will be replaced by vector type via raw SQL
        sa.Column("metadatos", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    # Add vector column properly
    op.execute("ALTER TABLE pgou_chunks ADD COLUMN IF NOT EXISTS embedding vector(1024)")
    op.execute("ALTER TABLE pgou_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE pgou_chunks ADD COLUMN embedding vector(1024)")
    op.execute("CREATE INDEX IF NOT EXISTS pgou_chunks_embedding_idx ON pgou_chunks USING ivfflat (embedding vector_cosine_ops)")

    # normativa_cache
    op.create_table(
        "normativa_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("clave", sa.Text, unique=True, nullable=False),
        sa.Column("resultado", postgresql.JSONB, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )


def downgrade() -> None:
    op.drop_table("normativa_cache")
    op.drop_table("pgou_chunks")
    op.drop_table("pgou_municipios")
    op.drop_table("tareas_background")
    op.drop_table("documentos_biblioteca")
