from sqlalchemy import func, select

from app.models import MovimientoInventario, Venta
from tests.conftest import crear_articulo, producir, stock


def pedido(articulo_id, **extra):
    return {
        "articulo_id": articulo_id,
        "nombre": "Ana Pérez",
        "whatsapp": "+57 300 123 4567",
        "cantidad": 2,
        **extra,
    }


async def test_catalogo_no_expone_stock_exacto_ni_ocultos(admin, publico):
    visible = await crear_articulo(admin, "Visible")
    await crear_articulo(admin, "Oculto", publicado=False)
    await producir(admin, visible["id"], 7)
    r = (await publico.get("/api/publico/articulos")).json()
    assert [a["nombre"] for a in r["articulos"]] == ["Visible"]
    a = r["articulos"][0]
    assert a["disponible"] is True
    assert "stock" not in a and "stock_minimo" not in a and "activo" not in a


async def test_sin_stock_figura_como_sobre_pedido(admin, publico):
    await crear_articulo(admin, "Agotado")
    assert (await publico.get("/api/publico/articulos")).json()["articulos"][0][
        "disponible"
    ] is False


async def test_pedido_no_toca_inventario_ni_ventas(admin, publico, db):
    a = await crear_articulo(admin)
    await producir(admin, a["id"], 10)
    movimientos_antes = (
        await db.execute(select(func.count()).select_from(MovimientoInventario))
    ).scalar_one()

    r = await publico.post("/api/publico/pedidos", json=pedido(a["id"], cantidad=3))
    assert r.status_code == 201 and r.json()["ok"] is True

    assert await stock(admin, a["id"]) == 10
    assert (
        await db.execute(select(func.count()).select_from(MovimientoInventario))
    ).scalar_one() == movimientos_antes
    assert (await db.execute(select(func.count()).select_from(Venta))).scalar_one() == 0
    pedidos = (await admin.get("/api/pedidos")).json()
    assert len(pedidos) == 1 and pedidos[0]["estado"] == "nuevo" and pedidos[0]["cantidad"] == 3

    # Ni siquiera marcarlo como cerrado mueve el stock: la venta se registra aparte.
    await admin.patch(f"/api/pedidos/{pedidos[0]['id']}", json={"estado": "cerrado"})
    assert await stock(admin, a["id"]) == 10


async def test_pedido_se_puede_hacer_de_algo_sin_stock(admin, publico):
    a = await crear_articulo(admin)
    assert (await publico.post("/api/publico/pedidos", json=pedido(a["id"]))).status_code == 201


async def test_pedido_valida_entrada(admin, publico):
    a = await crear_articulo(admin)
    assert (
        await publico.post("/api/publico/pedidos", json=pedido(a["id"], cantidad=0))
    ).status_code == 422
    assert (
        await publico.post("/api/publico/pedidos", json=pedido(a["id"], cantidad=100))
    ).status_code == 422
    assert (
        await publico.post("/api/publico/pedidos", json=pedido(a["id"], whatsapp="abc"))
    ).status_code == 422
    assert (
        await publico.post("/api/publico/pedidos", json=pedido(a["id"], nombre="A"))
    ).status_code == 422
    assert (
        await publico.post("/api/publico/pedidos", json=pedido(a["id"], estado="cerrado"))
    ).status_code == 422
    assert (
        await publico.post(
            "/api/publico/pedidos", json=pedido("00000000-0000-0000-0000-000000000000")
        )
    ).status_code == 404


async def test_pedido_de_articulo_oculto_se_rechaza(admin, publico):
    a = await crear_articulo(admin, publicado=False)
    assert (await publico.post("/api/publico/pedidos", json=pedido(a["id"]))).status_code == 404


async def test_honeypot_responde_ok_sin_guardar(admin, publico):
    a = await crear_articulo(admin)
    r = await publico.post(
        "/api/publico/pedidos", json=pedido(a["id"], sitio_web="http://spam.example")
    )
    assert r.status_code == 201
    assert (await admin.get("/api/pedidos")).json() == []


async def test_limite_de_pedidos_por_origen(admin, publico):
    a = await crear_articulo(admin)
    codigos = [
        (await publico.post("/api/publico/pedidos", json=pedido(a["id"]))).status_code
        for _ in range(7)
    ]
    assert codigos == [201] * 5 + [429] * 2


async def test_pedido_no_se_puede_ver_sin_sesion(admin, publico):
    a = await crear_articulo(admin)
    await publico.post("/api/publico/pedidos", json=pedido(a["id"]))
    assert (await publico.get("/api/pedidos")).status_code == 401
