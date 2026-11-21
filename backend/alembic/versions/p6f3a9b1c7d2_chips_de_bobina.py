"""Spoolman: memoria de los chips RFID ya leídos (para no registrar dos veces la misma bobina)

Revision ID: p6f3a9b1c7d2
Revises: o5e2f8a0b6c1
Create Date: 2026-11-20 23:30:00

Idempotente: usa los ayudantes de app/idempotente.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from app.idempotente import borrar_tabla_si_existe, crear_tabla_si_no_existe

revision: str = "p6f3a9b1c7d2"
down_revision: str | None = "o5e2f8a0b6c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    crear_tabla_si_no_existe(
        "chips_bobina",
        sa.Column("uid", sa.String(32), primary_key=True),
        sa.Column("spool_id", sa.Integer),
        sa.Column("visto_en", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
    )  # fmt: skip


def downgrade() -> None:
    borrar_tabla_si_existe("chips_bobina")
