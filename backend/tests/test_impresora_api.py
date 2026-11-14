"""API de la impresora (estado, órdenes, trabajos) e importación de un trabajo como producción."""

from datetime import timedelta

from sqlalchemy import select

from app.core.tokens import ahora
from app.models import ComandoImpresora, EstadoImpresora, RegistroAuditoria, TrabajoImpresora
from tests.conftest import crear_articulo

DATOS = {
    "estado": "imprimiendo", "trabajo": "tfic-angled", "progreso": 50, "capa": 50, "capas": 100,
    "restante_min": 30, "boquilla": 220.0, "cama": 60.0, "velocidad": 2, "luz": "on", "ams": [],
}  # fmt: skip


async def poner_estado(db, datos=None, conectada=True, hace_s=0):
    fila = await db.get(EstadoImpresora, 1)
    if fila is None:
        fila = EstadoImpresora(id=1)
        db.add(fila)
    fila.conectada, fila.datos = conectada, {**DATOS, **(datos or {})}
    fila.actualizado_en = ahora() - timedelta(seconds=hace_s)
    await db.commit()


async def poner_trabajo(db, **kw):
    inicio = ahora() - timedelta(hours=3)
    base = dict(nombre="Soporte", tarea_id="1", estado="terminado", inicio_en=inicio,
                fin_en=inicio + timedelta(hours=2, minutes=30), progreso=100)  # fmt: skip
    t = TrabajoImpresora(**{**base, **kw})
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


# --------------------------------------------------------------------------- estado
async def test_sin_servicio_no_hay_datos(admin):
    j = (await admin.get("/api/impresora")).json()
    assert j["servicio_activo"] is False and j["conectada"] is False and j["datos"] is None


async def test_estado_con_latido_reciente(admin, db):
    await poner_estado(db)
    j = (await admin.get("/api/impresora")).json()
    assert j["servicio_activo"] and j["conectada"]
    assert j["datos"]["estado"] == "imprimiendo" and j["datos"]["progreso"] == 50


async def test_latido_viejo_significa_servicio_caido(admin, db):
    await poner_estado(db, hace_s=120)
    j = (await admin.get("/api/impresora")).json()
    assert j["servicio_activo"] is False and j["datos"] is None  # no se muestran datos viejos


async def test_impresora_apagada(admin, db):
    await poner_estado(db, conectada=False)
    j = (await admin.get("/api/impresora")).json()
    assert j["servicio_activo"] is True and j["conectada"] is False


async def test_todo_requiere_sesion(admin, publico, db):
    for ruta in ("/api/impresora", "/api/impresora/trabajos", "/api/impresora/comandos/1"):
        assert (await publico.get(ruta)).status_code == 401
    r = await publico.post("/api/impresora/comandos", json={"comando": "pausar"})
    assert r.status_code == 401


# -------------------------------------------------------------------------- órdenes
async def test_pausar_deja_una_orden_y_auditoria(admin, db):
    await poner_estado(db)
    r = await admin.post("/api/impresora/comandos", json={"comando": "pausar"})
    assert r.status_code == 202 and r.json()["estado"] == "pendiente"
    orden = (await db.execute(select(ComandoImpresora))).scalar_one()
    assert orden.comando == "pausar" and orden.usuario_id is not None
    acciones = (await db.execute(select(RegistroAuditoria.accion))).scalars().all()
    assert "impresora_orden" in acciones
    assert (await admin.get(f"/api/impresora/comandos/{orden.id}")).json()["estado"] == "pendiente"
    assert (await admin.get("/api/impresora/comandos/999999")).status_code == 404


async def test_ordenes_se_validan_contra_el_estado(admin, db):
    await poner_estado(db, {"estado": "imprimiendo"})
    r = await admin.post("/api/impresora/comandos", json={"comando": "reanudar"})
    assert r.status_code == 409 and "imprimiendo" in r.json()["detail"]
    await poner_estado(db, {"estado": "lista"})
    for c in ("pausar", "cancelar"):
        assert (await admin.post("/api/impresora/comandos", json={"comando": c})).status_code == 409
    await poner_estado(db, {"estado": "pausada"})
    assert (
        await admin.post("/api/impresora/comandos", json={"comando": "reanudar"})
    ).status_code == 202
    assert (
        await admin.post("/api/impresora/comandos", json={"comando": "cancelar"})
    ).status_code == 202


