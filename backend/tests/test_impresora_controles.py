"""Temperaturas y ventiladores: lo que se envía a la impresora y los límites de seguridad."""

import pytest
from sqlalchemy import select

from app.impresora import bambu
from app.models import ComandoImpresora, RegistroAuditoria
from tests.test_impresora_api import poner_estado
from tests.test_impresora_servicio import FalsoCliente


def gcode(comando, valor):
    orden = bambu.construir_orden(comando, valor)["print"]
    assert orden["command"] == "gcode_line" and orden["param"].endswith("\n")
    return orden["param"]


# ------------------------------------------------------------------------------ protocolo
def test_gcode_de_temperaturas():
    assert gcode("temp_boquilla", "220") == "M104 S220\n"
    assert gcode("temp_boquilla", "0") == "M104 S0\n"  # apagar
    assert gcode("temp_cama", "60") == "M140 S60\n"
    assert gcode("temp_cama", "0") == "M140 S0\n"


def test_gcode_de_ventiladores_convierte_porcentaje_a_0_255():
    assert gcode("ventilador_pieza", "100") == "M106 P1 S255\n"
    assert gcode("ventilador_pieza", "0") == "M106 P1 S0\n"
    assert gcode("ventilador_pieza", "50") == "M106 P1 S128\n"
    assert gcode("ventilador_aux", "100") == "M106 P2 S255\n"
    assert gcode("ventilador_aux", "30") == "M106 P2 S77\n"


@pytest.mark.parametrize(
    ("comando", "valor"),
    [
        ("temp_boquilla", "301"), ("temp_boquilla", "100"), ("temp_boquilla", "149"),
        ("temp_boquilla", "-5"), ("temp_cama", "101"), ("temp_cama", "-1"),
        ("ventilador_pieza", "101"), ("ventilador_aux", "-10"), ("temp_cama", "abc"),
        ("temp_cama", ""), ("temp_cama", None), ("temp_cama", "60; M112"),
        ("temp_boquilla", "2e2"), ("ventilador_pieza", "5.5"),
    ],
)  # fmt: skip
def test_valores_fuera_de_limite_o_raros_se_rechazan(comando, valor):
    with pytest.raises(ValueError):
        bambu.construir_orden(comando, valor)


def test_limites_validos_en_los_bordes():
    assert bambu.validar_numero("temp_boquilla", "150") == 150
    assert bambu.validar_numero("temp_boquilla", "300") == 300
    assert bambu.validar_numero("temp_cama", "100") == 100
    assert bambu.validar_numero("ventilador_aux", " 40 ") == 40


def test_los_ventiladores_se_muestran_en_porcentaje():
    n = bambu.normalizar({"cooling_fan_speed": "10", "big_fan1_speed": "15", "big_fan2_speed": "0"})
    assert (n["ventilador_pieza"], n["ventilador_aux"]) == (67, 100)
    n = bambu.normalizar({"cooling_fan_speed": "0", "big_fan1_speed": "x"})
    assert (n["ventilador_pieza"], n["ventilador_aux"]) == (0, None)
    assert bambu.normalizar({})["ventilador_pieza"] is None


# ------------------------------------------------------------------------------------ API
async def test_ordenes_numericas_se_encolan_con_auditoria(admin, db):
    await poner_estado(db, {"estado": "lista"})
    for comando, valor in (("temp_boquilla", "200"), ("temp_cama", "60"),
                           ("ventilador_pieza", "80"), ("ventilador_aux", "0")):  # fmt: skip
        r = await admin.post("/api/impresora/comandos", json={"comando": comando, "valor": valor})
        assert r.status_code == 202, (comando, r.text)
    ordenes = (
        (await db.execute(select(ComandoImpresora).order_by(ComandoImpresora.id))).scalars().all()
    )
    assert [(o.comando, o.valor) for o in ordenes] == [
        ("temp_boquilla", "200"), ("temp_cama", "60"),
        ("ventilador_pieza", "80"), ("ventilador_aux", "0"),
    ]  # fmt: skip
    acciones = [a for (a,) in (await db.execute(select(RegistroAuditoria.accion))).all()]
    assert acciones.count("impresora_orden") == 4


async def test_la_api_rechaza_valores_peligrosos_sin_encolar(admin, db):
    await poner_estado(db, {"estado": "lista"})
    for comando, valor in (("temp_boquilla", "400"), ("temp_boquilla", "100"), ("temp_cama", "150"),
                           ("ventilador_pieza", "200"), ("temp_cama", None), ("temp_cama", "x"),
                           ("temp_cama", "60 M112")):  # fmt: skip
        r = await admin.post("/api/impresora/comandos", json={"comando": comando, "valor": valor})
        assert r.status_code == 422, (comando, valor)
    assert (await db.execute(select(ComandoImpresora))).first() is None


