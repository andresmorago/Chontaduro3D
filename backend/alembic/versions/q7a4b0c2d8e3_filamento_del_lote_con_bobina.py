"""Producción: cada línea de filamento de un lote puede apuntar a una bobina de Spoolman

Revision ID: q7a4b0c2d8e3
Revises: p6f3a9b1c7d2
Create Date: 2026-11-21 00:10:00

Idempotente: usa los ayudantes de app/idempotente.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from app.idempotente import agregar_columna_si_no_existe, borrar_columna_si_existe

revision: str = "q7a4b0c2d8e3"
down_revision: str | None = "p6f3a9b1c7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    agregar_columna_si_no_existe("produccion_filamentos", sa.Column("spool_id", sa.Integer))


def downgrade() -> None:
    borrar_columna_si_existe("produccion_filamentos", "spool_id")
