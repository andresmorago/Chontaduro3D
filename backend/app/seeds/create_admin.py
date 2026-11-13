"""Crea o actualiza el único usuario administrador (ADMIN_EMAIL / ADMIN_PASSWORD). Idempotente."""

import asyncio
import sys

from sqlalchemy import select, update

from app.config import settings
from app.core.security import hash_password, validar_fortaleza
from app.db import SessionLocal, engine
from app.models import SesionRefresh, Usuario


async def crear_o_actualizar(email: str, password: str) -> str:
    motivo = validar_fortaleza(password)
    if motivo:
        raise SystemExit(motivo)
    email = email.strip().lower()
    async with SessionLocal() as db:
        usuario = (
            await db.execute(select(Usuario).where(Usuario.email == email))
        ).scalar_one_or_none()
        if usuario is None:
            db.add(Usuario(email=email, password_hash=hash_password(password)))
            accion = "creado"
        else:
            usuario.password_hash = hash_password(password)
            usuario.activo = True
            # Recuperación tras una posible filtración: cerrar TODAS las sesiones (refresh) e
            # invalidar los JWT de acceso ya emitidos subiendo la versión.
            usuario.version_sesion += 1
            await db.execute(
                update(SesionRefresh)
                .where(SesionRefresh.usuario_id == usuario.id)
                .values(revocada=True)
            )
            accion = "actualizado"
        await db.commit()
    return accion


async def main() -> int:
    if not settings.admin_email or not settings.admin_password:
        print("Falta ADMIN_EMAIL o ADMIN_PASSWORD en el .env.", file=sys.stderr)
        return 1
    accion = await crear_o_actualizar(settings.admin_email, settings.admin_password)
    print(f"Administrador {accion}: {settings.admin_email.strip().lower()}")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
