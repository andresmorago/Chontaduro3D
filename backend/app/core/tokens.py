"""Sesión: JWT de acceso (corto) + token de refresco opaco (solo su hash en la BD)."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.config import settings

ALGORITMO = "HS256"


def ahora() -> datetime:
    return datetime.now(UTC)


def crear_access_token(usuario_id: str, version: int = 0) -> str:
    emitido = ahora()
    payload = {
        "sub": str(usuario_id),
        "iat": emitido,
        "exp": emitido + timedelta(minutes=settings.access_token_minutes),
        "typ": "access",
        "ver": version,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITMO)


def leer_access_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITMO],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError:
        return None
    return payload if payload.get("typ") == "access" else None


def hash_token(crudo: str) -> str:
    return hashlib.sha256(crudo.encode()).hexdigest()


def generar_token_opaco() -> tuple[str, str]:
    """(token para la cookie, hash para la base)."""
    crudo = secrets.token_urlsafe(48)
    return crudo, hash_token(crudo)


def vencimiento_refresco() -> datetime:
    return ahora() + timedelta(days=settings.refresh_token_days)
