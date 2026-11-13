"""Verificación de Cloudflare Turnstile en el servidor.

El widget del navegador solo entrega un token; el que decide es este módulo, que lo valida contra
Cloudflare con la llave SECRETA. Un token sirve una sola vez y caduca a los 5 minutos (lo impone
Cloudflare). Si Turnstile está configurado y la verificación no se puede completar, se rechaza
(falla cerrado): es preferible pedir «inténtalo de nuevo» a dejar pasar a un robot.
"""

import httpx
from fastapi import HTTPException, status

from app.config import settings

MENSAJE = "No pudimos verificar que eres una persona. Recarga la página e inténtalo de nuevo."


async def _consultar(token: str, ip: str) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as cliente:
        r = await cliente.post(
            settings.turnstile_url,
            data={"secret": settings.turnstile_secretkey, "response": token, "remoteip": ip},
        )
        r.raise_for_status()
        return r.json()


async def exigir(token: str | None, ip: str) -> None:
    """No hace nada si Turnstile está apagado; si está activo, exige un token válido."""
    if not settings.turnstile_activo:
        return
    if not token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, MENSAJE)
    try:
        resultado = await _consultar(token, ip)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MENSAJE) from None
    if not resultado.get("success"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, MENSAJE)
