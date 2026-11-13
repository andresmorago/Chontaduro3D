import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, Numeric, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import MarcaDeTiempo, uuid_pk


class Produccion(MarcaDeTiempo, Base):
    """Un lote de impresión terminado: lo que sale de la impresora entra al stock."""

    __tablename__ = "producciones"
    __table_args__ = (
        CheckConstraint("gramos_total > 0", name="gramos_positivos"),
        CheckConstraint("minutos_impresion > 0", name="minutos_positivos"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    fecha: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    nota: Mapped[str | None] = mapped_column(String(300))
    # Filamento y tiempo del lote (opcionales). Los gramos son el TOTAL: se escribe directo o es la
    # suma de `produccion_filamentos` (por filamento).
    gramos_total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    minutos_impresion: Mapped[int | None] = mapped_column(Integer)
    # Energía: se CONGELA al registrar (potencia y precio del kWh de ese día), como el precio
    # de una venta: cambiar los parámetros después no reescribe el pasado.
    potencia_w: Mapped[Decimal | None] = mapped_column(Numeric(8, 1))
    precio_kwh: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    kwh: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    costo_energia: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))


class ProduccionItem(Base):
    __tablename__ = "produccion_items"
    __table_args__ = (CheckConstraint("cantidad > 0", name="cantidad_positiva"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    produccion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("producciones.id", ondelete="CASCADE"), index=True
    )
    articulo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articulos.id"), index=True
    )
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)


class ProduccionFilamento(Base):
    """Gramos de un filamento concreto usado en el lote (p. ej. «PLA negro» 120 g)."""

    __tablename__ = "produccion_filamentos"
    __table_args__ = (CheckConstraint("gramos > 0", name="gramos_positivos"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    produccion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("producciones.id", ondelete="CASCADE"), index=True
    )
    orden: Mapped[int] = mapped_column(SmallInteger, server_default="0", nullable=False)
    descripcion: Mapped[str] = mapped_column(String(60), server_default="", nullable=False)
    gramos: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
