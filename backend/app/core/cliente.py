"""Origen de la petición, para limitar abuso sin guardar IPs en claro."""

import hashlib
import hmac

from fastapi import Request

from app.config import settings


def ip_cliente(request: Request) -> str:
    """IP real del visitante.

    Detrás del Worker de Cloudflare la conexión llega desde el túnel; la IP real
    viene en X-Real-Client-IP, y solo se acepta si la petición trae el secreto
    compartido (x-proxy-secret). Sin eso, cualquiera podría falsear su origen.
    """
    if settings.trust_proxy and settings.proxy_shared_secret:
        enviado = request.headers.get("x-proxy-secret", "")
        if hmac.compare_digest(enviado, settings.proxy_shared_secret):
            real = request.headers.get("x-real-client-ip", "").strip()
            if real:
                return real[:64]
    return request.client.host if request.client else "desconocido"


def origen_hash(request: Request) -> str:
    """HMAC de la IP con la clave de la app: sirve para contar, no para identificar."""
    clave = settings.secret_key.encode()
    return hmac.new(clave, ip_cliente(request).encode(), hashlib.sha256).hexdigest()
