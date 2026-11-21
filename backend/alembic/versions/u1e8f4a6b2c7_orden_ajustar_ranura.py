"""órdenes de la impresora: poner color y material en una ranura del AMS

Revision ID: u1e8f4a6b2c7
Revises: t0d7e3f5a1b6
Create Date: 2026-11-21 08:30:00

Idempotente: la restricción se recrea con DROP … IF EXISTS y ensanchar la columna se puede repetir.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "u1e8f4a6b2c7"
down_revision: str | None = "t0d7e3f5a1b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ANTIGUOS = (
    "pausar", "reanudar", "cancelar", "luz", "velocidad",
    "temp_boquilla", "temp_cama", "ventilador_pieza", "ventilador_aux", "leer_rfid",
)  # fmt: skip
NUEVOS = (*ANTIGUOS, "ajustar_ranura")
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
    # «ranura:RRGGBB:MATERIAL» (p. ej. «2:7b2cbf:PLA») no cabe en 12 caracteres.
    op.alter_column("impresora_comandos", "valor", type_=sa.String(40), existing_nullable=True)
    _poner(NUEVOS)


def downgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("impresora_comandos"):
        return
    op.execute(f"DELETE FROM impresora_comandos WHERE comando NOT IN ({_lista(ANTIGUOS)})")
    _poner(ANTIGUOS)
    op.execute("UPDATE impresora_comandos SET valor = LEFT(valor, 12)")
    op.alter_column("impresora_comandos", "valor", type_=sa.String(12), existing_nullable=True)
