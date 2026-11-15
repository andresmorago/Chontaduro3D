"""configuración de la impresora y de la cuenta de Bambu Cloud, guardada en la base (cifrada)

Revision ID: m3c0d6e8f4a9
Revises: l2b9c5d7e3f8
Create Date: 2026-11-15 12:00:00

Idempotente: usa los ayudantes de app/idempotente.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from app.idempotente import (
    agregar_columna_si_no_existe,
    borrar_columna_si_existe,
    borrar_tabla_si_existe,
    crear_tabla_si_no_existe,
)

revision: str = "m3c0d6e8f4a9"
down_revision: str | None = "l2b9c5d7e3f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    crear_tabla_si_no_existe(
        "impresora_config",
        sa.Column("id", sa.SmallInteger, primary_key=True, server_default="1"),
        sa.Column("ip", sa.String(45)),
        sa.Column("serial", sa.String(32)),
        sa.Column("codigo_acceso", sa.Text),
        sa.Column("version", sa.Integer, server_default="1", nullable=False),
        sa.Column("nube_sesion", sa.Text),
        sa.Column("nube_correo", sa.String(254)),
        sa.Column("nube_solicitada_en", sa.DateTime(timezone=True)),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.CheckConstraint("id = 1", name="ck_impresora_config_fila_unica"),
    )  # fmt: skip
    agregar_columna_si_no_existe(
        "impresora_estado", sa.Column("nube_atendida_en", sa.DateTime(timezone=True))
    )
    agregar_columna_si_no_existe("impresora_estado", sa.Column("config_version", sa.Integer))
    agregar_columna_si_no_existe("impresora_estado", sa.Column("conexion_error", sa.String(20)))


def downgrade() -> None:
    for col in ("conexion_error", "config_version", "nube_atendida_en"):
        borrar_columna_si_existe("impresora_estado", col)
    borrar_tabla_si_existe("impresora_config")