async def test_luz_funciona_en_cualquier_estado_y_valida_el_valor(admin, db):
    await poner_estado(db, {"estado": "lista"})
    assert (
        await admin.post("/api/impresora/comandos", json={"comando": "luz", "valor": "off"})
    ).status_code == 202
    for malo in (
        {"comando": "luz"},
        {"comando": "luz", "valor": "x"},
        {"comando": "velocidad", "valor": "9"},
        {"comando": "pausar", "valor": "1"},
        {"comando": "explotar"},
    ):
        assert (await admin.post("/api/impresora/comandos", json=malo)).status_code == 422, malo


async def test_velocidad_solo_imprimiendo(admin, db):
    await poner_estado(db, {"estado": "lista"})
    r = await admin.post("/api/impresora/comandos", json={"comando": "velocidad", "valor": "3"})
    assert r.status_code == 409
    await poner_estado(db, {"estado": "imprimiendo"})
    r = await admin.post("/api/impresora/comandos", json={"comando": "velocidad", "valor": "3"})
    assert r.status_code == 202


async def test_sin_conexion_no_se_aceptan_ordenes(admin, db):
    assert (
        await admin.post("/api/impresora/comandos", json={"comando": "luz", "valor": "on"})
    ).status_code == 409
    await poner_estado(db, conectada=False)
    assert (
        await admin.post("/api/impresora/comandos", json={"comando": "luz", "valor": "on"})
    ).status_code == 409
    await poner_estado(db, hace_s=120)
    assert (
        await admin.post("/api/impresora/comandos", json={"comando": "luz", "valor": "on"})
    ).status_code == 409
    assert (await db.execute(select(ComandoImpresora))).first() is None


async def test_doble_clic_no_duplica_la_orden(admin, db):
    await poner_estado(db)
    a = await admin.post("/api/impresora/comandos", json={"comando": "pausar"})
    b = await admin.post("/api/impresora/comandos", json={"comando": "pausar"})
    assert a.json()["id"] == b.json()["id"]
    assert len((await db.execute(select(ComandoImpresora))).scalars().all()) == 1


# -------------------------------------------------------------------------- trabajos
async def test_lista_de_trabajos_con_tiempo_medido_o_estimado(admin, db):
    await poner_trabajo(db, nombre="Medido", minutos_estimados=999, gramos_total=12.5,
                        filamentos=[{"tipo": "PLA", "color": "#f00", "gramos": 12.5}])  # fmt: skip
    await poner_trabajo(db, nombre="Estimado", inicio_observado=False, minutos_estimados=95)
    j = {t["nombre"]: t for t in (await admin.get("/api/impresora/trabajos")).json()}
    assert j["Medido"]["minutos"] == 150 and j["Medido"]["minutos_origen"] == "medido"
    assert j["Medido"]["gramos_total"] == 12.5 and j["Medido"]["filamentos"][0]["color"] == "#f00"
    assert j["Estimado"]["minutos"] == 95 and j["Estimado"]["minutos_origen"] == "estimado"
    assert j["Estimado"]["gramos_total"] is None


async def test_pendientes_cuentan_solo_los_terminados(admin, db):
    await poner_trabajo(db, nombre="A")
    await poner_trabajo(db, nombre="B", estado="interrumpido")
    await poner_trabajo(db, nombre="C", estado="en_curso", fin_en=None)
    assert (await admin.get("/api/impresora")).json()["trabajos_pendientes"] == 2
    nombres = {t["nombre"] for t in (await admin.get("/api/impresora/trabajos")).json()}
    assert nombres == {"A", "B", "C"}  # el que sigue en curso se ve, pero no se puede importar


