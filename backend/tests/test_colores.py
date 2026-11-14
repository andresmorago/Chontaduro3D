"""Colores por artículo: el cliente elige uno al pedir."""

from tests.conftest import crear_articulo

ROJO = {"nombre": "Rojo", "hex": "#dc2626"}
AZUL = {"nombre": "Azul", "hex": "#2563eb"}


def pedido(articulo_id, **extra):
    return {"articulo_id": articulo_id, "nombre": "Ana Pérez", "whatsapp": "3001234567",
            "cantidad": 1, **extra}  # fmt: skip


async def test_colores_se_crean_y_se_ven_en_catalogo(admin, publico):
    a = await crear_articulo(admin, colores=[ROJO, AZUL])
    assert [c["nombre"] for c in a["colores"]] == ["Rojo", "Azul"]
    cat = (await publico.get("/api/publico/articulos")).json()["articulos"][0]
    assert [(c["nombre"], c["hex"]) for c in cat["colores"]] == [
        ("Rojo", "#dc2626"),
        ("Azul", "#2563eb"),
    ]


async def test_articulo_sin_colores_tiene_lista_vacia(admin, publico):
    a = await crear_articulo(admin)
    assert a["colores"] == []
    assert (await publico.get("/api/publico/articulos")).json()["articulos"][0]["colores"] == []


async def test_editar_colores_reemplaza_y_omitirlos_no_los_toca(admin):
    a = await crear_articulo(admin, colores=[ROJO])
    r = await admin.patch(f"/api/articulos/{a['id']}", json={"nombre": "Otro nombre"})
    assert [c["nombre"] for c in r.json()["colores"]] == ["Rojo"]
    r = await admin.patch(f"/api/articulos/{a['id']}", json={"colores": [AZUL, ROJO]})
    assert [c["nombre"] for c in r.json()["colores"]] == ["Azul", "Rojo"]
    r = await admin.patch(f"/api/articulos/{a['id']}", json={"colores": []})
    assert r.json()["colores"] == []
    assert (await admin.get(f"/api/articulos/{a['id']}")).json()["colores"] == []


async def test_colores_validan_nombre_hex_y_repetidos(admin):
    base = {"nombre": "X", "precio_venta": 1000}
    for colores in (
        [{"nombre": "", "hex": "#000000"}],
        [{"nombre": "Rojo", "hex": "rojo"}],
        [{"nombre": "Rojo", "hex": "#12345"}],
        [ROJO, {"nombre": "  rojo ", "hex": "#000000"}],  # repetido sin importar mayúsculas
        [{"nombre": f"C{i}", "hex": "#000000"} for i in range(21)],
    ):
        r = await admin.post("/api/articulos", json={**base, "colores": colores})
        assert r.status_code == 422, colores


async def test_pedido_exige_color_valido_si_el_articulo_tiene(admin, publico):
    a = await crear_articulo(admin, colores=[ROJO, AZUL])
    sin = await publico.post("/api/publico/pedidos", json=pedido(a["id"]))
    assert sin.status_code == 422 and "color" in sin.json()["detail"].lower()
    malo = await publico.post("/api/publico/pedidos", json=pedido(a["id"], color="Verde"))
    assert malo.status_code == 422
    ok = await publico.post("/api/publico/pedidos", json=pedido(a["id"], color="azul"))
    assert ok.status_code == 201
    p = (await admin.get("/api/pedidos")).json()
    assert len(p) == 1 and p[0]["items"][0]["color"] == "Azul"  # queda con el nombre oficial


async def test_pedido_de_articulo_sin_colores_ignora_color(admin, publico):
    a = await crear_articulo(admin)
    r = await publico.post("/api/publico/pedidos", json=pedido(a["id"], color="Rojo"))
    assert r.status_code == 201
    assert (await admin.get("/api/pedidos")).json()[0]["items"][0]["color"] is None


async def test_cambiar_colores_no_rompe_pedidos_ya_hechos(admin, publico):
    a = await crear_articulo(admin, colores=[ROJO])
    await publico.post("/api/publico/pedidos", json=pedido(a["id"], color="Rojo"))
    await admin.patch(f"/api/articulos/{a['id']}", json={"colores": [AZUL]})
    assert (await admin.get("/api/pedidos")).json()[0]["items"][0]["color"] == "Rojo"


async def test_colores_requieren_sesion_para_editarse(admin, publico):
    a = await crear_articulo(admin)
    r = await publico.patch(f"/api/articulos/{a['id']}", json={"colores": [ROJO]})
    assert r.status_code == 401
