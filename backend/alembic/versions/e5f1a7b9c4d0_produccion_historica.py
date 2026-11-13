"""producción histórica: lotes que no suman al inventario actual

Revision ID: e5f1a7b9c4d0
Revises: d4e0f6a8b3c9
Create Date: 2026-11-13 20:00:00

Idempotente: usa los ayudantes de app/idempotente.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from app.idempotente import agregar_columna_si_no_existe, borrar_columna_si_existe

revision: str = "e5f1a7b9c4d0"
down_revision: str | None = "d4e0f6a8b3c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    agregar_columna_si_no_existe(
        "producciones",
        sa.Column("afecta_inventario", sa.Boolean, server_default=sa.text("true"), nullable=False),
    )


def downgrade() -> None:
    borrar_columna_si_existe("producciones", "afecta_inventario")
