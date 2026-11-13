import asyncio

from tests.conftest import crear_articulo, producir, stock


async def test_produccion_suma_stock(admin):
    a = await crear_articulo(admin)
    await producir(admin, a["id"], 10)
    await producir(admin, a["id"], 5)
    assert await stock(admin, a["id"]) == 15


async def test_venta_resta_stock_y_congela_precio(admin):
    a = await crear_articulo(admin, precio=6000)
    await producir(admin, a["id"], 10)
    r = await admin.post(
        "/api/ventas",
        json={"metodo_pago": "efectivo", "items": [{"articulo_id": a["id"], "cantidad": 3}]},
    )
    assert r.status_code == 201
    venta = r.json()
    assert venta["total"] == 18000
    assert await stock(admin, a["id"]) == 7

    # Cambiar el precio maestro no reescribe la venta ya hecha.
    await admin.patch(f"/api/articulos/{a['id']}", json={"precio_venta": 9000})
    hoy = (await admin.get("/api/ventas")).json()
    assert hoy[0]["total"] == 18000 and hoy[0]["items"][0]["precio_unitario"] == 6000


async def test_venta_con_descuento_por_linea(admin):
    a = await crear_articulo(admin, precio=6000)
    await producir(admin, a["id"], 10)
    r = await admin.post(
        "/api/ventas",
        json={"items": [{"articulo_id": a["id"], "cantidad": 2, "precio_unitario": 5000}]},
    )
    assert r.json()["total"] == 10000


async def test_venta_sin_stock_falla_y_no_cambia_nada(admin):
    a = await crear_articulo(admin)
    b = await crear_articulo(admin, "Otro")
    await producir(admin, a["id"], 5)
    await producir(admin, b["id"], 1)
    r = await admin.post(
        "/api/ventas",
        json={
            "items": [
                {"articulo_id": a["id"], "cantidad": 2},
                {"articulo_id": b["id"], "cantidad": 3},
            ]
        },
    )
    assert r.status_code == 409 and "hay 1" in r.json()["detail"]
    assert await stock(admin, a["id"]) == 5  # la línea válida tampoco se aplicó
    assert await stock(admin, b["id"]) == 1
    assert (await admin.get("/api/ventas")).json() == []


async def test_anular_devuelve_stock_una_sola_vez(admin):
    a = await crear_articulo(admin)
    await producir(admin, a["id"], 10)
    v = (
        await admin.post("/api/ventas", json={"items": [{"articulo_id": a["id"], "cantidad": 4}]})
    ).json()
    assert await stock(admin, a["id"]) == 6
    assert (await admin.post(f"/api/ventas/{v['id']}/anular")).json()["anulada"] is True
    assert await stock(admin, a["id"]) == 10
    await admin.post(f"/api/ventas/{v['id']}/anular")  # repetir no devuelve doble
    assert await stock(admin, a["id"]) == 10


async def test_ajuste_no_deja_stock_negativo(admin):
    a = await crear_articulo(admin)
    await producir(admin, a["id"], 3)
    ok = await admin.post(
        "/api/inventario/ajustes",
        json={"articulo_id": a["id"], "cantidad": -2, "nota": "pieza rota"},
    )
    assert ok.status_code == 201 and ok.json()["stock"] == 1
    mal = await admin.post(
        "/api/inventario/ajustes", json={"articulo_id": a["id"], "cantidad": -5, "nota": "conteo"}
    )
    assert mal.status_code == 409
    cero = await admin.post(
        "/api/inventario/ajustes", json={"articulo_id": a["id"], "cantidad": 0, "nota": "nada"}
    )
    assert cero.status_code == 422


async def test_kardex_registra_cada_movimiento(admin):
    a = await crear_articulo(admin)
    await producir(admin, a["id"], 10)
    await admin.post("/api/ventas", json={"items": [{"articulo_id": a["id"], "cantidad": 2}]})
    mov = (await admin.get(f"/api/inventario/movimientos?articulo_id={a['id']}")).json()
    assert sorted((m["tipo"], m["cantidad"]) for m in mov) == [("produccion", 10), ("venta", -2)]


async def test_ventas_simultaneas_no_venden_lo_que_no_hay(admin):
    a = await crear_articulo(admin)
    await producir(admin, a["id"], 5)

    async def vender():
        return await admin.post(
            "/api/ventas", json={"items": [{"articulo_id": a["id"], "cantidad": 1}]}
        )

    respuestas = await asyncio.gather(*[vender() for _ in range(12)])
    codigos = sorted(r.status_code for r in respuestas)
    assert codigos.count(201) == 5 and codigos.count(409) == 7
    assert await stock(admin, a["id"]) == 0


async def test_fechas_futuras_o_muy_viejas_se_rechazan(admin):
    a = await crear_articulo(admin)
    await producir(admin, a["id"], 3)
    item = [{"articulo_id": a["id"], "cantidad": 1}]
    assert (
        await admin.post("/api/ventas", json={"fecha": "2999-01-01", "items": item})
    ).status_code == 422
    assert (
        await admin.post("/api/ventas", json={"fecha": "2000-01-01", "items": item})
    ).status_code == 422


async def test_articulo_archivado_no_se_vende_ni_produce(admin):
    a = await crear_articulo(admin)
    await producir(admin, a["id"], 3)
    await admin.patch(f"/api/articulos/{a['id']}", json={"activo": False})
    r = await admin.post("/api/ventas", json={"items": [{"articulo_id": a["id"], "cantidad": 1}]})
    assert r.status_code == 422


async def test_panel_resume_el_dia(admin):
    a = await crear_articulo(admin, precio=1000, stock_minimo=5)
    await producir(admin, a["id"], 4)
    await admin.post("/api/ventas", json={"items": [{"articulo_id": a["id"], "cantidad": 1}]})
    p = (await admin.get("/api/panel")).json()
    assert p["hoy"]["total"] == 1000 and p["hoy"]["cantidad"] == 1
    assert [s["codigo"] for s in p["stock_bajo"]] == [a["codigo"]]
    assert p["unidades_en_stock"] == 3 and len(p["ultimos_dias"]) == 7
