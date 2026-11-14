"""pedidos con varios artículos (mini carrito): renglones en pedido_items

Revision ID: l2b9c5d7e3f8
Revises: k1a8b4c6d2e7
Create Date: 2026-11-15 14:00:00

Idempotente. Los pedidos existentes (un artículo cada uno) se copian como un renglón; las columnas
antiguas de `pedidos` (articulo_id, cantidad, color) quedan como deprecadas y opcionales.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op
from app.idempotente import crear_indice_si_no_existe, crear_tabla_si_no_existe

revision: str = "l2b9c5d7e3f8"
down_revision: str | None = "k1a8b4c6d2e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    crear_tabla_si_no_existe(
        "pedido_items",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"),
                  primary_key=True),
        sa.Column("pedido_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("pedidos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("articulo_id", pg.UUID(as_uuid=True), sa.ForeignKey("articulos.id"),
                  nullable=False),
        sa.Column("color", sa.String(30)),
        sa.Column("cantidad", sa.Integer, nullable=False),
        sa.CheckConstraint("cantidad > 0", name="ck_pedido_items_cantidad_positiva"),
    )  # fmt: skip
    crear_indice_si_no_existe("ix_pedido_items_pedido_id", "pedido_items", ["pedido_id"])
    crear_indice_si_no_existe("ix_pedido_items_articulo_id", "pedido_items", ["articulo_id"])
    # Cada pedido anterior pasa a tener su renglón (solo si aún no lo tiene: se puede repetir).
    op.execute(
        "INSERT INTO pedido_items (pedido_id, articulo_id, color, cantidad) "
        "SELECT p.id, p.articulo_id, p.color, p.cantidad FROM pedidos p "
        "WHERE p.articulo_id IS NOT NULL AND p.cantidad IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM pedido_items i WHERE i.pedido_id = p.id)"
    )
    op.execute("ALTER TABLE pedidos ALTER COLUMN articulo_id DROP NOT NULL")
    op.execute("ALTER TABLE pedidos ALTER COLUMN cantidad DROP NOT NULL")


def downgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("pedido_items"):
        return
    # El formato anterior guarda UN artículo por pedido: se conserva el primer renglón de cada uno
    # (los demás renglones de un pedido de varios artículos se pierden al volver atrás).
    op.execute(
        "UPDATE pedidos p SET articulo_id = i.articulo_id, cantidad = i.cantidad, color = i.color "
        "FROM (SELECT DISTINCT ON (pedido_id) pedido_id, articulo_id, cantidad, color "
        "      FROM pedido_items ORDER BY pedido_id, id) i "
        "WHERE i.pedido_id = p.id AND p.articulo_id IS NULL"
    )
    op.execute("ALTER TABLE pedidos ALTER COLUMN articulo_id SET NOT NULL")
    op.execute("ALTER TABLE pedidos ALTER COLUMN cantidad SET NOT NULL")
    op.drop_table("pedido_items")
