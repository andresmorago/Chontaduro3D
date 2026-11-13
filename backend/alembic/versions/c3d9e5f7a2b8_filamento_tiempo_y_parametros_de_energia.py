"""filamento, tiempo de impresión y parámetros de energía en la producción

Revision ID: c3d9e5f7a2b8
Revises: b2c8d4e6f1a7
Create Date: 2026-11-13 16:00:00

- producciones: gramos_total, minutos_impresion y la energía congelada
  (potencia_w, precio_kwh, kwh, costo_energia).
- produccion_filamentos: gramos por filamento (opcional; si se usa, el total es su suma).
- parametros: fila única con el precio del kWh y la potencia de la impresora.

Idempotente: usa los ayudantes de app/idempotente.py y SQL con IF NOT EXISTS.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op
from app.idempotente import (
    agregar_columna_si_no_existe,
    borrar_columna_si_existe,
    borrar_tabla_si_existe,
    crear_indice_si_no_existe,
    crear_tabla_si_no_existe,
)

revision: str = "c3d9e5f7a2b8"
down_revision: str | None = "b2c8d4e6f1a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNAS = (
    sa.Column("gramos_total", sa.Numeric(10, 2)),
    sa.Column("minutos_impresion", sa.Integer),
    sa.Column("potencia_w", sa.Numeric(8, 1)),
    sa.Column("precio_kwh", sa.Numeric(12, 2)),
    sa.Column("kwh", sa.Numeric(10, 3)),
    sa.Column("costo_energia", sa.Numeric(14, 2)),
)


def _check(tabla: str, nombre: str, condicion: str) -> None:
    """ADD CONSTRAINT … CHECK solo si no existe (repetible)."""
    op.execute(
        f"""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{nombre}') THEN
            ALTER TABLE {tabla} ADD CONSTRAINT {nombre} CHECK ({condicion});
          END IF;
        END $$;
        """
    )


def upgrade() -> None:
    for c in COLUMNAS:
        agregar_columna_si_no_existe("producciones", c)
    _check("producciones", "ck_producciones_gramos_positivos", "gramos_total > 0")
    _check("producciones", "ck_producciones_minutos_positivos", "minutos_impresion > 0")

    crear_tabla_si_no_existe(
        "produccion_filamentos",
        sa.Column(
            "id",
            pg.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("produccion_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("orden", sa.SmallInteger, server_default=sa.text("0"), nullable=False),
        sa.Column("descripcion", sa.String(60), server_default=sa.text("''"), nullable=False),
        sa.Column("gramos", sa.Numeric(10, 2), nullable=False),
        sa.ForeignKeyConstraint(["produccion_id"], ["producciones.id"], ondelete="CASCADE"),
        sa.CheckConstraint("gramos > 0", name="gramos_positivos"),
    )
    crear_indice_si_no_existe(
        "ix_produccion_filamentos_produccion_id", "produccion_filamentos", ["produccion_id"]
    )

    crear_tabla_si_no_existe(
        "parametros",
        sa.Column("id", sa.SmallInteger, primary_key=True, server_default=sa.text("1")),
        sa.Column("precio_kwh", sa.Numeric(12, 2)),
        sa.Column("potencia_impresora_w", sa.Numeric(8, 1)),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="fila_unica"),
        sa.CheckConstraint("precio_kwh >= 0", name="precio_kwh_no_negativo"),
        sa.CheckConstraint("potencia_impresora_w > 0", name="potencia_positiva"),
    )
    op.execute("INSERT INTO parametros (id) VALUES (1) ON CONFLICT (id) DO NOTHING")


def downgrade() -> None:
    borrar_tabla_si_existe("parametros")
    borrar_tabla_si_existe("produccion_filamentos")
    op.execute(
        "ALTER TABLE producciones DROP CONSTRAINT IF EXISTS ck_producciones_minutos_positivos"
    )
    op.execute(
        "ALTER TABLE producciones DROP CONSTRAINT IF EXISTS ck_producciones_gramos_positivos"
    )
    for c in reversed(COLUMNAS):
        borrar_columna_si_existe("producciones", c.name)
