"""Demanda de los pedidos por atender, agrupada por artículo: cuánto falta producir."""

from tests.conftest import crear_articulo, producir
from tests.test_carrito import pedir

ROJO = {"nombre": "Rojo", "hex": "#dc2626"}
AZUL = {"nombre": "Azul", "hex": "#2563eb"}


async def demanda(admin) -> dict:
    r = await admin.get("/api/pedidos/demanda")
    assert r.status_code == 200, r.text
    return {d["articulo"]: d for d in r.json()}


async def estado(admin, pedido_id, nuevo):
    r = await admin.patch(f"/api/pedidos/{pedido_id}", json={"estado": nuevo})
    assert r.status_code == 200, r.text


async def test_sin_pedidos_no_hay_demanda(admin):
    assert (await admin.get("/api/pedidos/demanda")).json() == []


async def test_suma_los_pedidos_y_resta_el_stock(admin, publico):
    a = await crear_articulo(admin, nombre="Llavero")
    await producir(admin, a["id"], 4)
    assert (await pedir(publico, (a["id"], 3, None))).status_code == 201
    assert (await pedir(publico, (a["id"], 5, None), nombre="Luis Gómez")).status_code == 201
    d = (await demanda(admin))["Llavero"]
    assert (d["pedidos"], d["pendiente"], d["stock"], d["faltan"]) == (2, 8, 4, 4)
    assert d["colores"] == []


async def test_con_stock_de_sobra_no_falta_nada(admin, publico):
    a = await crear_articulo(admin, nombre="Llavero")
    await producir(admin, a["id"], 10)
    await pedir(publico, (a["id"], 3, None))
    d = (await demanda(admin))["Llavero"]
    assert (d["pendiente"], d["stock"], d["faltan"]) == (3, 10, 0)


async def test_los_pedidos_cerrados_o_descartados_no_cuentan(admin, publico):
    a = await crear_articulo(admin, nombre="Llavero")
    await pedir(publico, (a["id"], 3, None))
    await pedir(publico, (a["id"], 2, None), nombre="Luis Gómez")
    pedidos = (await admin.get("/api/pedidos")).json()
    reciente, antiguo = pedidos[0], pedidos[1]  # el listado va del más nuevo al más viejo
    await estado(admin, antiguo["id"], "cerrado")  # el de 3 piezas
    await estado(admin, reciente["id"], "contactado")  # contactado sigue abierto (2 piezas)
    assert (await demanda(admin))["Llavero"]["pendiente"] == 2
    await estado(admin, reciente["id"], "descartado")
    assert await demanda(admin) == {}


async def test_por_color_y_el_stock_sin_color_cubre_lo_que_falte(admin, publico):
    a = await crear_articulo(admin, nombre="Llavero", colores=[ROJO, AZUL])
    rojo, azul = a["colores"][0]["id"], a["colores"][1]["id"]
    for color, n in ((rojo, 3), (azul, 1)):
        r = await admin.post(
            "/api/produccion",
            json={"items": [{"articulo_id": a["id"], "color_id": color, "cantidad": n}]},
        )
        assert r.status_code == 201, r.text
    await pedir(publico, (a["id"], 5, "Rojo"), (a["id"], 4, "Azul"))
    d = (await demanda(admin))["Llavero"]
    por_color = {c["color"]: (c["pendiente"], c["stock"], c["faltan"]) for c in d["colores"]}
    assert por_color == {"Rojo": (5, 3, 2), "Azul": (4, 1, 3)}
    assert (d["pendiente"], d["stock"], d["faltan"]) == (9, 4, 5)


async def test_lo_ya_vendido_al_pedido_no_se_vuelve_a_producir(admin, publico):
    a = await crear_articulo(admin, nombre="Llavero")
    await producir(admin, a["id"], 3)
    await pedir(publico, (a["id"], 5, None))
    pedido = (await admin.get("/api/pedidos")).json()[0]
    v = await admin.post(
        "/api/ventas",
        json={"pedido_id": pedido["id"], "items": [{"articulo_id": a["id"], "cantidad": 3}]},
    )
    assert v.status_code == 201, v.text
    # Pidieron 5, ya se entregaron 3 (el stock quedó en 0): faltan 2, no 5.
    d = (await demanda(admin))["Llavero"]
    assert (d["pendiente"], d["stock"], d["faltan"]) == (2, 0, 2)
    # Anular la venta devuelve las piezas al stock y al pendiente.
    assert (await admin.post(f"/api/ventas/{v.json()['id']}/anular")).status_code in (200, 204)
    d = (await demanda(admin))["Llavero"]
    assert (d["pendiente"], d["stock"], d["faltan"]) == (5, 3, 2)


async def test_ordena_primero_lo_que_mas_falta(admin, publico):
    a = await crear_articulo(admin, nombre="Maceta")
    b = await crear_articulo(admin, nombre="Llavero")
    await producir(admin, a["id"], 5)
    await pedir(publico, (a["id"], 2, None), (b["id"], 4, None))
    r = (await admin.get("/api/pedidos/demanda")).json()
    assert [d["articulo"] for d in r] == ["Llavero", "Maceta"]


async def test_exige_sesion(publico):
    assert (await publico.get("/api/pedidos/demanda")).status_code in (401, 403)
