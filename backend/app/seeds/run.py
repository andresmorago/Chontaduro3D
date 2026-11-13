"""Siembra lo mínimo e idempotente. Hoy no hay catálogos fijos que sembrar: el
negocio carga sus propios artículos. Se deja como punto de extensión y para que
`make bootstrap` tenga un paso uniforme."""

import asyncio
import sys

from sqlalchemy import text

from app.db import engine


async def main() -> int:
    async with engine.connect() as conexion:
        await conexion.execute(text("SELECT 1"))
    await engine.dispose()
    print("Nada que sembrar: la base está lista.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
