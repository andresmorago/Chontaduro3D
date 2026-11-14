"""colores por artículo y color elegido en el pedido

Revision ID: f6a2b8c0d5e1
Revises: e5f1a7b9c4d0
Create Date: 2026-11-14 09:00:00

Idempotente: usa los ayudantes de app/idempotente.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.idempotente import (
    agregar_columna_si_no_existe,
    borrar_columna_si_existe,
    borrar_tabla_si_existe,
    crear_indice_si_no_existe,
    crear_tabla_si_no_existe,
)

revision: str = "f6a2b8c0d5e1"
down_revision: str | None = "e5f1a7b9c4d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    crear_tabla_si_no_existe(
        "articulo_colores",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "articulo_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("articulos.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("orden", sa.SmallInteger, server_default="0", nullable=False),
        sa.Column("nombre", sa.String(30), nullable=False),
        sa.Column("hex", sa.String(7), nullable=False),
        sa.UniqueConstraint("articulo_id", "nombre", name="uq_articulo_colores_nombre"),
    )
    crear_indice_si_no_existe("ix_articulo_colores_articulo_id", "articulo_colores", ["articulo_id"])
    agregar_columna_si_no_existe("pedidos", sa.Column("color", sa.String(30), nullable=True))


def downgrade() -> None:
    borrar_columna_si_existe("pedidos", "color")
    borrar_tabla_si_existe("articulo_colores")
