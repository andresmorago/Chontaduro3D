import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import MarcaDeTiempo, uuid_pk


class Usuario(MarcaDeTiempo, Base):
    __tablename__ = "usuarios"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)


class SesionRefresh(MarcaDeTiempo, Base):
    """Token de refresco: solo se guarda su hash."""

    __tablename__ = "sesiones_refresh"

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revocada: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(255))
