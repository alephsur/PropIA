"""Initial schema: all PropIA v3 tables

Revision ID: 001_initial
Revises: 
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector.sqlalchemy

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # tareas_background
    op.create_table(
        "tareas_background",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("municipio", sa.Text()),
        sa.Column("provincia", sa.Text()),
        sa.Column("url_origen", sa.Text()),
        sa.Column("mensaje", sa.Text()),
        sa.Column("detalle", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # documentos_biblioteca
    op.create_table(
        "documentos_biblioteca",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("municipio", sa.Text(), nullable=False),
        sa.Column("provincia", sa.Text(), nullable=False),
        sa.Column("ccaa", sa.Text(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("seccion", sa.Text()),
        sa.Column("ruta_local", sa.Text(), nullable=False),
        sa.Column("url_origen", sa.Text()),
        sa.Column("tamanio_bytes", sa.Integer()),
        sa.Column("indexado", sa.Boolean(), server_default="false"),
        sa.Column("descargado_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("municipio", "provincia", "nombre", name="uq_doc_municipio_nombre"),
    )

    # pgou_municipios
    op.create_table(
        "pgou_municipios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("municipio", sa.Text(), nullable=False),
        sa.Column("provincia", sa.Text(), nullable=False),
        sa.Column("ccaa", sa.Text(), nullable=False),
        sa.Column("total_chunks", sa.Integer(), server_default="0"),
        sa.Column("indexado_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("municipio", "provincia", name="uq_pgou_municipio"),
    )

    # pgou_chunks with pgvector
    op.create_table(
        "pgou_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("municipio_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("pgou_municipios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("documento_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documentos_biblioteca.id", ondelete="SET NULL")),
        sa.Column("municipio", sa.Text(), nullable=False),
        sa.Column("provincia", sa.Text(), nullable=False),
        sa.Column("seccion", sa.Text()),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("pagina", sa.Integer()),
        sa.Column("chunk_index", sa.Integer(), server_default="0"),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(1024)),
        sa.Column("metadatos", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # IVFFlat index for cosine similarity search
    op.execute(
        "CREATE INDEX pgou_chunks_embedding_idx ON pgou_chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    # normativa_cache
    op.create_table(
        "normativa_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("clave", sa.Text(), unique=True, nullable=False),
        sa.Column("resultado", postgresql.JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("normativa_cache")
    op.drop_table("pgou_chunks")
    op.drop_table("pgou_municipios")
    op.drop_table("documentos_biblioteca")
    op.drop_table("tareas_background")
