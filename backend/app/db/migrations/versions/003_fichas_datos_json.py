"""Añadir datos_json a pgou_fichas_aa para almacenar todos los campos extraídos con Claude

Revision ID: 003
Revises: 002
Create Date: 2026-04-16

Cambios:
- pgou_fichas_aa: añade columna datos_json (JSONB) con todos los campos de la ficha
  extraídos por Claude durante la indexación. Incluye campos no modelados en columnas
  separadas: objetivos, superficies desglosadas, cesiones, instrumentos, plazos,
  prioridades, condiciones como array, referencias catastrales en texto.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pgou_fichas_aa",
        sa.Column("datos_json", postgresql.JSONB, nullable=True),
    )
    # Índice GIN para búsquedas dentro del JSONB (ej: condiciones que mencionan "PEPRI")
    op.create_index(
        "ix_pgou_fichas_aa_datos_json",
        "pgou_fichas_aa",
        ["datos_json"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_pgou_fichas_aa_datos_json", table_name="pgou_fichas_aa")
    op.drop_column("pgou_fichas_aa", "datos_json")
