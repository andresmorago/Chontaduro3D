"""Diagnóstico del historial de Bambu Cloud: `make bambu-nube-prueba`.

Muestra la FORMA de lo que devuelve la nube (campos, estados, conteos), sin imprimir el token ni
datos personales, para poder ajustar el lector si Bambu cambia su API."""

from collections import Counter
from datetime import UTC, datetime, timedelta

from app.config import settings
from app.impresora import nube


def main() -> int:
    almacen = nube.AlmacenToken(settings.bambu_nube_archivo)
    if not almacen.existe():
        print("No hay token: corre primero `make bambu-login`.")
        return 1
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
    tareas = cliente.tareas(desde, settings.bambu_serial or None)
    print(f"\nÚltimos {settings.bambu_nube_dias} días (esta impresora): {len(tareas)} trabajos")
    for t in tareas[:15]:
        print(
            f"  {t.inicio:%Y-%m-%d %H:%M} · {t.estado:11} · {t.minutos or '—'} min · "
            f"{t.gramos or '—'} g · {t.titulo[:40]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
