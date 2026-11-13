import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import TIPOS_MOVIMIENTO, en_lista


class MovimientoInventario(Base):
    """Libro mayor del inventario. El stock de un artículo es la SUMA de sus
    movimientos: no hay un contador aparte que pueda desincronizarse."""

    __tablename__ = "movimientos_inventario"
    __table_args__ = (
        CheckConstraint(en_lista("tipo", TIPOS_MOVIMIENTO), name="tipo_valido"),
        CheckConstraint("cantidad <> 0", name="cantidad_no_cero"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    articulo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articulos.id"), index=True, nullable=False
    )
    tipo: Mapped[str] = mapped_column(String(12), nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)  # con signo
    produccion_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("producciones.id"), index=True
    )
    venta_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ventas.id"), index=True
    )
    nota: Mapped[str | None] = mapped_column(String(300))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
