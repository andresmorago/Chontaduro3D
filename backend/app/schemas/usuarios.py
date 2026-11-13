from datetime import datetime
from uuid import UUID

from pydantic import EmailStr, Field

from app.schemas.comunes import Entrada, Salida


class UsuarioNuevo(Entrada):
    nombre: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UsuarioCambios(Entrada):
    nombre: str | None = Field(default=None, min_length=1, max_length=80)
    activo: bool | None = None


class CambiarContrasena(Entrada):
    actual: str = Field(min_length=1, max_length=200)
    nueva: str = Field(min_length=1, max_length=200)


class RestablecerContrasena(Entrada):
    nueva: str = Field(min_length=1, max_length=200)


class UsuarioAdminOut(Salida):
    id: UUID
    email: str
    nombre: str | None
    activo: bool
    creado_en: datetime
    es_yo: bool
