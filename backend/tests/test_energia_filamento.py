"""Producción con filamento (total o por filamento), tiempo de impresión y parámetros de energía."""

from tests.conftest import crear_articulo


async def lote(c, articulo_id, **extra):
    return await c.post(
        "/api/produccion", json={"items": [{"articulo_id": articulo_id, "cantidad": 2}], **extra}
    )


async def test_lote_sin_filamento_ni_tiempo_sigue_funcionando(admin):
    a = await crear_articulo(admin)
    r = await lote(admin, a["id"])
    assert r.status_code == 201
    j = r.json()
    assert j["gramos_total"] is None and j["minutos_impresion"] is None and j["kwh"] is None
    assert j["filamentos"] == []


async def test_gramos_totales_directos_y_tiempo(admin):
    a = await crear_articulo(admin)
    j = (await lote(admin, a["id"], gramos_total=187.5, minutos_impresion=200)).json()
    assert j["gramos_total"] == 187.5 and j["minutos_impresion"] == 200 and j["filamentos"] == []


async def test_por_filamento_el_total_es_la_suma(admin):
    a = await crear_articulo(admin)
    fil = [{"descripcion": "PLA negro", "gramos": 120}, {"descripcion": "PLA rojo", "gramos": 30.5}]
    j = (await lote(admin, a["id"], filamentos=fil)).json()
    assert j["gramos_total"] == 150.5
    assert [(f["descripcion"], f["gramos"]) for f in j["filamentos"]] == [
        ("PLA negro", 120),
        ("PLA rojo", 30.5),
    ]


async def test_total_y_filamentos_deben_cuadrar(admin):
    a = await crear_articulo(admin)
    fil = [{"descripcion": "PLA", "gramos": 100}, {"descripcion": "PETG", "gramos": 50}]
    mal = await lote(admin, a["id"], gramos_total=200, filamentos=fil)
    assert mal.status_code == 422 and "no coincide" in mal.json()["detail"]
    bien = await lote(admin, a["id"], gramos_total=150, filamentos=fil)
    assert bien.status_code == 201 and bien.json()["gramos_total"] == 150
    # Un lote rechazado no deja stock a medias.
    assert (await admin.get(f"/api/articulos/{a['id']}")).json()["stock"] == 2


async def test_validaciones_de_filamento_y_tiempo(admin):
    a = await crear_articulo(admin)
    for extra in (
        {"gramos_total": 0}, {"gramos_total": -5}, {"minutos_impresion": 0},
        {"minutos_impresion": 60 * 24 * 31}, {"filamentos": [{"descripcion": "x", "gramos": 0}]},
        {"filamentos": [{"descripcion": "x", "gramos": 1}] * 21}, {"kwh": 5},
    ):  # fmt: skip
        assert (await lote(admin, a["id"], **extra)).status_code == 422, extra


async def test_parametros_se_guardan_y_validan(admin):
    assert (await admin.get("/api/parametros")).json() == {
        "precio_kwh": None,
        "potencia_impresora_w": None,
    }
    r = await admin.put("/api/parametros", json={"precio_kwh": 850, "potencia_impresora_w": 220})
    assert r.status_code == 200 and r.json() == {"precio_kwh": 850, "potencia_impresora_w": 220}
    assert (await admin.get("/api/parametros")).json()["precio_kwh"] == 850
    for malo in (
        {"precio_kwh": -1},
        {"potencia_impresora_w": 0},
        {"potencia_impresora_w": 99999},
        {"x": 1},
    ):
        assert (await admin.put("/api/parametros", json=malo)).status_code == 422, malo


async def test_los_parametros_exigen_sesion_y_cabecera(publico, admin):
    assert (await publico.get("/api/parametros")).status_code == 401
    assert (await publico.put("/api/parametros", json={"precio_kwh": 1})).status_code == 401
    sin = await admin.put(
        "/api/parametros", json={"precio_kwh": 1}, headers={"X-Requested-With": ""}
    )
    assert sin.status_code == 403


async def test_energia_del_lote_y_se_congela(admin):
    a = await crear_articulo(admin)
    await admin.put("/api/parametros", json={"precio_kwh": 800, "potencia_impresora_w": 200})
    # 200 W durante 2 h 30 min = 0,5 kWh → 0,5 × 800 = 400
    j = (await lote(admin, a["id"], minutos_impresion=150)).json()
    assert (
        j["kwh"] == 0.5
        and j["costo_energia"] == 400
        and j["potencia_w"] == 200
        and j["precio_kwh"] == 800
    )

    # Cambiar los parámetros NO reescribe el lote ya registrado…
    await admin.put("/api/parametros", json={"precio_kwh": 1200, "potencia_impresora_w": 300})
    viejo = (await admin.get("/api/produccion")).json()[0]
    assert viejo["kwh"] == 0.5 and viejo["costo_energia"] == 400 and viejo["precio_kwh"] == 800
    # …y los lotes nuevos usan los nuevos: 300 W × 1 h = 0,3 kWh → 360
    nuevo = (await lote(admin, a["id"], minutos_impresion=60)).json()
    assert nuevo["kwh"] == 0.3 and nuevo["costo_energia"] == 360


