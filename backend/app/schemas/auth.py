from uuid import UUID

from pydantic import EmailStr, Field

from app.schemas.comunes import Entrada, Salida


class LoginIn(Entrada):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UsuarioOut(Salida):
    id: UUID
    email: str
