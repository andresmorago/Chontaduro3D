import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import MarcaDeTiempo, uuid_pk


class Produccion(MarcaDeTiempo, Base):
    """Un lote de impresión terminado: lo que sale de la impresora entra al stock."""

    __tablename__ = "producciones"

    id: Mapped[uuid.UUID] = uuid_pk()
    fecha: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    nota: Mapped[str | None] = mapped_column(String(300))


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
