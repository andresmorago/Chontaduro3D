"""Producción: costo congelado del filamento de cada línea de un lote

Revision ID: r8b5c1d3e9f4
Revises: q7a4b0c2d8e3
Create Date: 2026-11-21 04:00:00

Idempotente: usa los ayudantes de app/idempotente.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from app.idempotente import agregar_columna_si_no_existe, borrar_columna_si_existe

revision: str = "r8b5c1d3e9f4"
down_revision: str | None = "q7a4b0c2d8e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    agregar_columna_si_no_existe("produccion_filamentos", sa.Column("costo", sa.Numeric(14, 2)))


def downgrade() -> None:
    borrar_columna_si_existe("produccion_filamentos", "costo")
