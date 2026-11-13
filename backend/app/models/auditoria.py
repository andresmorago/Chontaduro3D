import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class RegistroAuditoria(Base):
    """Eventos que importan: ingresos (y fallos), cambios de precio, anulaciones.
    Los fallos de ingreso también sirven para limitar intentos entre procesos."""

    __tablename__ = "registro_auditoria"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    accion: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    detalle: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    origen_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