async def test_ignorar_y_restaurar(admin, db):
    t = await poner_trabajo(db)
    r = await admin.post(f"/api/impresora/trabajos/{t.id}/ignorar")
    assert r.status_code == 200 and r.json()["gestion"] == "ignorado"
    assert (await admin.get("/api/impresora/trabajos")).json() == []
    assert len((await admin.get("/api/impresora/trabajos?gestion=ignorado")).json()) == 1
    assert (await admin.post(f"/api/impresora/trabajos/{t.id}/ignorar")).status_code == 409
    assert (await admin.post(f"/api/impresora/trabajos/{t.id}/restaurar")).json()[
        "gestion"
    ] == "pendiente"
    en_curso = await poner_trabajo(db, estado="en_curso", fin_en=None)
    assert (await admin.post(f"/api/impresora/trabajos/{en_curso.id}/ignorar")).status_code == 409
    assert (
        await admin.post("/api/impresora/trabajos/00000000-0000-0000-0000-000000000000/ignorar")
    ).status_code == 404


# ------------------------------------------------------------- importar como producción
def lote(articulo_id, trabajo_id, **extra):
    return {"items": [{"articulo_id": articulo_id, "cantidad": 3}], "trabajo_id": str(trabajo_id),
            "gramos_total": 12.5, "minutos_impresion": 150, **extra}  # fmt: skip


async def test_importar_trabajo_crea_el_lote_y_lo_vincula(admin, db):
    a = await crear_articulo(admin)
    t = await poner_trabajo(db, nombre="Soporte v2")
    r = await admin.post("/api/produccion", json=lote(a["id"], t.id))
    assert r.status_code == 201, r.text
    j = r.json()
    assert (
        j["desde_impresora"] == "Soporte v2"
        and j["gramos_total"] == 12.5
        and j["minutos_impresion"] == 150
    )
    await db.refresh(t)
    assert t.gestion == "importado" and str(t.produccion_id) == j["id"]
    assert (await admin.get("/api/impresora")).json()["trabajos_pendientes"] == 0
    assert (await admin.get("/api/produccion")).json()[0]["desde_impresora"] == "Soporte v2"
    assert (await admin.get("/api/impresora/trabajos?gestion=importado")).json()[0][
        "produccion_id"
    ] == j["id"]


async def test_un_trabajo_no_se_importa_dos_veces(admin, db):
    a = await crear_articulo(admin)
    t = await poner_trabajo(db)
    assert (await admin.post("/api/produccion", json=lote(a["id"], t.id))).status_code == 201
    r = await admin.post("/api/produccion", json=lote(a["id"], t.id))
    assert r.status_code == 409 and "ya se importó" in r.json()["detail"]
    assert (await admin.get(f"/api/articulos/{a['id']}")).json()[
        "stock"
    ] == 3  # no se sumó dos veces


async def test_no_se_importa_en_curso_ignorado_ni_inexistente(admin, db):
    a = await crear_articulo(admin)
    en_curso = await poner_trabajo(db, estado="en_curso", fin_en=None)
    ignorado = await poner_trabajo(db, gestion="ignorado")
    for t, codigo in ((en_curso, 409), (ignorado, 409)):
        assert (await admin.post("/api/produccion", json=lote(a["id"], t.id))).status_code == codigo
    r = await admin.post(
        "/api/produccion", json=lote(a["id"], "00000000-0000-0000-0000-000000000000")
    )
    assert r.status_code == 422
    assert (await admin.get(f"/api/articulos/{a['id']}")).json()["stock"] == 0


async def test_si_el_lote_falla_el_trabajo_sigue_pendiente(admin, db):
    t = await poner_trabajo(db)
    malo = lote("00000000-0000-0000-0000-000000000000", t.id)  # artículo inexistente
    assert (await admin.post("/api/produccion", json=malo)).status_code == 422
    await db.refresh(t)
    assert t.gestion == "pendiente" and t.produccion_id is None


async def test_editar_el_lote_no_toca_el_vinculo(admin, db):
    a = await crear_articulo(admin)
    t = await poner_trabajo(db)
    j = (await admin.post("/api/produccion", json=lote(a["id"], t.id))).json()
    r = await admin.put(f"/api/produccion/{j['id']}", json=lote(a["id"], t.id, nota="corregido"))
    assert (
        r.status_code == 200
        and r.json()["desde_impresora"] == "Soporte"
        and r.json()["nota"] == "corregido"
    )
