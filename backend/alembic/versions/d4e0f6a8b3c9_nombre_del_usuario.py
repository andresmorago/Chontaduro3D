"""nombre del usuario (módulo de administración)

Revision ID: d4e0f6a8b3c9
Revises: c3d9e5f7a2b8
Create Date: 2026-11-13 18:00:00

Idempotente: usa los ayudantes de app/idempotente.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from app.idempotente import agregar_columna_si_no_existe, borrar_columna_si_existe

revision: str = "d4e0f6a8b3c9"
down_revision: str | None = "c3d9e5f7a2b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    agregar_columna_si_no_existe("usuarios", sa.Column("nombre", sa.String(80)))


def downgrade() -> None:
    borrar_columna_si_existe("usuarios", "nombre")
