import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import MarcaDeTiempo, uuid_pk
from app.models.enums import ESTADOS_PEDIDO, en_lista


class Pedido(MarcaDeTiempo, Base):
    """Solicitud de un cliente desde el catálogo público.
    NO es una venta y NO mueve el inventario."""

    __tablename__ = "pedidos"
    __table_args__ = (
        Index("ix_pedidos_creado_en", "creado_en"),
        CheckConstraint(en_lista("estado", ESTADOS_PEDIDO), name="estado_valido"),
        CheckConstraint("cantidad > 0", name="cantidad_positiva"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    articulo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articulos.id"), index=True
    )
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    whatsapp: Mapped[str] = mapped_column(String(20), nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(String(12), server_default=text("'nuevo'"), nullable=False)
    nota: Mapped[str | None] = mapped_column(String(300))
    # Hash del origen, para limitar abuso sin guardar la IP en claro.
    origen_hash: Mapped[str | None] = mapped_column(String(64), index=True)
