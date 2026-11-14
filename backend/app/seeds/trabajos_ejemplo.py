"""Deja dos trabajos de la impresora de EJEMPLO («E2E trabajo A/B») por revisar, para la prueba
de navegador (`make e2e`). Idempotente: solo agrega el que no esté ya pendiente.
No usar en producción."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.db import SessionLocal, engine
from app.models import TrabajoImpresora

EJEMPLOS = [
    ("E2E trabajo A", 125, Decimal("42.50"), [
        {"tipo": "PLA", "color": "#ff0000", "gramos": 30.0},
        {"tipo": "PLA", "color": "#ffffff", "gramos": 12.5},
    ]),
    ("E2E trabajo B", 40, Decimal("9.00"), [{"tipo": "PLA", "color": "#00aa00", "gramos": 9.0}]),
]  # fmt: skip


async def main() -> None:
    async with SessionLocal() as db:
        for nombre, minutos, gramos, filamentos in EJEMPLOS:
            hay = (
                await db.execute(
                    select(TrabajoImpresora.id).where(
                        TrabajoImpresora.nombre == nombre, TrabajoImpresora.gestion == "pendiente"
                    )
                )
            ).first()
            if hay:
                continue
            fin = datetime.now(UTC) - timedelta(minutes=30)
            db.add(
                TrabajoImpresora(
                    nombre=nombre,
                    tarea_id="e2e",
                    estado="terminado",
                    progreso=100,
                    inicio_en=fin - timedelta(minutes=minutos),
                    fin_en=fin,
                    inicio_observado=False,
                    minutos_estimados=minutos,
                    gramos_total=gramos,
                    filamentos=filamentos,
                )  # fmt: skip
            )
        await db.commit()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
