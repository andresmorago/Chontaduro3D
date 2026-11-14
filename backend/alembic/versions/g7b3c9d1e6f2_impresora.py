"""impresora 3D: trabajos detectados, estado y comandos

Revision ID: g7b3c9d1e6f2
Revises: f6a2b8c0d5e1
Create Date: 2026-11-14 15:00:00

Idempotente: usa los ayudantes de app/idempotente.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from app.idempotente import (
    borrar_tabla_si_existe,
    crear_indice_si_no_existe,
    crear_tabla_si_no_existe,
)

revision: str = "g7b3c9d1e6f2"
down_revision: str | None = "f6a2b8c0d5e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    crear_tabla_si_no_existe(
        "trabajos_impresora",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"),
                  primary_key=True),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("archivo", sa.String(300)),
        sa.Column("tarea_id", sa.String(40), server_default="", nullable=False),
        sa.Column("estado", sa.String(12), server_default="en_curso", nullable=False),
        sa.Column("gestion", sa.String(10), server_default="pendiente", nullable=False),
        sa.Column("inicio_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("inicio_observado", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("fin_en", sa.DateTime(timezone=True)),
        sa.Column("progreso", sa.SmallInteger, server_default="0", nullable=False),
        sa.Column("plate", sa.SmallInteger),
        sa.Column("minutos_estimados", sa.Integer),
        sa.Column("gramos_total", sa.Numeric(10, 2)),
        sa.Column("filamentos", pg.JSONB),
        sa.Column("produccion_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("producciones.id", ondelete="SET NULL"), unique=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.CheckConstraint("estado IN ('en_curso', 'terminado', 'interrumpido')",
                           name="ck_trabajos_impresora_estado_valido"),
        sa.CheckConstraint("gestion IN ('pendiente', 'importado', 'ignorado')",
                           name="ck_trabajos_impresora_gestion_valida"),
    )  # fmt: skip
    crear_indice_si_no_existe(
        "ix_trabajos_impresora_gestion_fin", "trabajos_impresora", ["gestion", "fin_en"]
    )
    crear_tabla_si_no_existe(
        "impresora_estado",
        sa.Column("id", sa.SmallInteger, primary_key=True, server_default="1"),
        sa.Column("conectada", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("ultimo_mensaje_en", sa.DateTime(timezone=True)),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("datos", pg.JSONB),
        sa.CheckConstraint("id = 1", name="ck_impresora_estado_fila_unica"),
    )  # fmt: skip
    crear_tabla_si_no_existe(
        "impresora_comandos",
        sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
        sa.Column("comando", sa.String(12), nullable=False),
        sa.Column("valor", sa.String(12)),
        sa.Column("usuario_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
        sa.Column("estado", sa.String(10), server_default="pendiente", nullable=False),
        sa.Column("detalle", sa.String(200)),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("atendido_en", sa.DateTime(timezone=True)),
        sa.CheckConstraint("comando IN ('pausar', 'reanudar', 'cancelar', 'luz', 'velocidad')",
                           name="ck_impresora_comandos_comando_valido"),
        sa.CheckConstraint("estado IN ('pendiente', 'enviado', 'fallido', 'vencido')",
                           name="ck_impresora_comandos_estado_valido"),
    )  # fmt: skip
    crear_indice_si_no_existe("ix_impresora_comandos_creado_en", "impresora_comandos", ["creado_en"])


def downgrade() -> None:
    borrar_tabla_si_existe("impresora_comandos")
    borrar_tabla_si_existe("impresora_estado")
    borrar_tabla_si_existe("trabajos_impresora")
