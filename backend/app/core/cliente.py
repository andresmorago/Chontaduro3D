"""Origen de la petición, para limitar abuso sin guardar IPs en claro."""

import hashlib
import hmac
import ipaddress

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


def _agrupar(ip: str) -> str:
    """Una dirección IPv6 completa da 2^64 «orígenes» a quien tenga un /64: se agrupa por /64."""
    try:
        d = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if d.version == 6:
        return str(ipaddress.ip_network(f"{d}/64", strict=False))
    return ip


def origen_hash(request: Request) -> str:
    """HMAC del origen (IPv4 tal cual, IPv6 por /64): sirve para contar, no para identificar."""
    clave = settings.secret_key.encode()
    return hmac.new(clave, _agrupar(ip_cliente(request)).encode(), hashlib.sha256).hexdigest()
