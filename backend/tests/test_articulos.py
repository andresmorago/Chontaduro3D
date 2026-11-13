from tests.conftest import crear_articulo


async def test_codigos_legibles_consecutivos(admin):
    a = await crear_articulo(admin, "Uno")
    b = await crear_articulo(admin, "Dos")
    assert (a["codigo"], b["codigo"]) == ("IMP-0001", "IMP-0002")
    assert a["stock"] == 0


async def test_cambio_de_precio_queda_en_el_historial(admin):
    a = await crear_articulo(admin, "Maceta", precio=18000)
    r = await admin.patch(f"/api/articulos/{a['id']}", json={"precio_venta": 20000})
    assert r.status_code == 200 and r.json()["precio_venta"] == 20000
    # Mismo precio otra vez: no ensucia el historial.
    await admin.patch(f"/api/articulos/{a['id']}", json={"precio_venta": 20000})
    precios = [p["precio"] for p in (await admin.get(f"/api/articulos/{a['id']}/precios")).json()]
    assert precios == [20000, 18000]


async def test_validaciones(admin):
    base = {"nombre": "X", "precio_venta": 1}
    assert (
        await admin.post("/api/articulos", json={**base, "precio_venta": -5})
    ).status_code == 422
    assert (await admin.post("/api/articulos", json={**base, "nombre": ""})).status_code == 422
    assert (await admin.post("/api/articulos", json={**base, "extra": 1})).status_code == 422
    assert (
        await admin.get("/api/articulos/00000000-0000-0000-0000-000000000000")
    ).status_code == 404


async def test_archivar_oculta_del_catalogo(admin, publico):
    a = await crear_articulo(admin, "Se va")
    assert len((await publico.get("/api/publico/articulos")).json()["articulos"]) == 1
    await admin.patch(f"/api/articulos/{a['id']}", json={"activo": False})
    assert (await publico.get("/api/publico/articulos")).json()["articulos"] == []
    assert (await admin.get("/api/articulos")).json() == []
    assert len((await admin.get("/api/articulos?incluir_inactivos=true")).json()) == 1
