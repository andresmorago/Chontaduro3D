"""Carga artículos de EJEMPLO para probar la interfaz. Idempotente (por nombre).
Todos llevan «(ejemplo)» en el nombre: no son datos reales del negocio."""

import asyncio
import sys
from decimal import Decimal

from sqlalchemy import select

from app.db import SessionLocal, engine
from app.models import Articulo, MovimientoInventario, PrecioHistorial

EJEMPLOS = [
    ("Llavero con inicial (ejemplo)", "Llavero impreso en PLA, una letra a elección.", 6000, 5, 12),
    ("Maceta pequeña (ejemplo)", "Maceta de 8 cm con plato, PLA mate.", 18000, 3, 6),
    ("Soporte de celular (ejemplo)", "Soporte plegable para escritorio.", 22000, 2, 0),
]


async def main() -> int:
    async with SessionLocal() as db:
        for nombre, descripcion, precio, minimo, inicial in EJEMPLOS:
            existe = (
                await db.execute(select(Articulo).where(Articulo.nombre == nombre))
            ).scalar_one_or_none()
            if existe:
                continue
            a = Articulo(
                nombre=nombre,
                descripcion=descripcion,
                precio_venta=Decimal(precio),
                stock_minimo=minimo,
            )
            db.add(a)
            await db.flush()
            await db.refresh(a)
            db.add(PrecioHistorial(articulo_id=a.id, precio=a.precio_venta))
            if inicial:
                db.add(
                    MovimientoInventario(
                        articulo_id=a.id,
                        tipo="ajuste",
                        cantidad=inicial,
                        nota="Stock inicial de ejemplo",
                    )
                )
        await db.commit()
    await engine.dispose()
    print("Artículos de ejemplo listos.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