async def test_temperaturas_y_ventiladores_requieren_conexion_y_sesion(admin, publico, db):
    cuerpo = {"comando": "temp_cama", "valor": "60"}
    assert (await publico.post("/api/impresora/comandos", json=cuerpo)).status_code == 401
    assert (
        await admin.post("/api/impresora/comandos", json=cuerpo)
    ).status_code == 409  # sin servicio
    await poner_estado(db, conectada=False)
    assert (await admin.post("/api/impresora/comandos", json=cuerpo)).status_code == 409


async def test_los_datos_incluyen_los_ventiladores(admin, db):
    await poner_estado(db, {"ventilador_pieza": 67, "ventilador_aux": 100})
    d = (await admin.get("/api/impresora")).json()["datos"]
    assert (d["ventilador_pieza"], d["ventilador_aux"]) == (67, 100)


# -------------------------------------------------------------------------------- servicio
async def test_el_servicio_envia_las_ordenes_numericas(db):
    from app.impresora.servicio import Servicio

    cliente = FalsoCliente()
    servicio = Servicio(cliente)
    db.add_all([ComandoImpresora(comando="temp_boquilla", valor="210"),
                ComandoImpresora(comando="ventilador_pieza", valor="40")])  # fmt: skip
    await db.commit()
    await servicio._atender_ordenes()
    assert cliente.enviadas == [("temp_boquilla", "210"), ("ventilador_pieza", "40")]
    db.expire_all()
    estados = {o.comando: o.estado for o in (await db.execute(select(ComandoImpresora))).scalars()}
    assert estados == {"temp_boquilla": "enviado", "ventilador_pieza": "enviado"}


# ----------------------------------------------------------------- releer el chip RFID de una ranura
AMS = [
    {"id": str(i), "vacia": False, "tipo": "PLA", "color": "#ff0000", "tag": None,
     "medido": False, "restante": None, "en_uso": False}
    for i in range(4)
]  # fmt: skip


def test_releer_el_chip_manda_lo_mismo_que_bambu_studio():
    assert gcode("leer_rfid", "0") == "M620 R0\n"
    assert gcode("leer_rfid", "3") == "M620 R3\n"
    assert gcode("leer_rfid", " 5 ") == "M620 R5\n"


@pytest.mark.parametrize("valor", [None, "", "x", "-1", "16", "1.5", "2; M112", "1e1"])
def test_releer_el_chip_rechaza_ranuras_raras(valor):
    with pytest.raises(ValueError):
        bambu.construir_orden("leer_rfid", valor)


def test_el_estado_informa_si_hay_filamento_en_el_cabezal():
    assert bambu.normalizar({"hw_switch_state": 1})["en_extrusor"] is True
    assert bambu.normalizar({"hw_switch_state": "0"})["en_extrusor"] is False
    assert bambu.normalizar({})["en_extrusor"] is None


async def test_releer_el_chip_se_encola_con_la_impresora_quieta(admin, db):
    await poner_estado(db, {"estado": "lista", "ams": AMS, "en_extrusor": False})
    r = await admin.post("/api/impresora/comandos", json={"comando": "leer_rfid", "valor": "2"})
    assert r.status_code == 202, r.text
    (o,) = (await db.execute(select(ComandoImpresora))).scalars().all()
    assert (o.comando, o.valor) == ("leer_rfid", "2")


async def test_releer_el_chip_se_permite_si_la_impresora_no_informa_el_cabezal(admin, db):
    await poner_estado(db, {"estado": "lista", "ams": AMS})  # sin «en_extrusor»
    r = await admin.post("/api/impresora/comandos", json={"comando": "leer_rfid", "valor": "0"})
    assert r.status_code == 202, r.text


async def test_releer_el_chip_se_rechaza_si_algo_lo_impide(admin, db):
    async def intentar(valor="1"):
        return await admin.post("/api/impresora/comandos", json={"comando": "leer_rfid", "valor": valor})

    await poner_estado(db, {"estado": "imprimiendo", "ams": AMS})
    assert (await intentar()).status_code == 409  # imprimiendo: el AMS está trabajando
    await poner_estado(db, {"estado": "lista", "ams": AMS, "en_extrusor": True})
    r = await intentar()
    assert r.status_code == 409 and "cabezal" in r.json()["detail"]
    await poner_estado(db, {"estado": "lista", "ams": AMS, "en_extrusor": False})
    assert (await intentar("9")).status_code == 409  # esa ranura no existe
    assert (await intentar("99")).status_code == 422
    assert (await intentar("x")).status_code == 422
    assert (await db.execute(select(ComandoImpresora))).first() is None


async def test_el_servicio_envia_la_orden_de_releer_el_chip(db):
    from app.impresora.servicio import Servicio

    cliente = FalsoCliente()
    servicio = Servicio(cliente)
    db.add(ComandoImpresora(comando="leer_rfid", valor="1"))
    await db.commit()
    await servicio._atender_ordenes()
    assert cliente.enviadas == [("leer_rfid", "1")]
