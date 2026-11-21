"""órdenes de la impresora: releer el chip RFID de una ranura

Revision ID: s9c6d2e4f0a5
Revises: r8b5c1d3e9f4
Create Date: 2026-11-21 05:00:00

Idempotente: la restricción se recrea con DROP … IF EXISTS.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "s9c6d2e4f0a5"
down_revision: str | None = "r8b5c1d3e9f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ANTIGUOS = (
    "pausar", "reanudar", "cancelar", "luz", "velocidad",
    "temp_boquilla", "temp_cama", "ventilador_pieza", "ventilador_aux",
)  # fmt: skip
NUEVOS = (*ANTIGUOS, "leer_rfid")
RESTRICCION = "ck_impresora_comandos_comando_valido"


def _lista(valores: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in valores)


def _poner(valores: tuple[str, ...]) -> None:
    # El nombre real de la restricción depende de la convención con que se creó: se buscan las que
    # miran la columna `comando` (las que nombran «pausar»).
    for c in sa.inspect(op.get_bind()).get_check_constraints("impresora_comandos"):
        if "pausar" in (c.get("sqltext") or ""):
            op.execute(f'ALTER TABLE impresora_comandos DROP CONSTRAINT IF EXISTS "{c["name"]}"')
    op.execute(f"ALTER TABLE impresora_comandos DROP CONSTRAINT IF EXISTS {RESTRICCION}")
    op.execute(f"ALTER TABLE impresora_comandos ADD CONSTRAINT {RESTRICCION} "
               f"CHECK (comando IN ({_lista(valores)}))")  # fmt: skip


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("impresora_comandos"):
        return
    _poner(NUEVOS)


def downgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("impresora_comandos"):
        return
    op.execute(f"DELETE FROM impresora_comandos WHERE comando NOT IN ({_lista(ANTIGUOS)})")
    _poner(ANTIGUOS)
