"""Calendario de ventas: resumen por día y listado de un día elegido."""

from datetime import timedelta

from app.api.produccion import hoy
from tests.conftest import crear_articulo, producir


async def vender(admin, articulo, *, cantidad=1, dias_atras=0, **extra):
    cuerpo = {"items": [{"articulo_id": articulo["id"], "cantidad": cantidad}], **extra}
    if dias_atras:
        cuerpo["fecha"] = (hoy() - timedelta(days=dias_atras)).isoformat()
    r = await admin.post("/api/ventas", json=cuerpo)
    assert r.status_code == 201, r.text
    return r.json()


async def resumen(admin, desde, hasta):
    r = await admin.get(
        "/api/ventas/resumen", params={"desde": desde.isoformat(), "hasta": hasta.isoformat()}
    )
    assert r.status_code == 200, r.text
    return {d["fecha"]: (d["ventas"], d["total"]) for d in r.json()}


async def test_el_resumen_agrupa_por_dia_y_no_cuenta_las_anuladas(admin):
    a = await crear_articulo(admin, nombre="Llavero", precio=6000)
    await producir(admin, a["id"], 20)
    await vender(admin, a, cantidad=2)  # hoy: 12.000
    anulada = await vender(admin, a, cantidad=1)  # hoy, pero se anula
    await vender(admin, a, cantidad=3, dias_atras=2)  # hace 2 días: 18.000
    await vender(admin, a, cantidad=1, dias_atras=2)  # y otra: 6.000
    assert (await admin.post(f"/api/ventas/{anulada['id']}/anular")).status_code == 200
    h = hoy()
    r = await resumen(admin, h - timedelta(days=10), h)
    assert r == {
        h.isoformat(): (1, 12000),
        (h - timedelta(days=2)).isoformat(): (2, 24000),
    }  # los días sin ventas no aparecen


async def test_el_resumen_respeta_el_rango(admin):
    a = await crear_articulo(admin, nombre="Llavero", precio=6000)
    await producir(admin, a["id"], 5)
    await vender(admin, a, dias_atras=5)
    h = hoy()
    assert await resumen(admin, h - timedelta(days=3), h) == {}
    assert len(await resumen(admin, h - timedelta(days=5), h - timedelta(days=5))) == 1


async def test_rango_invalido_o_demasiado_largo(admin):
    h = hoy()
    r = await admin.get(
        "/api/ventas/resumen",
        params={"desde": h.isoformat(), "hasta": (h - timedelta(days=1)).isoformat()},
    )
    assert r.status_code == 422
    r = await admin.get(
        "/api/ventas/resumen",
        params={"desde": (h - timedelta(days=500)).isoformat(), "hasta": h.isoformat()},
    )
    assert r.status_code == 422
    assert (await admin.get("/api/ventas/resumen")).status_code == 422  # faltan las fechas


async def test_listar_un_dia_trae_solo_las_de_ese_dia(admin):
    a = await crear_articulo(admin, nombre="Llavero", precio=6000)
    await producir(admin, a["id"], 10)
    await vender(admin, a)
    antes = await vender(admin, a, cantidad=2, dias_atras=3)
    dia = (hoy() - timedelta(days=3)).isoformat()
    r = await admin.get("/api/ventas", params={"desde": dia, "hasta": dia})
    assert [v["id"] for v in r.json()] == [antes["id"]]


async def test_el_resumen_exige_sesion(publico):
    r = await publico.get(
        "/api/ventas/resumen", params={"desde": "2026-11-01", "hasta": "2026-11-30"}
    )
    assert r.status_code in (401, 403)
