"""El servicio de la impresora con una impresora de mentira: estado, trabajos y órdenes."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.impresora import lector3mf
from app.impresora.servicio import Servicio
from app.models import ComandoImpresora, EstadoImpresora, TrabajoImpresora


class FalsoCliente:
    def __init__(self):
        self.estado: dict = {}
        self.conectada = True
        self.ultimo_mensaje = datetime.now(UTC)
        self.enviadas: list = []
        self.fallar = False

    def crudo(self):
        return dict(self.estado)

    def enviar(self, comando, valor=None):
        self.enviadas.append((comando, valor))
        return not self.fallar

    def pedir_todo(self):
        pass


@pytest.fixture
def cliente():
    return FalsoCliente()


@pytest.fixture
def servicio(cliente, monkeypatch):
    llamadas = []

    def falso(ip, codigo, archivo, nombre, plate=None):
        llamadas.append((archivo, nombre))
        return lector3mf.InfoArchivo(
            plate=1, minutos=90, gramos=12.5,
            filamentos=[{"tipo": "PLA", "color": "#ff0000", "gramos": 12.5}],
        )  # fmt: skip

    monkeypatch.setattr(lector3mf, "leer_de_la_impresora", falso)
    s = Servicio(cliente)
    s.llamadas = llamadas
    return s


def poner(cliente, estado, nombre="Soporte", tarea="77", progreso=0):
    cliente.estado = {"gcode_state": estado, "subtask_name": nombre, "gcode_file": f"{nombre}.3mf",
                      "task_id": tarea, "mc_percent": progreso}  # fmt: skip


async def trabajos(db):
    db.expire_all()
    return (
        (await db.execute(select(TrabajoImpresora).order_by(TrabajoImpresora.inicio_en)))
        .scalars()
        .all()
    )


async def test_ciclo_completo_de_un_trabajo(servicio, cliente, db):
    poner(cliente, "IDLE")
    await servicio._seguir_trabajos()
    assert await trabajos(db) == []

    poner(cliente, "RUNNING", progreso=10)
    await servicio._seguir_trabajos()
    (t,) = await trabajos(db)
    assert t.estado == "en_curso" and t.inicio_observado is True and t.nombre == "Soporte"
    assert t.gramos_total == 12.5 and t.minutos_estimados == 90  # leído del .3mf al empezar

    poner(cliente, "RUNNING", progreso=60)
    await servicio._seguir_trabajos()
    assert (await trabajos(db))[0].progreso == 60 and len(await trabajos(db)) == 1

    poner(cliente, "FINISH", progreso=100)
    await servicio._seguir_trabajos()
    (t,) = await trabajos(db)
    assert t.estado == "terminado" and t.fin_en is not None and t.progreso == 100
    assert t.gestion == "pendiente" and t.filamentos[0]["color"] == "#ff0000"

    # El estado FINISH persiste en la impresora: no se crea ni se duplica nada.
    await servicio._seguir_trabajos()
    assert len(await trabajos(db)) == 1


async def test_progreso_real_no_arrastra_el_100_del_trabajo_anterior(servicio, cliente, db):
    poner(cliente, "FINISH", progreso=100)  # el trabajo anterior terminó al 100 %
    await servicio._seguir_trabajos()
    poner(cliente, "PREPARE", progreso=100)  # empieza el nuevo y la impresora aún informa 100
    await servicio._seguir_trabajos()
    (t,) = await trabajos(db)
    assert t.estado == "en_curso" and t.progreso == 0
    poner(cliente, "RUNNING", progreso=3)
    await servicio._seguir_trabajos()
    assert (await trabajos(db))[0].progreso == 3
    poner(cliente, "RUNNING", progreso=2)  # puede bajar: es el valor real, no un máximo
    await servicio._seguir_trabajos()
    assert (await trabajos(db))[0].progreso == 2


async def test_cancelado_queda_interrumpido_con_su_progreso(servicio, cliente, db):
    poner(cliente, "IDLE")
    await servicio._seguir_trabajos()
    poner(cliente, "RUNNING", progreso=40)
    await servicio._seguir_trabajos()
    poner(cliente, "FAILED", progreso=40)
    await servicio._seguir_trabajos()
    (t,) = await trabajos(db)
    assert t.estado == "interrumpido" and t.progreso == 40


async def test_servicio_que_arranca_con_un_trabajo_ya_andando(servicio, cliente, db):
    poner(cliente, "RUNNING", progreso=85)
    await servicio._seguir_trabajos()
    (t,) = await trabajos(db)
    assert t.inicio_observado is False  # el inicio real no se vio: el tiempo medido no es confiable


async def test_un_finish_viejo_al_arrancar_no_crea_trabajo(servicio, cliente, db):
    poner(cliente, "FINISH", progreso=100)
    await servicio._seguir_trabajos()
    assert await trabajos(db) == []


async def test_reinicio_del_servicio_continua_el_mismo_trabajo(cliente, monkeypatch, db):
    monkeypatch.setattr(lector3mf, "leer_de_la_impresora", lambda *a, **k: None)
    poner(cliente, "IDLE")
    s1 = Servicio(cliente)
    await s1._seguir_trabajos()
    poner(cliente, "RUNNING", progreso=20)
    await s1._seguir_trabajos()
    s2 = Servicio(cliente)  # se reinicia a mitad del trabajo
    poner(cliente, "RUNNING", progreso=50)
    await s2._seguir_trabajos()
    poner(cliente, "FINISH", progreso=100)
    await s2._seguir_trabajos()
    (t,) = await trabajos(db)
    assert (
        t.estado == "terminado" and t.inicio_observado is True
    )  # sigue siendo el mismo, con su inicio real


async def test_sin_3mf_el_trabajo_queda_sin_gramos_para_ponerlos_a_mano(cliente, monkeypatch, db):
    intentos = []
    monkeypatch.setattr(lector3mf, "leer_de_la_impresora", lambda *a, **k: intentos.append(1))
    s = Servicio(cliente)
    poner(cliente, "IDLE")
    await s._seguir_trabajos()
    poner(cliente, "RUNNING")
    await s._seguir_trabajos()
    poner(cliente, "FINISH", progreso=100)
    await s._seguir_trabajos()
    (t,) = await trabajos(db)
    assert t.estado == "terminado" and t.gramos_total is None
    assert len(intentos) == 2  # al empezar y una última vez al terminar


async def test_error_leyendo_el_archivo_no_rompe_el_seguimiento(cliente, monkeypatch, db):
    def falla(*a, **k):
        raise OSError("sin red")

    monkeypatch.setattr(lector3mf, "leer_de_la_impresora", falla)
    s = Servicio(cliente)
    poner(cliente, "IDLE")
    await s._seguir_trabajos()
    poner(cliente, "RUNNING")
    await s._seguir_trabajos()
    poner(cliente, "FINISH", progreso=100)
    await s._seguir_trabajos()
    assert (await trabajos(db))[0].estado == "terminado"


async def test_trabajo_nuevo_cierra_el_anterior_que_no_se_vio_terminar(servicio, cliente, db):
    poner(cliente, "RUNNING", nombre="Uno", tarea="1")
    await servicio._seguir_trabajos()
    poner(cliente, "RUNNING", nombre="Dos", tarea="2")
    await servicio._seguir_trabajos()
    uno, dos = await trabajos(db)
    assert (uno.nombre, uno.estado, dos.nombre, dos.estado) == (
        "Uno",
        "interrumpido",
        "Dos",
        "en_curso",
    )


async def test_escribe_el_estado_normalizado(servicio, cliente, db):
    poner(cliente, "RUNNING", progreso=33)
    await servicio._escribir_estado()
    fila = await db.get(EstadoImpresora, 1)
    assert (
        fila.conectada is True
        and fila.datos["estado"] == "imprimiendo"
        and fila.datos["progreso"] == 33
    )
    cliente.conectada = False
    servicio._ultimo_estado = None
    await servicio._escribir_estado()
    await db.refresh(fila)
    assert fila.conectada is False


async def test_atiende_ordenes_y_deja_vencer_las_viejas(servicio, cliente, db):
    from datetime import timedelta

    from app.core.tokens import ahora

    db.add_all([
        ComandoImpresora(comando="pausar"),
        ComandoImpresora(comando="luz", valor="off"),
        ComandoImpresora(comando="cancelar", creado_en=ahora() - timedelta(minutes=5)),
    ])  # fmt: skip
    await db.commit()
    await servicio._atender_ordenes()
    db.expire_all()
    estados = {o.comando: o.estado for o in (await db.execute(select(ComandoImpresora))).scalars()}
    assert estados == {"pausar": "enviado", "luz": "enviado", "cancelar": "vencido"}
    assert cliente.enviadas == [("pausar", None), ("luz", "off")]  # la vieja NO se ejecutó


async def test_orden_sin_conexion_o_con_error_queda_fallida(servicio, cliente, db):
    db.add_all([ComandoImpresora(comando="pausar")])
    await db.commit()
    cliente.conectada = False
    await servicio._atender_ordenes()
    db.expire_all()
    o = (await db.execute(select(ComandoImpresora))).scalar_one()
    assert o.estado == "fallido" and "no está conectada" in o.detalle
    assert cliente.enviadas == []
    db.add(ComandoImpresora(comando="reanudar"))
    await db.commit()
    cliente.conectada, cliente.fallar = True, True
    await servicio._atender_ordenes()
    db.expire_all()
    ultimo = (
        (await db.execute(select(ComandoImpresora).order_by(ComandoImpresora.id.desc())))
        .scalars()
        .first()
    )
    assert ultimo.estado == "fallido"


# ------------------------------------------------- configuración tomada de la base (panel)
class ClienteCreado(FalsoCliente):
    creados: list = []

    def __init__(self, ip, serial, codigo):
        super().__init__()
        self.datos = (ip, serial, codigo)
        self.iniciado = self.detenido = False
        ClienteCreado.creados.append(self)

    def iniciar(self):
        self.iniciado = True

    def detener(self):
        self.detenido = True


async def guardar_config(db, ip="10.0.4.244", codigo="12345678"):
    from app.core import secretos
    from app.impresora import ajustes

    f = await ajustes.obtener_o_crear(db)
    f.ip, f.serial, f.codigo_acceso = ip, "03919D550007E91", secretos.cifrar(codigo)
    f.version += 1
    await db.commit()


@pytest.fixture
def real(monkeypatch):
    from app.impresora import bambu

    ClienteCreado.creados = []
    monkeypatch.setattr(bambu, "ClienteBambu", ClienteCreado)
    return ClienteCreado


async def test_sin_configuracion_espera_y_lo_dice(db, real):
    s = Servicio()
    await s._cargar_config()
    await s._escribir_estado()
    assert s.cliente is None and real.creados == []
    fila = await db.get(EstadoImpresora, 1)
    assert fila.conectada is False and fila.config_version is None
    await s._seguir_trabajos()  # sin cliente: no hace nada ni falla
    await s._atender_ordenes()


async def test_conecta_con_lo_guardado_en_la_base_y_reconecta_al_cambiar(db, real):
    s = Servicio()
    await guardar_config(db)
    await s._cargar_config()
    (c1,) = real.creados
    assert c1.datos == ("10.0.4.244", "03919D550007E91", "12345678") and c1.iniciado
    await s._cargar_config()  # sin cambios: no reconecta
    assert len(real.creados) == 1

    await guardar_config(db, ip="192.168.1.9", codigo="87654321")
    await s._cargar_config()
    c2 = real.creados[-1]
    assert c1.detenido and c2.datos == ("192.168.1.9", "03919D550007E91", "87654321")
    await s._escribir_estado()
    db.expire_all()
    fila = await db.get(EstadoImpresora, 1)
    assert (
        fila.config_version
        == (
            await db.get(__import__("app.models", fromlist=["ConfigImpresora"]).ConfigImpresora, 1)
        ).version
    )


async def test_informa_el_motivo_si_no_conecta(db, real):
    s = Servicio()
    await guardar_config(db)
    await s._cargar_config()
    s.cliente.conectada = False
    s.cliente.error_conexion = "credenciales"
    await s._escribir_estado()
    db.expire_all()
    assert (await db.get(EstadoImpresora, 1)).conexion_error == "credenciales"


async def test_importa_una_vez_el_env_y_el_archivo_viejo(db, real, monkeypatch, tmp_path):
    from app.config import settings
    from app.impresora import ajustes, nube

    archivo = tmp_path / "bambu.json"
    nube.AlmacenToken(archivo).guardar(nube.Sesion("tok-" + "z" * 30, "ref", 0))
    monkeypatch.setattr(settings, "bambu_ip", "10.0.4.244")
    monkeypatch.setattr(settings, "bambu_serial", "03919D550007E91")
    monkeypatch.setattr(settings, "bambu_access_code", "12345678")
    monkeypatch.setattr(settings, "bambu_nube_archivo", str(archivo))
    s = Servicio()
    await s._cargar_config()
    db.expire_all()
    f = await ajustes.obtener(db)
    assert f.ip == "10.0.4.244" and ajustes.conexion_de(f).codigo == "12345678"
    assert ajustes.sesion_de(f).access_token.startswith("tok-")
    assert not archivo.exists()  # ya vive en la base
    assert real.creados and s._solicitud_nueva  # conectó y pidió sincronizar

    # lo guardado en el panel manda sobre el .env, y desvincular no revive el archivo
    f.nube_sesion = None
    f.ip = "192.168.1.9"
    f.version += 1
    await db.commit()
    s2 = Servicio()
    await s2._cargar_config()
    db.expire_all()
    f = await ajustes.obtener(db)
    assert f.ip == "192.168.1.9" and f.nube_sesion is None


async def test_un_env_invalido_se_ignora(db, real, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "bambu_ip", "8.8.8.8")
    monkeypatch.setattr(settings, "bambu_serial", "03919D550007E91")
    monkeypatch.setattr(settings, "bambu_access_code", "12345678")
    s = Servicio()
    await s._cargar_config()
    assert s.cliente is None and real.creados == []
