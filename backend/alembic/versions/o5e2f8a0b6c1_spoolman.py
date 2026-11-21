"""Spoolman: estado de la conexión, bobinas por ranura y descuento de filamento por trabajo

Revision ID: o5e2f8a0b6c1
Revises: n4d1e7f9a5b0
Create Date: 2026-11-19 12:00:00

Idempotente: usa los ayudantes de app/idempotente.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.idempotente import (
    agregar_columna_si_no_existe,
    borrar_columna_si_existe,
    borrar_tabla_si_existe,
    crear_indice_si_no_existe,
    crear_tabla_si_no_existe,
)

revision: str = "o5e2f8a0b6c1"
down_revision: str | None = "n4d1e7f9a5b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ESTADOS = ("sin_bobina", "por_enviar", "enviando", "descontado", "omitido", "revisar")


def upgrade() -> None:
    crear_tabla_si_no_existe(
        "spoolman_estado",
        sa.Column("id", sa.SmallInteger, primary_key=True, server_default="1"),
        sa.Column("desde", sa.DateTime(timezone=True)),
        sa.Column("conectado", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("version", sa.String(20)),
        sa.Column("ultimo_ok_en", sa.DateTime(timezone=True)),
        sa.Column("detalle", sa.String(200)),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.CheckConstraint("id = 1", name="ck_spoolman_estado_fila_unica"),
    )  # fmt: skip
    crear_tabla_si_no_existe(
        "ranura_bobinas",
        sa.Column("ranura", sa.String(4), primary_key=True),
        sa.Column("spool_id", sa.Integer, nullable=False),
        sa.Column("tipo", sa.String(20)),
        sa.Column("color", sa.String(7)),
        sa.Column("vinculada_en", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
    )  # fmt: skip
    crear_tabla_si_no_existe(
        "consumos_filamento",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("trabajo_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("trabajos_impresora.id", ondelete="CASCADE"), nullable=False),
        sa.Column("orden", sa.SmallInteger, server_default="0", nullable=False),
        sa.Column("tipo", sa.String(20)),
        sa.Column("color", sa.String(7)),
        sa.Column("gramos_plan", sa.Numeric(10, 2), nullable=False),
        sa.Column("gramos", sa.Numeric(10, 2), nullable=False),
        sa.Column("ranura", sa.String(4)),
        sa.Column("spool_id", sa.Integer),
        sa.Column("estado", sa.String(12), server_default="sin_bobina", nullable=False),
        sa.Column("detalle", sa.String(200)),
        sa.Column("intentos", sa.SmallInteger, server_default="0", nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("descontado_en", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("trabajo_id", "orden", name="uq_consumos_filamento_trabajo_orden"),
        sa.CheckConstraint(
            "estado IN (" + ", ".join(repr(e) for e in ESTADOS) + ")",
            name="ck_consumos_filamento_estado_valido",
        ),
        sa.CheckConstraint("gramos >= 0", name="ck_consumos_filamento_gramos_no_negativos"),
    )  # fmt: skip
    crear_indice_si_no_existe(
        "ix_consumos_filamento_trabajo_id", "consumos_filamento", ["trabajo_id"]
    )
    agregar_columna_si_no_existe("trabajos_impresora", sa.Column("bandejas", postgresql.JSONB))


def downgrade() -> None:
    borrar_columna_si_existe("trabajos_impresora", "bandejas")
    borrar_tabla_si_existe("consumos_filamento")
    borrar_tabla_si_existe("ranura_bobinas")
    borrar_tabla_si_existe("spoolman_estado")
