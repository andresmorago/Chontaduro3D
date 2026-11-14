"""Editar un lote ya guardado: el inventario se ajusta solo por la diferencia."""

from sqlalchemy import func, select

from app.models import MovimientoInventario
from tests.conftest import crear_articulo, stock


async def lote(c, items, **extra):
    r = await c.post(
        "/api/produccion",
        json={"items": [{"articulo_id": a, "cantidad": n} for a, n in items], **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def editar(c, lote_id, items, **extra):
    return await c.put(
        f"/api/produccion/{lote_id}",
        json={"items": [{"articulo_id": a, "cantidad": n} for a, n in items], **extra},
    )


async def test_subir_la_cantidad_suma_solo_la_diferencia(admin, db):
    a = await crear_articulo(admin)
    p = await lote(admin, [(a["id"], 5)])
    r = await editar(admin, p["id"], [(a["id"], 8)])
    assert r.status_code == 200 and r.json()["items"][0]["cantidad"] == 8
    assert await stock(admin, a["id"]) == 8
    tipos = (await db.execute(select(MovimientoInventario.tipo, MovimientoInventario.cantidad)
                              .order_by(MovimientoInventario.id))).all()  # fmt: skip
    assert [tuple(t) for t in tipos] == [
        ("produccion", 5),
        ("ajuste", 3),
    ]  # el alta no se reescribe


async def test_bajar_la_cantidad_resta(admin):
    a = await crear_articulo(admin)
    p = await lote(admin, [(a["id"], 5)])
    assert (await editar(admin, p["id"], [(a["id"], 2)])).status_code == 200
    assert await stock(admin, a["id"]) == 2


async def test_no_se_puede_bajar_por_debajo_de_lo_ya_vendido(admin):
    a = await crear_articulo(admin)
    p = await lote(admin, [(a["id"], 5)])
    v = await admin.post("/api/ventas", json={"items": [{"articulo_id": a["id"], "cantidad": 4}]})
    assert v.status_code == 201
    r = await editar(admin, p["id"], [(a["id"], 2)])  # quedaría en -2
    assert r.status_code == 409 and "ya salió" in r.json()["detail"]
    assert await stock(admin, a["id"]) == 1  # nada cambió
    assert (await editar(admin, p["id"], [(a["id"], 4)])).status_code == 200  # justo lo vendido
    assert await stock(admin, a["id"]) == 0


async def test_cambiar_el_articulo_del_lote(admin):
    a = await crear_articulo(admin, nombre="Llavero")
    b = await crear_articulo(admin, nombre="Soporte")
    p = await lote(admin, [(a["id"], 3)])
    r = await editar(admin, p["id"], [(b["id"], 4)])
    assert r.status_code == 200 and [i["nombre"] for i in r.json()["items"]] == ["Soporte"]
    assert await stock(admin, a["id"]) == 0 and await stock(admin, b["id"]) == 4


async def test_pasar_a_solo_historial_y_volver(admin):
    a = await crear_articulo(admin)
    p = await lote(admin, [(a["id"], 5)])
    r = await editar(admin, p["id"], [(a["id"], 5)], afecta_inventario=False)
    assert r.status_code == 200 and r.json()["afecta_inventario"] is False
    assert await stock(admin, a["id"]) == 0
    r = await editar(admin, p["id"], [(a["id"], 6)], afecta_inventario=True)
    assert r.status_code == 200 and await stock(admin, a["id"]) == 6


async def test_editar_dos_veces_acumula_bien(admin):
    a = await crear_articulo(admin)
    p = await lote(admin, [(a["id"], 5)])
    await editar(admin, p["id"], [(a["id"], 7)])
    await editar(admin, p["id"], [(a["id"], 3)])
    assert await stock(admin, a["id"]) == 3


async def test_sin_cambios_no_genera_movimientos(admin, db):
    a = await crear_articulo(admin)
    p = await lote(admin, [(a["id"], 5)], nota="hola")
    await editar(admin, p["id"], [(a["id"], 5)], nota="otra nota")
    n = (await db.execute(select(func.count()).select_from(MovimientoInventario))).scalar_one()
    assert n == 1
    assert (await admin.get("/api/produccion")).json()[0]["nota"] == "otra nota"


async def test_editar_fecha_filamento_y_tiempo(admin):
    a = await crear_articulo(admin)
    p = await lote(admin, [(a["id"], 2)], gramos_total=100)
    fil = [{"descripcion": "PLA negro", "gramos": 80}, {"descripcion": "PLA rojo", "gramos": 20}]
    r = await editar(admin, p["id"], [(a["id"], 2)], fecha="2026-01-15", filamentos=fil,
                     minutos_impresion=120)  # fmt: skip
    j = r.json()
    assert r.status_code == 200 and j["fecha"] == "2026-01-15"
    assert j["gramos_total"] == 100 and len(j["filamentos"]) == 2 and j["minutos_impresion"] == 120
    # Se pueden quitar: omitirlos los borra.
    j = (await editar(admin, p["id"], [(a["id"], 2)])).json()
    assert j["gramos_total"] is None and j["filamentos"] == [] and j["minutos_impresion"] is None
    assert j["kwh"] is None


async def test_la_energia_congelada_se_conserva_al_editar(admin):
    a = await crear_articulo(admin)
    await admin.put("/api/parametros", json={"precio_kwh": 1000, "potencia_impresora_w": 200})
    p = await lote(admin, [(a["id"], 1)], minutos_impresion=60)
    assert p["kwh"] == 0.2 and p["costo_energia"] == 200
    # Cambian los parámetros de hoy: el lote editado NO los toma.
    await admin.put("/api/parametros", json={"precio_kwh": 5000, "potencia_impresora_w": 500})
    j = (await editar(admin, p["id"], [(a["id"], 1)], minutos_impresion=120)).json()
    assert j["potencia_w"] == 200 and j["precio_kwh"] == 1000
    assert j["kwh"] == 0.4 and j["costo_energia"] == 400
    # …salvo que se indiquen valores propios.
    j = (await editar(admin, p["id"], [(a["id"], 1)], minutos_impresion=60, precio_kwh=2000)).json()
    assert j["precio_kwh"] == 2000 and j["costo_energia"] == 400


async def test_validaciones_al_editar(admin):
    a = await crear_articulo(admin)
    p = await lote(admin, [(a["id"], 2)])
    item = [(a["id"], 2)]
    assert (await editar(admin, p["id"], item, fecha="2999-01-01")).status_code == 422
    assert (await editar(admin, p["id"], item, fecha="1999-01-01")).status_code == 422
    assert (await editar(admin, p["id"], [])).status_code == 422
    assert (await editar(admin, p["id"], [("00000000-0000-0000-0000-000000000000", 1)])
            ).status_code == 422  # fmt: skip
    fil = [{"descripcion": "PLA", "gramos": 10}]
    assert (await editar(admin, p["id"], item, gramos_total=99, filamentos=fil)).status_code == 422
    assert (await editar(admin, "00000000-0000-0000-0000-000000000000", item)).status_code == 404
    assert await stock(admin, a["id"]) == 2


async def test_articulo_archivado_puede_seguir_en_su_lote_pero_no_entrar_a_otro(admin):
    a = await crear_articulo(admin, nombre="Viejo")
    b = await crear_articulo(admin, nombre="Otro")
    p = await lote(admin, [(a["id"], 2)])
    q = await lote(admin, [(b["id"], 1)])
    await admin.patch(f"/api/articulos/{a['id']}", json={"activo": False})
    assert (await editar(admin, p["id"], [(a["id"], 2)], nota="x")).status_code == 200
    assert (await editar(admin, q["id"], [(a["id"], 1)])).status_code == 422


async def test_editar_requiere_sesion_y_deja_auditoria(admin, publico, db):
    a = await crear_articulo(admin)
    p = await lote(admin, [(a["id"], 2)])
    r = await publico.put(
        f"/api/produccion/{p['id']}", json={"items": [{"articulo_id": a["id"], "cantidad": 3}]}
    )
    assert r.status_code == 401
    await editar(admin, p["id"], [(a["id"], 3)])
    from app.models import RegistroAuditoria

    acciones = (await db.execute(select(RegistroAuditoria.accion))).scalars().all()
    assert "produccion_modificada" in acciones
