"""Inventario por color: producir, vender, ajustar y editar lotes por (artículo, color)."""

from sqlalchemy import select

from app.models import MovimientoInventario
from tests.conftest import crear_articulo

ROJO = {"nombre": "Rojo", "hex": "#dc2626"}
AZUL = {"nombre": "Azul", "hex": "#2563eb"}


async def articulo_con_colores(admin, **extra):
    a = await crear_articulo(admin, colores=[ROJO, AZUL], **extra)
    return a, a["colores"][0]["id"], a["colores"][1]["id"]


async def producir(c, articulo_id, cantidad, color_id=None, **extra):
    item = {"articulo_id": articulo_id, "cantidad": cantidad}
    if color_id:
        item["color_id"] = color_id
    return await c.post("/api/produccion", json={"items": [item], **extra})


async def vender(c, articulo_id, cantidad, color_id=None):
    item = {"articulo_id": articulo_id, "cantidad": cantidad}
    if color_id:
        item["color_id"] = color_id
    return await c.post("/api/ventas", json={"items": [item]})


async def ver(c, articulo_id):
    return (await c.get(f"/api/articulos/{articulo_id}")).json()


def por_color(a):
    return {s["nombre"]: s["stock"] for s in a["stock_colores"]}


# ------------------------------------------------------------------------------ producir
async def test_producir_pide_color_si_el_articulo_tiene_colores(admin):
    a, rojo, _ = await articulo_con_colores(admin)
    r = await producir(admin, a["id"], 3)
    assert r.status_code == 422 and "elige uno" in r.json()["detail"]
    assert (await ver(admin, a["id"]))["stock"] == 0  # no quedó nada a medias
    assert (await producir(admin, a["id"], 3, rojo)).status_code == 201


async def test_el_stock_se_lleva_por_color_y_el_total_es_la_suma(admin):
    a, rojo, azul = await articulo_con_colores(admin)
    await producir(admin, a["id"], 5, rojo)
    await producir(admin, a["id"], 2, azul)
    v = await ver(admin, a["id"])
    assert v["stock"] == 7 and por_color(v) == {"Rojo": 5, "Azul": 2}
    assert all(s["color_id"] for s in v["stock_colores"])  # no hay «sin color asignado»
    # La lista de inventario trae el mismo desglose.
    inv = {x["id"]: x for x in (await admin.get("/api/inventario")).json()}
    assert por_color(inv[a["id"]]) == {"Rojo": 5, "Azul": 2}


async def test_un_lote_puede_traer_varios_colores_del_mismo_articulo(admin):
    a, rojo, azul = await articulo_con_colores(admin)
    r = await admin.post("/api/produccion", json={"items": [
        {"articulo_id": a["id"], "color_id": rojo, "cantidad": 4},
        {"articulo_id": a["id"], "color_id": azul, "cantidad": 1},
        {"articulo_id": a["id"], "color_id": rojo, "cantidad": 2},  # se suma al rojo
    ]})  # fmt: skip
    assert r.status_code == 201, r.text
    items = {(i["color"], i["cantidad"]) for i in r.json()["items"]}
    assert items == {("Rojo", 6), ("Azul", 1)}
    assert por_color(await ver(admin, a["id"])) == {"Rojo": 6, "Azul": 1}


async def test_color_inexistente_ajeno_o_en_articulo_sin_colores_se_rechaza(admin):
    a, rojo, _ = await articulo_con_colores(admin)
    otro, otro_rojo, _ = await articulo_con_colores(admin, nombre="Otro")
    sin_colores = await crear_articulo(admin, nombre="Liso")
    r = await producir(admin, a["id"], 1, otro_rojo)  # color de OTRO artículo
    assert r.status_code == 422 and "no tiene ese color" in r.json()["detail"]
    r = await producir(admin, a["id"], 1, "00000000-0000-0000-0000-000000000000")
    assert r.status_code == 422
    r = await producir(admin, sin_colores["id"], 1, rojo)
    assert r.status_code == 422 and "no tiene colores" in r.json()["detail"]
    assert (
        await producir(admin, sin_colores["id"], 2)
    ).status_code == 201  # sin color: como siempre
    assert (await ver(admin, sin_colores["id"]))["stock_colores"] == []


