import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import MarcaDeTiempo, uuid_pk
from app.models.enums import METODOS_PAGO, en_lista


class Venta(MarcaDeTiempo, Base):
    __tablename__ = "ventas"
    __table_args__ = (
        CheckConstraint(en_lista("metodo_pago", METODOS_PAGO), name="metodo_valido"),
        CheckConstraint("total >= 0", name="total_no_negativo"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    fecha: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    cliente: Mapped[str | None] = mapped_column(String(120))
    metodo_pago: Mapped[str] = mapped_column(String(15), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    nota: Mapped[str | None] = mapped_column(String(300))
    anulada: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)
    anulada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Pedido del catálogo que esta venta atiende (opcional). Un pedido puede tener varias ventas
    # (entregas parciales). Asociarla NO cambia el inventario: eso lo hace la venta como siempre.
    pedido_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pedidos.id", ondelete="SET NULL"), index=True
    )


class VentaItem(Base):
    __tablename__ = "venta_items"
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="cantidad_positiva"),
        CheckConstraint("precio_unitario >= 0", name="precio_no_negativo"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    venta_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ventas.id", ondelete="CASCADE"), index=True
    )
    articulo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articulos.id"), index=True
    )
    color_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articulo_colores.id", ondelete="SET NULL"), index=True
    )
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    # Precio congelado al vender: cambiar el precio maestro no reescribe el pasado.
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
