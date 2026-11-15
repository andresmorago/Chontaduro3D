"""Diagnóstico del historial de Bambu Cloud: `make bambu-nube-prueba`.

Muestra la FORMA de lo que devuelve la nube (campos, estados, conteos), sin imprimir el token ni
datos personales, para poder ajustar el lector si Bambu cambia su API."""

import asyncio
from collections import Counter
from datetime import UTC, datetime, timedelta

from app.config import settings
from app.db import SessionLocal
from app.impresora import ajustes, nube


async def _cargar() -> tuple[nube.Sesion | None, str | None]:
    async with SessionLocal() as db:
        fila = await ajustes.obtener(db)
        return ajustes.sesion_de(fila), (fila.serial if fila else None)


def main() -> int:
    sesion, serial = asyncio.run(_cargar())
    if sesion is None:
        print("No hay cuenta vinculada: hazlo en Administración → Conexión.")
        return 1
    almacen = nube.AlmacenMemoria()
    almacen.poner(sesion)
    cliente = nube.ClienteNube(settings.bambu_nube_url, almacen)
    try:
        crudo = cliente._get("/v1/user-service/my/tasks", {"limit": 50})
    except nube.ErrorNube as e:
        print("Error:", e)
        return 1
    filas = crudo.get("hits") if isinstance(crudo, dict) else None
    print("claves de la respuesta:", sorted(crudo) if isinstance(crudo, dict) else type(crudo))
    print("tareas en la primera página:", len(filas or []))
    if filas:
        print("campos de una tarea:", sorted(filas[0]))
        print("valores de «status»:", dict(Counter(f.get("status") for f in filas)))
        print(
            "con costTime:", sum(1 for f in filas if f.get("costTime")),
            "| con weight:", sum(1 for f in filas if f.get("weight")),
            "| con amsDetailMapping:", sum(1 for f in filas if f.get("amsDetailMapping")),
        )  # fmt: skip
        print("ejemplo startTime/endTime:", filas[0].get("startTime"), "→", filas[0].get("endTime"))
    desde = datetime.now(UTC) - timedelta(days=settings.bambu_nube_dias)
    tareas = cliente.tareas(desde, serial)
    print(f"\nÚltimos {settings.bambu_nube_dias} días (esta impresora): {len(tareas)} trabajos")
    for t in tareas[:15]:
        print(
            f"  {t.inicio:%Y-%m-%d %H:%M} · {t.estado:11} · real {t.minutos_reales} min "
            f"(est. {t.minutos or '—'}) · "
            f"{t.gramos or '—'} g · {t.titulo[:40]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
