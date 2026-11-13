from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RegistroAuditoria


def registrar(
    db: AsyncSession,
    accion: str,
    *,
    usuario_id: UUID | None = None,
    detalle: dict[str, Any] | None = None,
    origen_hash: str | None = None,
) -> None:
    db.add(
        RegistroAuditoria(
            accion=accion, usuario_id=usuario_id, detalle=detalle, origen_hash=origen_hash
        )
    )