async def test_produccion_solo_historial_no_toca_el_stock_de_ningun_color(admin):
    a, rojo, _ = await articulo_con_colores(admin)
    r = await producir(admin, a["id"], 4, rojo, afecta_inventario=False)
    assert r.status_code == 201 and r.json()["items"][0]["color"] == "Rojo"
    assert (await ver(admin, a["id"]))["stock"] == 0


# -------------------------------------------------------------------------------- vender
async def test_vender_descuenta_del_color_elegido_y_valida_su_stock(admin):
    a, rojo, azul = await articulo_con_colores(admin)
    await producir(admin, a["id"], 3, rojo)
    await producir(admin, a["id"], 1, azul)
    r = await vender(admin, a["id"], 2, rojo)
    assert r.status_code == 201 and r.json()["items"][0]["color"] == "Rojo"
    assert por_color(await ver(admin, a["id"])) == {"Rojo": 1, "Azul": 1}
    # Hay 2 en total de rojo+azul, pero de AZUL solo hay 1: el error nombra el color.
    r = await vender(admin, a["id"], 2, azul)
    assert r.status_code == 409 and "Azul" in r.json()["detail"] and "hay 1" in r.json()["detail"]
    assert por_color(await ver(admin, a["id"])) == {"Rojo": 1, "Azul": 1}  # sin cambios


async def test_vender_sin_elegir_color_en_un_articulo_con_colores_se_rechaza(admin):
    a, rojo, _ = await articulo_con_colores(admin)
    await producir(admin, a["id"], 3, rojo)
    r = await vender(admin, a["id"], 1)
    assert r.status_code == 409 or r.status_code == 422  # no hay stock «sin color asignado»
    assert (await ver(admin, a["id"]))["stock"] == 3


async def test_anular_devuelve_la_pieza_a_su_color(admin):
    a, rojo, azul = await articulo_con_colores(admin)
    await producir(admin, a["id"], 2, rojo)
    await producir(admin, a["id"], 2, azul)
    venta = (await vender(admin, a["id"], 2, rojo)).json()
    assert por_color(await ver(admin, a["id"])) == {"Rojo": 0, "Azul": 2}
    assert (await admin.post(f"/api/ventas/{venta['id']}/anular")).status_code == 200
    assert por_color(await ver(admin, a["id"])) == {"Rojo": 2, "Azul": 2}


async def test_venta_de_varias_lineas_de_colores_distintos(admin):
    a, rojo, azul = await articulo_con_colores(admin)
    await producir(admin, a["id"], 3, rojo)
    await producir(admin, a["id"], 3, azul)
    r = await admin.post("/api/ventas", json={"items": [
        {"articulo_id": a["id"], "color_id": rojo, "cantidad": 1},
        {"articulo_id": a["id"], "color_id": azul, "cantidad": 2},
    ]})  # fmt: skip
    assert r.status_code == 201
    assert por_color(await ver(admin, a["id"])) == {"Rojo": 2, "Azul": 1}


# ------------------------------------------------ stock anterior a los colores («sin color»)
async def con_stock_antiguo(admin, db):
    """Un artículo que tenía 5 piezas ANTES de que se definieran sus colores."""
    a = await crear_articulo(admin)
    await producir(admin, a["id"], 5)
    r = await admin.patch(f"/api/articulos/{a['id']}", json={"colores": [ROJO, AZUL]})
    cs = r.json()["colores"]
    return a, cs[0]["id"], cs[1]["id"]


async def test_el_stock_anterior_a_los_colores_queda_como_sin_color_asignado(admin, db):
    a, rojo, azul = await con_stock_antiguo(admin, db)
    v = await ver(admin, a["id"])
    assert v["stock"] == 5
    sin = [s for s in v["stock_colores"] if s["color_id"] is None]
    assert len(sin) == 1 and sin[0]["stock"] == 5 and sin[0]["nombre"] is None
    assert por_color(v).get("Rojo") == 0


