from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Numeric, SmallInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Parametros(Base):
    """Parámetros universales del negocio. Una sola fila (id = 1).

    - precio_kwh: lo que cuesta el kWh (COP) — base de las métricas de costo de energía.
    - potencia_impresora_w: consumo promedio de la impresora en vatios — junto con el tiempo de
      impresión da los kWh de cada lote."""

    __tablename__ = "parametros"
    __table_args__ = (
        CheckConstraint("id = 1", name="fila_unica"),
        CheckConstraint("precio_kwh >= 0", name="precio_kwh_no_negativo"),
        CheckConstraint("potencia_impresora_w > 0", name="potencia_positiva"),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1, server_default="1")
    precio_kwh: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    potencia_impresora_w: Mapped[Decimal | None] = mapped_column(Numeric(8, 1))
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