async def test_sin_potencia_no_hay_kwh_y_sin_precio_no_hay_costo(admin):
    a = await crear_articulo(admin)
    j = (await lote(admin, a["id"], minutos_impresion=90)).json()
    assert j["kwh"] is None and j["costo_energia"] is None  # sin parámetros
    await admin.put("/api/parametros", json={"potencia_impresora_w": 240})
    j = (await lote(admin, a["id"], minutos_impresion=90)).json()
    assert j["kwh"] == 0.36 and j["costo_energia"] is None  # hay kWh pero no precio del kWh


async def test_el_cambio_de_parametros_queda_auditado(admin, db):
    from sqlalchemy import select

    from app.models import RegistroAuditoria

    await admin.put("/api/parametros", json={"precio_kwh": 900, "potencia_impresora_w": 250})
    fila = (
        await db.execute(
            select(RegistroAuditoria).where(RegistroAuditoria.accion == "parametros_cambiados")
        )
    ).scalar_one()
    assert fila.detalle["despues"] == {"precio_kwh": 900.0, "potencia_w": 250.0}


# --- Carga retrospectiva ------------------------------------------------------------------
async def test_lote_con_fecha_pasada_ordena_por_fecha_de_produccion(admin):
    from datetime import date, timedelta

    a = await crear_articulo(admin)
    hace_2_anios = (date.today() - timedelta(days=730)).isoformat()
    hace_40_dias = (date.today() - timedelta(days=40)).isoformat()
    for f in (hace_40_dias, hace_2_anios):
        assert (await lote(admin, a["id"], fecha=f)).status_code == 201
    await lote(admin, a["id"])  # hoy
    fechas = [x["fecha"] for x in (await admin.get("/api/produccion")).json()]
    assert fechas == sorted(fechas, reverse=True) and fechas[-1] == hace_2_anios


async def test_limites_de_fecha_de_produccion(admin):
    from datetime import date, timedelta

    a = await crear_articulo(admin)
    futura = (date.today() + timedelta(days=1)).isoformat()
    muy_vieja = (date.today() - timedelta(days=6 * 366)).isoformat()
    assert (await lote(admin, a["id"], fecha=futura)).status_code == 422
    r = await lote(admin, a["id"], fecha=muy_vieja)
    assert r.status_code == 422 and "5 años" in r.json()["detail"]
    assert (await lote(admin, a["id"], fecha="no-es-fecha")).status_code == 422


async def test_carga_historica_no_suma_al_inventario_de_hoy(admin):
    from datetime import date, timedelta

    a = await crear_articulo(admin)
    vieja = (date.today() - timedelta(days=200)).isoformat()
    r = await lote(admin, a["id"], fecha=vieja, afecta_inventario=False, gramos_total=100)
    assert r.status_code == 201 and r.json()["afecta_inventario"] is False
    assert (await admin.get(f"/api/articulos/{a['id']}")).json()["stock"] == 0
    movs = (await admin.get(f"/api/inventario/movimientos?articulo_id={a['id']}")).json()
    assert movs == []  # sin movimiento: el kardex tampoco cambia
    # …pero queda en el historial con sus datos (para métricas).
    hist = (await admin.get("/api/produccion")).json()
    assert (
        hist[0]["fecha"] == vieja
        and hist[0]["gramos_total"] == 100
        and hist[0]["items"][0]["cantidad"] == 2
    )
    # Y un lote retrospectivo que SÍ afecta suma al stock actual.
    assert (await lote(admin, a["id"], fecha=vieja)).status_code == 201
    assert (await admin.get(f"/api/articulos/{a['id']}")).json()["stock"] == 2


async def test_lote_viejo_con_su_propia_energia(admin):
    a = await crear_articulo(admin)
    await admin.put("/api/parametros", json={"precio_kwh": 900, "potencia_impresora_w": 300})
    # Con los valores de ese lote (no los de hoy): 150 W × 2 h = 0,3 kWh × 600 = 180
    j = (await lote(admin, a["id"], minutos_impresion=120, potencia_w=150, precio_kwh=600)).json()
    assert (
        j["kwh"] == 0.3
        and j["costo_energia"] == 180
        and j["potencia_w"] == 150
        and j["precio_kwh"] == 600
    )
    # Sin sobrescribir, usa los de hoy: 300 W × 2 h = 0,6 kWh × 900 = 540
    j = (await lote(admin, a["id"], minutos_impresion=120)).json()
    assert j["kwh"] == 0.6 and j["costo_energia"] == 540
    for malo in ({"potencia_w": 0}, {"precio_kwh": -1}, {"potencia_w": 99999}):
        assert (await lote(admin, a["id"], minutos_impresion=60, **malo)).status_code == 422