async def test_se_puede_vender_el_stock_sin_color_y_reasignarlo_con_ajustes(admin, db):
    a, rojo, azul = await con_stock_antiguo(admin, db)
    assert (await vender(admin, a["id"], 1)).status_code == 201  # sale del «sin color»
    # Reasignar 3: −3 sin color, +3 rojo.
    r = await admin.post(
        "/api/inventario/ajustes",
        json={"articulo_id": a["id"], "cantidad": -3, "nota": "pasar a rojo"},
    )
    assert r.status_code == 201, r.text
    r = await admin.post(
        "/api/inventario/ajustes",
        json={"articulo_id": a["id"], "color_id": rojo, "cantidad": 3, "nota": "pasar a rojo"},
    )
    assert r.status_code == 201, r.text
    v = await ver(admin, a["id"])
    assert v["stock"] == 4 and por_color(v)["Rojo"] == 3
    assert [s["stock"] for s in v["stock_colores"] if s["color_id"] is None] == [1]
    # SUMAR al «sin color asignado» no se permite: hay que elegir un color.
    r = await admin.post(
        "/api/inventario/ajustes",
        json={"articulo_id": a["id"], "cantidad": 2, "nota": "sumar sin color"},
    )
    assert r.status_code == 422 and "elige uno" in r.json()["detail"]


async def test_no_se_puede_producir_sin_color_aunque_haya_stock_antiguo(admin, db):
    a, rojo, _ = await con_stock_antiguo(admin, db)
    assert (await producir(admin, a["id"], 1)).status_code == 422


# ----------------------------------------------------------------------------- ajustes
async def test_ajuste_por_color_no_deja_negativos_y_nombra_el_color(admin):
    a, rojo, azul = await articulo_con_colores(admin)
    await producir(admin, a["id"], 2, rojo)
    r = await admin.post(
        "/api/inventario/ajustes",
        json={"articulo_id": a["id"], "color_id": azul, "cantidad": -1, "nota": "se dañó"},
    )
    assert r.status_code == 409 and "Azul" in r.json()["detail"]
    r = await admin.post(
        "/api/inventario/ajustes",
        json={"articulo_id": a["id"], "color_id": rojo, "cantidad": -1, "nota": "se dañó"},
    )
    assert r.status_code == 201 and por_color(r.json()) == {"Rojo": 1, "Azul": 0}
    r = await admin.post(
        "/api/inventario/ajustes", json={"articulo_id": a["id"], "cantidad": 1, "nota": "sin color"}
    )
    assert r.status_code == 422  # artículo con colores: hay que elegir uno


async def test_el_kardex_muestra_el_color(admin):
    a, rojo, _ = await articulo_con_colores(admin)
    await producir(admin, a["id"], 2, rojo)
    movs = (await admin.get(f"/api/inventario/movimientos?articulo_id={a['id']}")).json()
    assert movs[0]["color"] == "Rojo" and movs[0]["tipo"] == "produccion"


# -------------------------------------------------------------------- quitar / editar colores
async def test_no_se_puede_quitar_un_color_con_stock(admin):
    a, rojo, azul = await articulo_con_colores(admin)
    await producir(admin, a["id"], 2, rojo)
    solo_azul = [{"id": azul, "nombre": "Azul", "hex": "#2563eb"}]
    r = await admin.patch(f"/api/articulos/{a['id']}", json={"colores": solo_azul})
    assert r.status_code == 409 and "Rojo" in r.json()["detail"] and "Ajustar" in r.json()["detail"]
    assert len((await ver(admin, a["id"]))["colores"]) == 2
    # Con stock 0 sí se puede.
    await admin.post(
        "/api/inventario/ajustes",
        json={"articulo_id": a["id"], "color_id": rojo, "cantidad": -2, "nota": "vaciar"},
    )
    r = await admin.patch(f"/api/articulos/{a['id']}", json={"colores": solo_azul})
    assert r.status_code == 200 and [c["nombre"] for c in r.json()["colores"]] == ["Azul"]


