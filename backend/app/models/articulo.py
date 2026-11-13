import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Sequence,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import MarcaDeTiempo, uuid_pk

# Secuencia del código legible: IMP-0001, IMP-0002…
secuencia_codigo = Sequence("articulos_codigo_seq", metadata=Base.metadata)


class Articulo(MarcaDeTiempo, Base):
    """Artículo maestro: lo que se imprime y se vende."""

    __tablename__ = "articulos"
    __table_args__ = (
        CheckConstraint("precio_venta >= 0", name="precio_no_negativo"),
        CheckConstraint("stock_minimo >= 0", name="stock_minimo_no_negativo"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    codigo: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        server_default=text("'IMP-' || lpad(nextval('articulos_codigo_seq')::text, 4, '0')"),
    )
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, server_default=text("''"), nullable=False)
    imagen: Mapped[str | None] = mapped_column(String(80))
    precio_venta: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    stock_minimo: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    publicado: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PrecioHistorial(Base):
    """Cada precio que ha tenido un artículo. El primero se registra al crearlo."""

    __tablename__ = "precio_historial"

    id: Mapped[uuid.UUID] = uuid_pk()
    articulo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articulos.id", ondelete="CASCADE"), index=True
    )
    precio: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cambiado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
