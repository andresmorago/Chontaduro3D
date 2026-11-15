"""una venta puede asociarse (opcionalmente) a un pedido del catálogo

Revision ID: n4d1e7f9a5b0
Revises: m3c0d6e8f4a9
Create Date: 2026-11-15 14:00:00

Idempotente: usa los ayudantes de app/idempotente.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from app.idempotente import (
    agregar_columna_si_no_existe,
    borrar_columna_si_existe,
    borrar_indice_si_existe,
    crear_indice_si_no_existe,
)

revision: str = "n4d1e7f9a5b0"
down_revision: str | None = "m3c0d6e8f4a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    agregar_columna_si_no_existe(
        "ventas",
        sa.Column(
            "pedido_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("pedidos.id", ondelete="SET NULL", name="fk_ventas_pedido_id_pedidos"),
        ),
    )  # fmt: skip
    crear_indice_si_no_existe("ix_ventas_pedido_id", "ventas", ["pedido_id"])


def downgrade() -> None:
    borrar_indice_si_existe("ix_ventas_pedido_id", "ventas")
    borrar_columna_si_existe("ventas", "pedido_id")
