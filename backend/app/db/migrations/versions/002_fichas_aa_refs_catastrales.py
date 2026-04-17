"""Fichas AA y referencias catastrales cruzadas

Revision ID: 002
Revises: 001
Create Date: 2026-04-16

Cambios:
- pgou_chunks: añade columna 'pagina' para deep-link a la Biblioteca
- pgou_fichas_aa: fichas de desarrollo del PGOU (AA, URB, etc.) con datos estructurados
- pgou_refs_catastrales: referencias normalizadas manzana+parcela, una fila por parcela,
  permite cruzar cualquier RC con los ámbitos del plan directamente por índice B-tree.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # 1. pgou_chunks: añadir 'pagina' para referenciar la página exacta del PDF
    #    Permite al frontend mostrar "Ver fuente → documento.pdf, pág. 47"
    # -----------------------------------------------------------------------
    op.add_column(
        "pgou_chunks",
        sa.Column("pagina", sa.Integer, nullable=True),
    )

    # -----------------------------------------------------------------------
    # 2. pgou_fichas_aa: una fila por ámbito del plan (AA V1, AA BA, URB SM…)
    #
    #    - municipio_id / documento_id: FK sin constraint dura para no romper
    #      si se borra un documento (mismo patrón que documento_id en pgou_chunks)
    #    - id_ambito: código del plan, ej. 'AA V1', 'AA BA', 'URB SM'
    #    - pagina_inicio: primera página de esta ficha en el PDF fuente
    #    - texto_ficha: texto completo extraído, para búsqueda y auditoría
    #    - condiciones: campo "Condiciones" de la ficha (texto normativo relevante)
    # -----------------------------------------------------------------------
    op.create_table(
        "pgou_fichas_aa",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        # Municipio al que pertenece (FK blanda, mismo patrón que el resto)
        sa.Column("municipio_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Documento de la Biblioteca donde está esta ficha
        sa.Column("documento_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Identificador del ámbito tal como aparece en el PGOU
        sa.Column("id_ambito", sa.String(30), nullable=False),
        # Núcleo / zona geográfica dentro del municipio
        sa.Column("localizacion", sa.Text, nullable=True),
        # Uso predominante: Residencial, Viario, Industrial…
        sa.Column("uso_predominante", sa.Text, nullable=True),
        # Tipología edificatoria si la hay
        sa.Column("tipologia_edificatoria", sa.Text, nullable=True),
        # Ordenanza urbanística de referencia
        sa.Column("ordenanza_referencia", sa.Text, nullable=True),
        # Datos numéricos del ámbito
        sa.Column("sup_ambito_m2", sa.Float, nullable=True),
        sa.Column("edificabilidad_m2c", sa.Float, nullable=True),
        sa.Column("num_viviendas_estimado", sa.Integer, nullable=True),
        # Texto del campo "Condiciones" de la ficha (normativa accionable)
        sa.Column("condiciones", sa.Text, nullable=True),
        # Texto completo de la ficha para auditoría / re-indexación
        sa.Column("texto_ficha", sa.Text, nullable=True),
        # Página del PDF donde comienza esta ficha (para deep-link en Biblioteca)
        sa.Column("pagina_inicio", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
    )

    op.create_index(
        "ix_pgou_fichas_aa_municipio_id",
        "pgou_fichas_aa",
        ["municipio_id"],
    )
    op.create_index(
        "ix_pgou_fichas_aa_documento_id",
        "pgou_fichas_aa",
        ["documento_id"],
    )
    # Búsqueda por código de ámbito dentro de un municipio
    op.create_index(
        "ix_pgou_fichas_aa_municipio_ambito",
        "pgou_fichas_aa",
        ["municipio_id", "id_ambito"],
    )

    # -----------------------------------------------------------------------
    # 3. pgou_refs_catastrales: tabla de cruce normalizada
    #
    #    Una fila por cada parcela referenciada en cada ficha.
    #    Ejemplo: "Parcelas 1, 3 a 6 de la MANZANA 66467" genera 5 filas:
    #      (ficha_id, '66467', '01'), (ficha_id, '66467', '03'),
    #      (ficha_id, '66467', '04'), (ficha_id, '66467', '05'),
    #      (ficha_id, '66467', '06')
    #
    #    Esto permite la consulta más directa posible:
    #      SELECT f.* FROM pgou_fichas_aa f
    #      JOIN pgou_refs_catastrales r ON r.ficha_id = f.id
    #      WHERE r.manzana = '66467' AND r.parcela = '04'
    #
    #    Y el cruce desde RC (ej. 6646704UP8064N0001ST):
    #      manzana = rc[0:5]  → '66467'
    #      parcela = rc[5:7]  → '04'
    #
    #    tipo_catastro distingue urbano (manzana/parcela) de rústico (polígono/parcela)
    #    ya que el Catastro Rústico usa "Polígono N, Parcela M" con distinta semántica.
    # -----------------------------------------------------------------------
    op.create_table(
        "pgou_refs_catastrales",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "ficha_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pgou_fichas_aa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Manzana (catastro urbano) o Polígono (catastro rústico)
        # Almacenado sin ceros a la izquierda para coincidir con la RC real
        # Ej: '66467', '76992', '97391'
        sa.Column("manzana", sa.String(20), nullable=False),
        # Parcela con cero a la izquierda si es un solo dígito, para coincidir
        # con los chars 6-7 de la RC urbana. Ej: '04', '13', '14', '01'
        sa.Column("parcela", sa.String(10), nullable=False),
        # 'urbano' | 'rustico' — la RC rústica tiene formato distinto
        sa.Column(
            "tipo_catastro",
            sa.String(10),
            nullable=False,
            server_default="urbano",
        ),
        # Texto exacto del documento del que se extrajo esta referencia
        # Ej: "Parcelas 13 y 14 de la MANZANA 67441 del CATASTRO URBANO."
        sa.Column("texto_original", sa.Text, nullable=True),
    )

    # Índice principal: lookup directo desde manzana+parcela extraídos de una RC
    op.create_index(
        "ix_pgou_refs_manzana_parcela",
        "pgou_refs_catastrales",
        ["manzana", "parcela"],
    )
    # Índice para obtener todas las parcelas de una ficha (para listar ámbito completo)
    op.create_index(
        "ix_pgou_refs_ficha_id",
        "pgou_refs_catastrales",
        ["ficha_id"],
    )
    # Índice solo por manzana (útil si solo se conoce la manzana, sin parcela concreta)
    op.create_index(
        "ix_pgou_refs_manzana",
        "pgou_refs_catastrales",
        ["manzana"],
    )


def downgrade() -> None:
    op.drop_table("pgou_refs_catastrales")
    op.drop_table("pgou_fichas_aa")
    op.drop_column("pgou_chunks", "pagina")
