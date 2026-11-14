"""encuadre de la foto del artículo y foto opcional por color

Revision ID: i9e6f2a4b0c5
Revises: h8d5e1f3a9b4
Create Date: 2026-11-14 20:00:00

Idempotente: usa los ayudantes de app/idempotente.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.idempotente import agregar_columna_si_no_existe, borrar_columna_si_existe

revision: str = "i9e6f2a4b0c5"
down_revision: str | None = "h8d5e1f3a9b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENCUADRE = (("foto_x", "50"), ("foto_y", "50"), ("foto_zoom", "1"))


def _restricciones(tabla: str) -> None:
    # CHECK solo si faltan (la migración puede repetirse sobre un esquema parcial).
    existentes = {c["name"] for c in sa.inspect(op.get_bind()).get_check_constraints(tabla)}
    for nombre, regla in (
        (f"ck_{tabla}_foto_x_valida", "foto_x BETWEEN 0 AND 100"),
        (f"ck_{tabla}_foto_y_valida", "foto_y BETWEEN 0 AND 100"),
        (f"ck_{tabla}_foto_zoom_valido", "foto_zoom BETWEEN 1 AND 4"),
    ):
        if nombre not in existentes:
            op.create_check_constraint(nombre, tabla, regla)


def upgrade() -> None:
    for tabla in ("articulos", "articulo_colores"):
        for col, defecto in ENCUADRE:
            agregar_columna_si_no_existe(
                tabla, sa.Column(col, sa.Float, server_default=sa.text(defecto), nullable=False)
            )
        _restricciones(tabla)
    agregar_columna_si_no_existe("articulo_colores", sa.Column("imagen", sa.String(80)))


def downgrade() -> None:
    # Quitar las columnas arrastra sus CHECK.
    borrar_columna_si_existe("articulo_colores", "imagen")
    for tabla in ("articulo_colores", "articulos"):
        for col, _ in ENCUADRE:
            borrar_columna_si_existe(tabla, col)