async def test_renombrar_un_color_conserva_su_stock(admin):
    a, rojo, azul = await articulo_con_colores(admin)
    await producir(admin, a["id"], 4, rojo)
    r = await admin.patch(f"/api/articulos/{a['id']}", json={"colores": [
        {"id": rojo, "nombre": "Rojo vivo", "hex": "#ff0000"},
        {"id": azul, "nombre": "Azul", "hex": "#2563eb"},
    ]})  # fmt: skip
    assert por_color(r.json()) == {"Rojo vivo": 4, "Azul": 0}


# ----------------------------------------------------------------------- editar un lote
async def test_editar_un_lote_cambiando_de_color_ajusta_cada_color(admin):
    a, rojo, azul = await articulo_con_colores(admin)
    lote = (await producir(admin, a["id"], 3, rojo)).json()
    r = await admin.put(f"/api/produccion/{lote['id']}", json={"items": [
        {"articulo_id": a["id"], "color_id": azul, "cantidad": 3}]})  # fmt: skip
    assert r.status_code == 200, r.text
    assert por_color(await ver(admin, a["id"])) == {"Rojo": 0, "Azul": 3}
    assert r.json()["items"][0]["color"] == "Azul"


async def test_no_se_puede_reducir_un_lote_por_debajo_de_lo_vendido_de_ese_color(admin):
    a, rojo, azul = await articulo_con_colores(admin)
    lote = (await producir(admin, a["id"], 3, rojo)).json()
    await producir(admin, a["id"], 5, azul)  # sobra azul, pero no sirve para el rojo
    await vender(admin, a["id"], 2, rojo)
    r = await admin.put(f"/api/produccion/{lote['id']}", json={"items": [
        {"articulo_id": a["id"], "color_id": rojo, "cantidad": 0 + 1}]})  # fmt: skip
    assert r.status_code == 409 and "Rojo" in r.json()["detail"]
    assert por_color(await ver(admin, a["id"])) == {"Rojo": 1, "Azul": 5}


async def test_editar_un_lote_antiguo_sin_color_no_obliga_a_ponerlo(admin, db):
    a = await crear_articulo(admin)
    lote = (await producir(admin, a["id"], 3)).json()  # lote de antes de los colores
    await admin.patch(f"/api/articulos/{a['id']}", json={"colores": [ROJO]})
    r = await admin.put(
        f"/api/produccion/{lote['id']}",
        json={"items": [{"articulo_id": a["id"], "cantidad": 4}], "nota": "corregido"},
    )
    assert r.status_code == 200, r.text  # la línea ya existía sin color: se conserva
    assert (await ver(admin, a["id"]))["stock"] == 4


# ------------------------------------------------------------------------- catálogo público
async def test_catalogo_dice_que_color_esta_disponible_sin_dar_cifras(admin, publico):
    a, rojo, azul = await articulo_con_colores(admin)
    await producir(admin, a["id"], 3, rojo)
    cat = (await publico.get("/api/publico/articulos")).json()["articulos"][0]
    disp = {c["nombre"]: c["disponible"] for c in cat["colores"]}
    assert disp == {"Rojo": True, "Azul": False} and cat["disponible"] is True
    assert "stock" not in str(cat)  # nunca el número exacto


async def test_los_movimientos_guardan_el_color_en_el_libro_mayor(admin, db):
    a, rojo, _ = await articulo_con_colores(admin)
    await producir(admin, a["id"], 2, rojo)
    await vender(admin, a["id"], 1, rojo)
    colores = (
        await db.execute(select(MovimientoInventario.tipo, MovimientoInventario.color_id))
    ).all()
    assert {(t, str(c)) for t, c in colores} == {("produccion", rojo), ("venta", rojo)}
