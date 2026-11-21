"""sesiones de refresco: cuándo y por qué se revocaron

Revision ID: t0d7e3f5a1b6
Revises: s9c6d2e4f0a5
Create Date: 2026-11-21 12:00:00

Idempotente: las columnas solo se agregan si faltan. Permite la ventana de gracia de la rotación
del refresh y la purga periódica de sesiones viejas.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from app.idempotente import agregar_columna_si_no_existe, borrar_columna_si_existe

revision: str = "t0d7e3f5a1b6"
down_revision: str | None = "s9c6d2e4f0a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    agregar_columna_si_no_existe(
        "sesiones_refresh", sa.Column("revocada_en", sa.DateTime(timezone=True), nullable=True)
    )
    agregar_columna_si_no_existe(
        "sesiones_refresh", sa.Column("motivo_revocacion", sa.String(16), nullable=True)
    )


def downgrade() -> None:
    borrar_columna_si_existe("sesiones_refresh", "motivo_revocacion")
    borrar_columna_si_existe("sesiones_refresh", "revocada_en")
