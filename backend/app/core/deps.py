"""Dependencias de autenticación."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tokens import leer_access_token
from app.db import get_db
from app.models import Usuario

COOKIE_ACCESO = "mi_access"
COOKIE_REFRESCO = "mi_refresh"
METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}

DB = Annotated[AsyncSession, Depends(get_db)]


def exigir_cabecera_csrf(request: Request) -> None:
    """Las mutaciones deben traer una cabecera propia. Un formulario o una
    imagen de otro sitio no pueden ponerla sin permiso CORS (y aquí no hay),
    así que esto cierra CSRF aun si la cookie viajara."""
    if request.method not in METODOS_SEGUROS and request.headers.get("x-requested-with") != "fetch":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Petición no permitida desde este origen.")


async def usuario_actual(request: Request, db: DB) -> Usuario:
    no_autenticado = HTTPException(status.HTTP_401_UNAUTHORIZED, "Inicia sesión para continuar.")
    token = request.cookies.get(COOKIE_ACCESO)
    payload = leer_access_token(token) if token else None
    if payload is None:
        raise no_autenticado
    try:
        usuario = await db.get(Usuario, UUID(payload["sub"]))
    except (ValueError, KeyError):
        raise no_autenticado from None
    if usuario is None or not usuario.activo:
        raise no_autenticado
    return usuario


Admin = Annotated[Usuario, Depends(usuario_actual)]

# Todo router del panel se monta con esto: sesión válida + cabecera anti-CSRF en mutaciones.
PROTEGIDO = [Depends(usuario_actual), Depends(exigir_cabecera_csrf)]
