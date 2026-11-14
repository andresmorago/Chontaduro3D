"""historial de Bambu Cloud: origen y tiempo medido de los trabajos, y estado de la sincronización

Revision ID: h8d5e1f3a9b4
Revises: g7b3c9d1e6f2
Create Date: 2026-11-14 18:00:00

Idempotente: usa los ayudantes de app/idempotente.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.idempotente import (
    agregar_columna_si_no_existe,
    borrar_columna_si_existe,
    indice_existe,
)

revision: str = "h8d5e1f3a9b4"
down_revision: str | None = "g7b3c9d1e6f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    agregar_columna_si_no_existe(
        "trabajos_impresora",
        sa.Column("origen", sa.String(10), server_default="impresora", nullable=False),
    )
    agregar_columna_si_no_existe("trabajos_impresora", sa.Column("nube_id", sa.String(40)))
    agregar_columna_si_no_existe("trabajos_impresora", sa.Column("minutos_medidos", sa.Integer))
    if not indice_existe("trabajos_impresora", "uq_trabajos_impresora_nube_id"):
        op.create_index(
            "uq_trabajos_impresora_nube_id", "trabajos_impresora", ["nube_id"], unique=True,
            postgresql_where=sa.text("nube_id IS NOT NULL"),
        )  # fmt: skip
    agregar_columna_si_no_existe("impresora_estado", sa.Column("nube_estado", sa.String(20)))
    agregar_columna_si_no_existe(
        "impresora_estado", sa.Column("nube_sincronizada_en", sa.DateTime(timezone=True))
    )
    agregar_columna_si_no_existe("impresora_estado", sa.Column("nube_detalle", sa.String(200)))


def downgrade() -> None:
    for col in ("nube_detalle", "nube_sincronizada_en", "nube_estado"):
        borrar_columna_si_existe("impresora_estado", col)
    if indice_existe("trabajos_impresora", "uq_trabajos_impresora_nube_id"):
        op.drop_index("uq_trabajos_impresora_nube_id", table_name="trabajos_impresora")
    for col in ("minutos_medidos", "nube_id", "origen"):
        borrar_columna_si_existe("trabajos_impresora", col)
