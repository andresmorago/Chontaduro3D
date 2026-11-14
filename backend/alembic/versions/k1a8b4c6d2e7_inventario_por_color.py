"""inventario por color: el color de cada movimiento, línea de producción y línea de venta

Revision ID: k1a8b4c6d2e7
Revises: j0f7a3b5c1d6
Create Date: 2026-11-15 10:00:00

Idempotente: usa los ayudantes de app/idempotente.py. No reescribe datos: lo que ya existe queda con
color NULL («sin color asignado») y se reasigna con un ajuste cuando la persona quiera.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from app.idempotente import (
    agregar_columna_si_no_existe,
    borrar_columna_si_existe,
    crear_indice_si_no_existe,
)

revision: str = "k1a8b4c6d2e7"
down_revision: str | None = "j0f7a3b5c1d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLAS = ("movimientos_inventario", "produccion_items", "venta_items")


def upgrade() -> None:
    for tabla in TABLAS:
        agregar_columna_si_no_existe(
            tabla,
            sa.Column(
                "color_id", pg.UUID(as_uuid=True),
                sa.ForeignKey("articulo_colores.id", ondelete="SET NULL"), nullable=True,
            ),
        )  # fmt: skip
        crear_indice_si_no_existe(f"ix_{tabla}_color_id", tabla, ["color_id"])


def downgrade() -> None:
    for tabla in TABLAS:
        borrar_columna_si_existe(tabla, "color_id")  # arrastra su FK e índice
