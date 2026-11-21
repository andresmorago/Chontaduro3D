"""Cliente de Spoolman para el backend web (una instancia por petición)."""

from collections.abc import AsyncIterator

from fastapi import HTTPException, status

from app.config import settings
from app.spoolman.cliente import ClienteSpoolman


async def cliente_spoolman() -> AsyncIterator[ClienteSpoolman]:
    if not settings.spoolman_url:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Spoolman no está configurado en este servidor."
        )
    try:
        c = ClienteSpoolman(settings.spoolman_url)
    except ValueError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "La dirección de Spoolman (SPOOLMAN_URL) no es válida."
        ) from None
    try:
        yield c
    finally:
        await c.cerrar()


async def cliente_spoolman_opcional() -> AsyncIterator[ClienteSpoolman | None]:
    """Como `cliente_spoolman`, pero sin Spoolman da None (para lo que sirve con o sin él)."""
    if not settings.spoolman_url:
        yield None
        return
    try:
        c = ClienteSpoolman(settings.spoolman_url)
    except ValueError:
        yield None
        return
    try:
        yield c
    finally:
        await c.cerrar()
