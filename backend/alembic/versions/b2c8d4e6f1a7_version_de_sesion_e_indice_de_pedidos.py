"""versión de sesión del usuario e índice de pedidos por fecha

Revision ID: b2c8d4e6f1a7
Revises: a1f4c7e2b903
Create Date: 2026-11-13 14:00:00

- usuarios.version_sesion: permite invalidar de golpe los JWT de acceso ya emitidos
  (cambio de contraseña, robo de sesión detectado).
- ix_pedidos_creado_en: el límite horario de pedidos cuenta por fecha.

Idempotente: usa los ayudantes de app/idempotente.py para poder repetirse sobre un esquema parcial.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from app.idempotente import (
    agregar_columna_si_no_existe,
    borrar_columna_si_existe,
    borrar_indice_si_existe,
    crear_indice_si_no_existe,
)

revision: str = "b2c8d4e6f1a7"
down_revision: str | None = "a1f4c7e2b903"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    agregar_columna_si_no_existe(
        "usuarios",
        sa.Column("version_sesion", sa.Integer, server_default=sa.text("0"), nullable=False),
    )
    crear_indice_si_no_existe("ix_pedidos_creado_en", "pedidos", ["creado_en"])


def downgrade() -> None:
    borrar_indice_si_existe("ix_pedidos_creado_en", "pedidos")
    borrar_columna_si_existe("usuarios", "version_sesion")
