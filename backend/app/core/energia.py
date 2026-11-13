"""Energía de un lote: kWh = potencia (kW) × horas; costo = kWh × precio del kWh."""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Parametros


async def parametros(db: AsyncSession) -> Parametros:
    """La fila única de parámetros (se crea vacía si faltara)."""
    fila = await db.get(Parametros, 1)
    if fila is None:
        fila = Parametros(id=1)
        db.add(fila)
        await db.flush()
    return fila


def calcular(
    minutos: int | None, potencia_w: Decimal | None, precio_kwh: Decimal | None
) -> tuple[Decimal | None, Decimal | None]:
    """(kWh, costo). kWh necesita tiempo y potencia; el costo, además, el precio del kWh."""
    if not minutos or potencia_w is None:
        return None, None
    kwh = (potencia_w / Decimal(1000) * Decimal(minutos) / Decimal(60)).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )
    if precio_kwh is None:
        return kwh, None
    return kwh, (kwh * precio_kwh).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
