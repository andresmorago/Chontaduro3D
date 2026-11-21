"""Limpieza periódica de filas que ya no sirven: intentos de ingreso fallidos y sesiones viejas."""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import and_, delete, or_

from app.core.tokens import ahora
from app.db import SessionLocal
from app.models import RegistroAuditoria, SesionRefresh

log = logging.getLogger("limpieza")

CADA_S = 24 * 3600
DIAS_FALLOS = 90  # los `login_fallido` solo sirven para limitar intentos (ventana de minutos)
DIAS_SESIONES = 30  # sesiones caducadas o revocadas hace más de esto


async def purgar() -> dict[str, int]:
    """Borra `login_fallido` de más de 90 días y sesiones de refresco caducadas o revocadas hace
    más de 30. Devuelve cuántas filas quitó de cada tabla."""
    t = ahora()
    corte_sesiones = t - timedelta(days=DIAS_SESIONES)
    async with SessionLocal() as db:
        fallos = await db.execute(
            delete(RegistroAuditoria).where(
                RegistroAuditoria.accion == "login_fallido",
                RegistroAuditoria.creado_en < t - timedelta(days=DIAS_FALLOS),
            )
        )
        sesiones = await db.execute(
            delete(SesionRefresh).where(
                or_(
                    SesionRefresh.expira_en < corte_sesiones,
                    and_(SesionRefresh.revocada_en.is_not(None),
                         SesionRefresh.revocada_en < corte_sesiones),
                )
            )
        )
        await db.commit()
    return {"login_fallido": fallos.rowcount, "sesiones_refresh": sesiones.rowcount}


async def bucle_limpieza(cada_s: float = CADA_S) -> None:
    """Purga al iniciar y luego cada 24 h. Un fallo se registra y no detiene el bucle ni la app."""
    while True:
        try:
            quitadas = await purgar()
            if any(quitadas.values()):
                log.info("Limpieza periódica: %s", quitadas)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("Falló la limpieza periódica; se reintenta en el próximo ciclo.")
        await asyncio.sleep(cada_s)
