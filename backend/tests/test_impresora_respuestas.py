"""Lo que la impresora contesta (o avisa) cuando la app le manda una orden."""

from sqlalchemy import select

from app.models import ComandoImpresora


# ---------------------------------------------------- la respuesta de la impresora a la orden
def _cliente_bambu():
    import threading
    from collections import deque

    from app.impresora.bambu import ClienteBambu

    c = ClienteBambu.__new__(ClienteBambu)  # sin abrir ninguna conexión MQTT
    c._lock = threading.Lock()
    c._estado, c._ultimo, c._respuestas = {}, None, deque(maxlen=20)
    return c


class _Mensaje:
    def __init__(self, print_):
        import json

        self.payload = json.dumps({"print": print_})


def test_el_cliente_guarda_las_respuestas_a_las_ordenes_y_no_los_reportes():
    import time

    c = _cliente_bambu()
    desde = time.monotonic()
    c._al_mensaje(None, None, _Mensaje({"gcode_state": "IDLE", "mc_percent": 0}))  # un reporte
    assert c.esperar_respuesta("pause", desde, 0) is None
    c._al_mensaje(None, None, _Mensaje(
        {"command": "pause", "result": "fail", "reason": "mqtt message verify failed"}
    ))  # fmt: skip
    r = c.esperar_respuesta("pause", desde, 0)
    assert (r["result"], r["reason"]) == ("fail", "mqtt message verify failed")
    assert c.esperar_respuesta("pause", time.monotonic() + 1, 0) is None  # una respuesta vieja no vale


async def test_si_la_impresora_rechaza_la_orden_se_ve_el_motivo(db):
    from app.impresora.servicio import Servicio
    from tests.test_impresora_servicio import FalsoCliente

    class Rechaza(FalsoCliente):
        def esperar_respuesta(self, comando, desde, espera_s=4.0):
            assert comando == "pause"
            return {"comando": comando, "result": "fail", "reason": "tray is busy", "en": 0}

    servicio = Servicio(Rechaza())
    db.add(ComandoImpresora(comando="pausar"))
    await db.commit()
    await servicio._atender_ordenes()
    db.expire_all()
    (o,) = (await db.execute(select(ComandoImpresora))).scalars().all()
    assert o.estado == "fallido" and "tray is busy" in o.detalle


async def test_si_la_impresora_acepta_la_orden_queda_enviada(db):
    from app.impresora.servicio import Servicio
    from tests.test_impresora_servicio import FalsoCliente

    class Acepta(FalsoCliente):
        def esperar_respuesta(self, comando, desde, espera_s=4.0):
            return {"comando": comando, "result": "success", "reason": "", "en": 0}

    servicio = Servicio(Acepta())
    db.add(ComandoImpresora(comando="pausar"))
    await db.commit()
    await servicio._atender_ordenes()
    db.expire_all()
    (o,) = (await db.execute(select(ComandoImpresora))).scalars().all()
    assert o.estado == "enviado" and o.detalle is None


def test_se_detecta_el_aviso_de_verificacion_rechazada():
    c = _cliente_bambu()
    assert c.verificacion_rechazada() is False
    c._estado = {"hms": [{"attr": 0x05000500, "code": 0x00010007}]}
    assert c.verificacion_rechazada() is True
    c._estado = {"hms": [{"attr": 0x07000100, "code": 0x00010007}]}  # otro aviso
    assert c.verificacion_rechazada() is False


async def test_si_aparece_el_aviso_de_verificacion_la_orden_falla_con_una_explicacion(db):
    from app.impresora.servicio import Servicio
    from tests.test_impresora_servicio import FalsoCliente

    class Firmado(FalsoCliente):
        rechazada = False

        def enviar(self, comando, valor=None):
            self.rechazada = True  # tras la orden, la impresora muestra el aviso
            return super().enviar(comando, valor)

        def esperar_respuesta(self, comando, desde, espera_s=4.0):
            return None  # no contesta: solo muestra el aviso

        def verificacion_rechazada(self):
            return self.rechazada

    servicio = Servicio(Firmado())
    db.add(ComandoImpresora(comando="pausar"))
    await db.commit()
    await servicio._atender_ordenes()
    db.expire_all()
    (o,) = (await db.execute(select(ComandoImpresora))).scalars().all()
    assert o.estado == "fallido" and "Modo desarrollador" in o.detalle
