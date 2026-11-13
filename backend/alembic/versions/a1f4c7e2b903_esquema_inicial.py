"""esquema inicial: usuarios, artículos, inventario, producción, ventas y pedidos

Revision ID: a1f4c7e2b903
Revises:
Create Date: 2026-11-13 12:00:00

Idempotente: usa los ayudantes de app/idempotente.py para poder repetirse
sobre un esquema parcial sin error.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op
from app.idempotente import (
    borrar_tabla_si_existe,
    crear_indice_si_no_existe,
    crear_tabla_si_no_existe,
)

revision: str = "a1f4c7e2b903"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )


def _creado_en() -> sa.Column:
    return sa.Column(
        "creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS articulos_codigo_seq")

    crear_tabla_si_no_existe(
        "usuarios",
        _uuid_pk(),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("activo", sa.Boolean, server_default=sa.text("true"), nullable=False),
        _creado_en(),
        sa.UniqueConstraint("email"),
    )

    crear_tabla_si_no_existe(
        "sesiones_refresh",
        _uuid_pk(),
        sa.Column("usuario_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revocada", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("user_agent", sa.String(255)),
        _creado_en(),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash"),
    )
    crear_indice_si_no_existe("ix_sesiones_refresh_usuario_id", "sesiones_refresh", ["usuario_id"])

    crear_tabla_si_no_existe(
        "articulos",
        _uuid_pk(),
        sa.Column(
            "codigo",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'IMP-' || lpad(nextval('articulos_codigo_seq')::text, 4, '0')"),
        ),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("descripcion", sa.Text, server_default=sa.text("''"), nullable=False),
        sa.Column("imagen", sa.String(80)),
        sa.Column("precio_venta", sa.Numeric(12, 2), nullable=False),
        sa.Column("stock_minimo", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("publicado", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("activo", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        _creado_en(),
        sa.CheckConstraint("precio_venta >= 0", name="precio_no_negativo"),
        sa.CheckConstraint("stock_minimo >= 0", name="stock_minimo_no_negativo"),
        sa.UniqueConstraint("codigo"),
    )

    crear_tabla_si_no_existe(
        "precio_historial",
        _uuid_pk(),
        sa.Column("articulo_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("precio", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "cambiado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["articulo_id"], ["articulos.id"], ondelete="CASCADE"),
    )
    crear_indice_si_no_existe(
        "ix_precio_historial_articulo_id", "precio_historial", ["articulo_id"]
    )

    crear_tabla_si_no_existe(
        "producciones",
        _uuid_pk(),
        sa.Column("fecha", sa.Date, nullable=False),
        sa.Column("nota", sa.String(300)),
        _creado_en(),
    )
    crear_indice_si_no_existe("ix_producciones_fecha", "producciones", ["fecha"])

    crear_tabla_si_no_existe(
        "ventas",
        _uuid_pk(),
        sa.Column("fecha", sa.Date, nullable=False),
        sa.Column("cliente", sa.String(120)),
        sa.Column("metodo_pago", sa.String(15), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("nota", sa.String(300)),
        sa.Column("anulada", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("anulada_en", sa.DateTime(timezone=True)),
        _creado_en(),
        sa.CheckConstraint(
            "metodo_pago IN ('efectivo', 'transferencia', 'otro')", name="metodo_valido"
        ),
        sa.CheckConstraint("total >= 0", name="total_no_negativo"),
    )
    crear_indice_si_no_existe("ix_ventas_fecha", "ventas", ["fecha"])

    crear_tabla_si_no_existe(
        "produccion_items",
        _uuid_pk(),
        sa.Column("produccion_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("articulo_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("cantidad", sa.Integer, nullable=False),
        sa.ForeignKeyConstraint(["produccion_id"], ["producciones.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["articulo_id"], ["articulos.id"]),
        sa.CheckConstraint("cantidad > 0", name="cantidad_positiva"),
    )
    crear_indice_si_no_existe(
        "ix_produccion_items_produccion_id", "produccion_items", ["produccion_id"]
    )
    crear_indice_si_no_existe(
        "ix_produccion_items_articulo_id", "produccion_items", ["articulo_id"]
    )

    crear_tabla_si_no_existe(
        "venta_items",
        _uuid_pk(),
        sa.Column("venta_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("articulo_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("cantidad", sa.Integer, nullable=False),
        sa.Column("precio_unitario", sa.Numeric(12, 2), nullable=False),
        sa.ForeignKeyConstraint(["venta_id"], ["ventas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["articulo_id"], ["articulos.id"]),
        sa.CheckConstraint("cantidad > 0", name="cantidad_positiva"),
        sa.CheckConstraint("precio_unitario >= 0", name="precio_no_negativo"),
    )
    crear_indice_si_no_existe("ix_venta_items_venta_id", "venta_items", ["venta_id"])
    crear_indice_si_no_existe("ix_venta_items_articulo_id", "venta_items", ["articulo_id"])

    crear_tabla_si_no_existe(
        "movimientos_inventario",
        sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
        sa.Column("articulo_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("tipo", sa.String(12), nullable=False),
        sa.Column("cantidad", sa.Integer, nullable=False),
        sa.Column("produccion_id", pg.UUID(as_uuid=True)),
        sa.Column("venta_id", pg.UUID(as_uuid=True)),
        sa.Column("nota", sa.String(300)),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["articulo_id"], ["articulos.id"]),
        sa.ForeignKeyConstraint(["produccion_id"], ["producciones.id"]),
        sa.ForeignKeyConstraint(["venta_id"], ["ventas.id"]),
        sa.CheckConstraint(
            "tipo IN ('produccion', 'venta', 'ajuste', 'anulacion')", name="tipo_valido"
        ),
        sa.CheckConstraint("cantidad <> 0", name="cantidad_no_cero"),
    )
    for col in ("articulo_id", "produccion_id", "venta_id", "creado_en"):
        crear_indice_si_no_existe(
            f"ix_movimientos_inventario_{col}", "movimientos_inventario", [col]
        )

    crear_tabla_si_no_existe(
        "pedidos",
        _uuid_pk(),
        sa.Column("articulo_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("whatsapp", sa.String(20), nullable=False),
        sa.Column("cantidad", sa.Integer, nullable=False),
        sa.Column("estado", sa.String(12), server_default=sa.text("'nuevo'"), nullable=False),
        sa.Column("nota", sa.String(300)),
        sa.Column("origen_hash", sa.String(64)),
        _creado_en(),
        sa.ForeignKeyConstraint(["articulo_id"], ["articulos.id"]),
        sa.CheckConstraint(
            "estado IN ('nuevo', 'contactado', 'cerrado', 'descartado')", name="estado_valido"
        ),
        sa.CheckConstraint("cantidad > 0", name="cantidad_positiva"),
    )
    crear_indice_si_no_existe("ix_pedidos_articulo_id", "pedidos", ["articulo_id"])
    crear_indice_si_no_existe("ix_pedidos_origen_hash", "pedidos", ["origen_hash"])

    crear_tabla_si_no_existe(
        "registro_auditoria",
        sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
        sa.Column("usuario_id", pg.UUID(as_uuid=True)),
        sa.Column("accion", sa.String(40), nullable=False),
        sa.Column("detalle", pg.JSONB),
        sa.Column("origen_hash", sa.String(64)),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="SET NULL"),
    )
    for col in ("accion", "origen_hash", "creado_en"):
        crear_indice_si_no_existe(f"ix_registro_auditoria_{col}", "registro_auditoria", [col])

    # Stock = suma de movimientos. CREATE OR REPLACE: repetible.
    op.execute(
        """
        CREATE OR REPLACE VIEW v_stock AS
        SELECT a.id AS articulo_id, COALESCE(SUM(m.cantidad), 0)::int AS stock
        FROM articulos a
        LEFT JOIN movimientos_inventario m ON m.articulo_id = a.id
        GROUP BY a.id
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_stock")
    for tabla in (
        "registro_auditoria",
        "pedidos",
        "movimientos_inventario",
        "venta_items",
        "produccion_items",
        "ventas",
        "producciones",
        "precio_historial",
        "articulos",
        "sesiones_refresh",
        "usuarios",
    ):
        borrar_tabla_si_existe(tabla)
    op.execute("DROP SEQUENCE IF EXISTS articulos_codigo_seq")
