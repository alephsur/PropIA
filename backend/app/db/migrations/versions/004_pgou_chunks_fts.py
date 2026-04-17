"""Full-text search en pgou_chunks para búsqueda híbrida (semántica + lexical)

Revision ID: 004
Revises: 003
Create Date: 2026-04-16

Añade columna tsvector generada automáticamente sobre (articulo + contenido)
con diccionario 'spanish', y un índice GIN para búsquedas ts_rank eficientes.

La búsqueda RAG combina por Reciprocal Rank Fusion los resultados de:
  - Similitud coseno sobre embeddings (captura semántica)
  - ts_rank sobre tsvector (captura términos exactos, números, referencias)

Esto es especialmente útil en texto jurídico donde "artículo 4.3.1",
"coeficiente de ponderación 1,20", etc. son términos exactos que los
embeddings dispersan pero el FTS encuentra con precisión.
"""
from typing import Sequence, Union
from alembic import op


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Columna generada: se recalcula automáticamente en INSERT/UPDATE
    # No necesita trigger, no requiere re-indexación manual.
    op.execute("""
        ALTER TABLE pgou_chunks
        ADD COLUMN tsv tsvector
        GENERATED ALWAYS AS (
            to_tsvector(
                'spanish',
                coalesce(articulo, '') || ' ' || coalesce(contenido, '')
            )
        ) STORED
    """)

    op.execute("""
        CREATE INDEX ix_pgou_chunks_tsv
        ON pgou_chunks
        USING GIN (tsv)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_pgou_chunks_tsv")
    op.execute("ALTER TABLE pgou_chunks DROP COLUMN IF EXISTS tsv")
