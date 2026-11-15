"""Ventas asociadas (opcionalmente) a pedidos: atender un pedido y cerrarlo con la venta."""

from sqlalchemy import select

from app.models import RegistroAuditoria
from tests.conftest import crear_articulo, producir, stock
from tests.test_carrito import pedir

ROJO = {"nombre": "Rojo", "hex": "#dc2626"}


async def un_pedido(admin, publico, **extra) -> dict:
    a = await crear_articulo(admin, nombre="Llavero", precio=6000)
    await producir(admin, a["id"], 10)
    r = await pedir(publico, (a["id"], 2, None), **extra)
    assert r.status_code == 201, r.text
    return {"articulo": a, "pedido": (await admin.get("/api/pedidos")).json()[0]}


def venta(articulo, pedido=None, cantidad=2, **extra):
    d = {"items": [{"articulo_id": articulo["id"], "cantidad": cantidad}], **extra}
    if pedido:
        d["pedido_id"] = pedido["id"]
    return d


async def test_una_venta_sin_pedido_sigue_igual(admin, publico):
    x = await un_pedido(admin, publico)
    r = await admin.post("/api/ventas", json=venta(x["articulo"]))
    assert r.status_code == 201, r.text
    assert r.json()["pedido_id"] is None and r.json()["pedido_nombre"] is None
    p = (await admin.get("/api/pedidos")).json()[0]
    assert p["estado"] == "nuevo" and p["ventas"] == [] and p["total_vendido"] == 0


async def test_asociar_una_venta_a_un_pedido_sin_cerrarlo(admin, publico):
    x = await un_pedido(admin, publico)
    r = await admin.post("/api/ventas", json=venta(x["articulo"], x["pedido"], cantidad=1))
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["pedido_id"] == x["pedido"]["id"] and v["pedido_nombre"] == "Ana Pérez"
    assert v["cliente"] == "Ana Pérez"  # sin cliente escrito, toma el del pedido
    p = (await admin.get("/api/pedidos")).json()[0]
    assert p["estado"] == "nuevo"  # entrega parcial: sigue abierto
    assert [(s["id"], s["total"], s["anulada"]) for s in p["ventas"]] == [(v["id"], 6000, False)]
    assert p["total_vendido"] == 6000
    assert await stock(admin, x["articulo"]["id"]) == 9  # la venta mueve el inventario como siempre


async def test_cerrar_el_pedido_con_la_venta(admin, publico, db):
    x = await un_pedido(admin, publico)
    r = await admin.post(
        "/api/ventas", json=venta(x["articulo"], x["pedido"], cerrar_pedido=True, cliente="Ana P.")
    )
    assert r.status_code == 201, r.text
    assert r.json()["cliente"] == "Ana P."  # lo escrito manda sobre el nombre del pedido
    p = (await admin.get("/api/pedidos")).json()[0]
    assert p["estado"] == "cerrado" and p["total_vendido"] == 12000
    auditoria = (await db.execute(select(RegistroAuditoria))).scalars().all()
    assert any(a.accion == "pedido_estado" and a.detalle.get("por_venta") for a in auditoria)


async def test_varias_ventas_para_un_mismo_pedido(admin, publico):
    x = await un_pedido(admin, publico)
    for _ in range(2):
        r = await admin.post("/api/ventas", json=venta(x["articulo"], x["pedido"], cantidad=1))
        assert r.status_code == 201
    p = (await admin.get("/api/pedidos")).json()[0]
    assert len(p["ventas"]) == 2 and p["total_vendido"] == 12000


async def test_una_venta_anulada_se_marca_y_no_cuenta_como_vendida(admin, publico):
    x = await un_pedido(admin, publico)
    v = (await admin.post("/api/ventas", json=venta(x["articulo"], x["pedido"]))).json()
    await admin.post(f"/api/ventas/{v['id']}/anular")
    p = (await admin.get("/api/pedidos")).json()[0]
    assert p["ventas"][0]["anulada"] is True and p["total_vendido"] == 0
    assert await stock(admin, x["articulo"]["id"]) == 10


async def test_no_se_asocia_a_un_pedido_cerrado_descartado_o_inexistente(admin, publico):
    x = await un_pedido(admin, publico)
    pid = x["pedido"]["id"]
    for estado in ("cerrado", "descartado"):
        await admin.patch(f"/api/pedidos/{pid}", json={"estado": estado})
        r = await admin.post("/api/ventas", json=venta(x["articulo"], x["pedido"]))
        assert r.status_code == 409 and estado in r.json()["detail"]
    await admin.patch(f"/api/pedidos/{pid}", json={"estado": "contactado"})
    assert (
        await admin.post("/api/ventas", json=venta(x["articulo"], x["pedido"]))
    ).status_code == 201
    r = await admin.post(
        "/api/ventas",
        json=venta(x["articulo"]) | {"pedido_id": "00000000-0000-4000-8000-000000000000"},
    )
    assert r.status_code == 422
    assert await stock(admin, x["articulo"]["id"]) == 8  # lo rechazado no movió inventario


async def test_cerrar_sin_pedido_es_error(admin, publico):
    x = await un_pedido(admin, publico)
    r = await admin.post("/api/ventas", json=venta(x["articulo"], cerrar_pedido=True))
    assert r.status_code == 422


async def test_si_la_venta_falla_el_pedido_no_se_cierra(admin, publico):
    x = await un_pedido(admin, publico)
    r = await admin.post(
        "/api/ventas", json=venta(x["articulo"], x["pedido"], cantidad=99, cerrar_pedido=True)
    )
    assert r.status_code == 409  # no alcanza el stock
    assert (await admin.get("/api/pedidos")).json()[0]["estado"] == "nuevo"


async def test_el_historial_de_ventas_muestra_el_pedido(admin, publico):
    x = await un_pedido(admin, publico)
    await admin.post("/api/ventas", json=venta(x["articulo"], x["pedido"]))
    (v,) = (await admin.get("/api/ventas")).json()
    assert v["pedido_nombre"] == "Ana Pérez"


async def test_exige_sesion(publico):
    r = await publico.post("/api/ventas", json={"items": [], "pedido_id": None})
    assert r.status_code == 401
