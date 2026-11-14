"""órdenes de la impresora: temperaturas y ventiladores

Revision ID: j0f7a3b5c1d6
Revises: i9e6f2a4b0c5
Create Date: 2026-11-14 23:00:00

Idempotente: la restricción se recrea con DROP … IF EXISTS.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "j0f7a3b5c1d6"
down_revision: str | None = "i9e6f2a4b0c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ANTIGUOS = ("pausar", "reanudar", "cancelar", "luz", "velocidad")
NUEVOS = ANTIGUOS + ("temp_boquilla", "temp_cama", "ventilador_pieza", "ventilador_aux")
RESTRICCION = "ck_impresora_comandos_comando_valido"


def _lista(valores: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in valores)


def _poner(valores: tuple[str, ...]) -> None:
    # El nombre real de la restricción depende de la convención de nombres con que se creó
    # (puede llevar el prefijo duplicado): se buscan las que miran la columna `comando`.
    for c in sa.inspect(op.get_bind()).get_check_constraints("impresora_comandos"):
        if "pausar" in (c.get("sqltext") or ""):
            op.execute(f'ALTER TABLE impresora_comandos DROP CONSTRAINT IF EXISTS "{c["name"]}"')
    op.execute(f"ALTER TABLE impresora_comandos DROP CONSTRAINT IF EXISTS {RESTRICCION}")
    op.execute(f"ALTER TABLE impresora_comandos ADD CONSTRAINT {RESTRICCION} "
               f"CHECK (comando IN ({_lista(valores)}))")  # fmt: skip


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("impresora_comandos"):
        return
    op.alter_column("impresora_comandos", "comando", type_=sa.String(20), existing_nullable=False)
    _poner(NUEVOS)


def downgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("impresora_comandos"):
        return
    op.execute(f"DELETE FROM impresora_comandos WHERE comando NOT IN ({_lista(ANTIGUOS)})")
    _poner(ANTIGUOS)
    op.alter_column("impresora_comandos", "comando", type_=sa.String(12), existing_nullable=False)
