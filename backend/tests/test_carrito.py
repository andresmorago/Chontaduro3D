"""Pedidos de varios artículos (mini carrito del catálogo público)."""

from sqlalchemy import func, select

from app.models import MovimientoInventario, Pedido, PedidoItem
from tests.conftest import crear_articulo, producir, stock

ROJO = {"nombre": "Rojo", "hex": "#dc2626"}
AZUL = {"nombre": "Azul", "hex": "#2563eb"}


def carrito(*items, **extra):
    return {"nombre": "Ana Pérez", "whatsapp": "300 123 4567",
            "items": [{"articulo_id": a, "cantidad": n, **({"color": c} if c else {})}
                      for a, n, c in items], **extra}  # fmt: skip


async def pedir(publico, *items, **extra):
    return await publico.post("/api/publico/pedidos", json=carrito(*items, **extra))


async def test_un_pedido_puede_llevar_varios_articulos_y_colores(admin, publico):
    llavero = await crear_articulo(admin, nombre="Llavero", precio=6000, colores=[ROJO, AZUL])
    maceta = await crear_articulo(admin, nombre="Maceta", precio=18000)
    r = await pedir(
        publico, (llavero["id"], 2, "Rojo"), (llavero["id"], 1, "azul"), (maceta["id"], 3, None)
    )
    assert r.status_code == 201, r.text
    lista = (await admin.get("/api/pedidos")).json()
    assert len(lista) == 1  # UN pedido con tres renglones, no tres pedidos
    p = lista[0]
    assert p["piezas"] == 6 and p["total_estimado"] == 2 * 6000 + 6000 + 3 * 18000
    renglones = {(i["articulo"], i["color"], i["cantidad"], i["subtotal"]) for i in p["items"]}
    assert renglones == {
        ("Llavero", "Rojo", 2, 12000),
        ("Llavero", "Azul", 1, 6000),
        ("Maceta", None, 3, 54000),
    }


async def test_el_mismo_articulo_y_color_en_dos_renglones_se_suman(admin, publico):
    a = await crear_articulo(admin, colores=[ROJO])
    r = await pedir(publico, (a["id"], 2, "Rojo"), (a["id"], 3, "rojo"))
    assert r.status_code == 201
    items = (await admin.get("/api/pedidos")).json()[0]["items"]
    assert [(i["color"], i["cantidad"]) for i in items] == [("Rojo", 5)]
    # La suma nunca pasa de 99.
    r = await pedir(publico, (a["id"], 90, "Rojo"), (a["id"], 90, "Rojo"))
    assert (await admin.get("/api/pedidos")).json()[0]["items"][0]["cantidad"] == 99


async def test_falta_el_color_de_un_renglon_y_no_se_guarda_nada(admin, publico, db):
    con_colores = await crear_articulo(admin, nombre="Con colores", colores=[ROJO])
    sin_colores = await crear_articulo(admin, nombre="Liso")
    r = await pedir(publico, (sin_colores["id"], 1, None), (con_colores["id"], 1, None))
    assert r.status_code == 422 and "Con colores" in r.json()["detail"]
    assert (await db.execute(select(func.count()).select_from(Pedido))).scalar_one() == 0
    assert (await db.execute(select(func.count()).select_from(PedidoItem))).scalar_one() == 0


async def test_un_articulo_no_disponible_anula_todo_el_pedido(admin, publico, db):
    bueno = await crear_articulo(admin, nombre="Bueno")
    oculto = await crear_articulo(admin, nombre="Oculto", publicado=False)
    r = await pedir(publico, (bueno["id"], 1, None), (oculto["id"], 1, None))
    assert r.status_code == 404
    assert (await db.execute(select(func.count()).select_from(Pedido))).scalar_one() == 0


async def test_limites_del_carrito(admin, publico):
    a = await crear_articulo(admin)
    assert (await pedir(publico)).status_code == 422  # sin renglones
    muchos = [(a["id"], 1, None)] * 21
    assert (await pedir(publico, *muchos)).status_code == 422  # más de 20 renglones
    assert (await pedir(publico, (a["id"], 0, None))).status_code == 422
    assert (await pedir(publico, (a["id"], 100, None))).status_code == 422
    # Mezclar los dos formatos es ambiguo.
    r = await publico.post(
        "/api/publico/pedidos",
        json={**carrito((a["id"], 1, None)), "articulo_id": a["id"], "cantidad": 1},
    )
    assert r.status_code == 422


async def test_el_formato_anterior_de_un_solo_articulo_sigue_funcionando(admin, publico):
    a = await crear_articulo(admin, colores=[ROJO])
    r = await publico.post("/api/publico/pedidos", json={
        "articulo_id": a["id"], "nombre": "Ana Pérez", "whatsapp": "3001234567",
        "cantidad": 2, "color": "Rojo"})  # fmt: skip
    assert r.status_code == 201
    p = (await admin.get("/api/pedidos")).json()[0]
    assert p["piezas"] == 2 and p["items"][0]["color"] == "Rojo"


async def test_un_pedido_de_varios_articulos_no_toca_el_inventario(admin, publico, db):
    a = await crear_articulo(admin, nombre="A")
    b = await crear_articulo(admin, nombre="B", colores=[ROJO])
    await producir(admin, a["id"], 5)
    movimientos = (
        await db.execute(select(func.count()).select_from(MovimientoInventario))
    ).scalar_one()
    assert (await pedir(publico, (a["id"], 2, None), (b["id"], 4, "Rojo"))).status_code == 201
    assert await stock(admin, a["id"]) == 5 and await stock(admin, b["id"]) == 0
    assert (
        await db.execute(select(func.count()).select_from(MovimientoInventario))
    ).scalar_one() == movimientos
    pid = (await admin.get("/api/pedidos")).json()[0]["id"]
    r = await admin.patch(f"/api/pedidos/{pid}", json={"estado": "cerrado"})
    assert (
        r.status_code == 200 and len(r.json()["items"]) == 2
    )  # el estado cambia, los renglones siguen
    assert await stock(admin, a["id"]) == 5


async def test_el_catalogo_no_deja_de_aceptar_pedidos_por_el_limite_de_renglones_normales(
    admin, publico
):
    articulos = [await crear_articulo(admin, nombre=f"Art {i}") for i in range(20)]
    r = await pedir(publico, *[(a["id"], 1, None) for a in articulos])  # el máximo: 20 renglones
    assert r.status_code == 201
    assert len((await admin.get("/api/pedidos")).json()[0]["items"]) == 20
