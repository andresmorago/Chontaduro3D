"""Historial de Bambu Cloud: lectura de tareas, token que se renueva y unión con lo detectado."""

import json
import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.core.tokens import ahora
from app.impresora import nube, sincronizacion
from app.impresora.nube import AlmacenToken, ClienteNube, Sesion, tarea_de
from app.impresora.servicio import Servicio
from app.models import EstadoImpresora, TrabajoImpresora


def tarea_cruda(**kw):
    inicio = ahora() - timedelta(hours=5)
    base = {
        "id": 1440858776, "title": "tfic-angled", "status": 2, "plateIndex": 1,
        "startTime": inicio.isoformat().replace("+00:00", "Z"),
        "endTime": (inicio + timedelta(hours=1, minutes=6)).isoformat().replace("+00:00", "Z"),
        "costTime": 3900, "weight": 22.57, "deviceId": "SERIE1",
        "amsDetailMapping": [
            {"ams": 0, "filamentType": "PLA", "targetFilamentType": "PLA",
             "sourceColor": "443089FF", "targetColor": "443089FF", "weight": 22.57}
        ],
    }  # fmt: skip
    return {**base, **kw}


# ----------------------------------------------------------------------------- parseo
def test_tarea_terminada():
    t = tarea_de(tarea_cruda())
    assert (t.id, t.titulo, t.estado, t.minutos, t.gramos, t.plate) == (
        "1440858776", "tfic-angled", "terminado", 65, 22.57, 1,
    )  # fmt: skip
    # costTime (65) es la estimación; el tiempo real sale de inicio→fin (1 h 6 min).
    assert t.minutos_reales == 66
    assert t.filamentos == [{"tipo": "PLA", "color": "#443089", "gramos": 22.57}]
    assert t.dispositivo == "SERIE1"


def test_estados_de_la_nube():
    assert tarea_de(tarea_cruda(status=2)).estado == "terminado"
    assert tarea_de(tarea_cruda(status=3)).estado == "interrumpido"
    # Cualquier otro estado es un trabajo EN CURSO: la nube le pone una hora de fin provisional
    # (p. ej. «hace 2 minutos» en uno que sigue imprimiendo) y no debe tomarse como el final.
    for en_curso in (0, 1, 4, 5, None):
        assert tarea_de(tarea_cruda(status=en_curso)) is None, en_curso


def test_tolera_datos_incompletos_o_raros():
    assert tarea_de(tarea_cruda(endTime=None)) is None
    assert tarea_de(tarea_cruda(startTime="basura")) is None
    assert tarea_de(tarea_cruda(id=None)) is None
    assert tarea_de("no es un dict") is None
    cruda = tarea_cruda(endTime=tarea_cruda()["startTime"], title="")
    cruda["startTime"] = tarea_cruda()["endTime"]  # fin antes que inicio
    assert tarea_de(cruda) is None
    t = tarea_de(tarea_cruda(costTime=None, weight=None, amsDetailMapping=None, title=None))
    assert t.minutos is None and t.gramos is None and t.titulo == "Trabajo sin nombre"


def test_peso_total_sale_de_los_filamentos_si_falta_y_fechas_en_epoch():
    mapa = [{"filamentType": "PLA", "sourceColor": "FF0000FF", "weight": 3.5},
            {"filamentType": "PETG", "sourceColor": "00FF00FF", "weight": 1.5}]  # fmt: skip
    t = tarea_de(tarea_cruda(weight=0, amsDetailMapping=mapa))
    assert t.gramos == 5.0 and [f["tipo"] for f in t.filamentos] == ["PLA", "PETG"]
    ms = int(datetime(2026, 11, 10, 15, 0, tzinfo=UTC).timestamp() * 1000)
    t = tarea_de(tarea_cruda(startTime=ms, endTime=ms + 600_000))
    assert (
        t.inicio == datetime(2026, 11, 10, 15, 0, tzinfo=UTC) and (t.fin - t.inicio).seconds == 600
    )


# ------------------------------------------------------------------------------ token
def test_almacen_guarda_con_permisos_600(tmp_path):
    a = AlmacenToken(tmp_path / "n" / "bambu.json")
    assert not a.existe() and a.cargar() is None
    a.guardar(Sesion("acc", "ref", 123.0))
    assert a.existe() and oct(a.ruta.stat().st_mode & 0o777) == "0o600"
    s = a.cargar()
    assert (s.access_token, s.refresh_token, s.expira_en) == ("acc", "ref", 123.0)
    a.ruta.write_text("{roto")
    assert a.cargar() is None  # archivo dañado = sin sesión, no una excepción


def cliente_http(manejador, tmp_path, sesion=None):
    a = AlmacenToken(tmp_path / "bambu.json")
    if sesion:
        a.guardar(sesion)
    http = httpx.Client(
        transport=httpx.MockTransport(manejador), headers={"User-Agent": nube.AGENTE}
    )
    return ClienteNube("https://nube.test", a, http), a


def test_sin_token_pide_login(tmp_path):
    c, _ = cliente_http(lambda r: httpx.Response(200, json={}), tmp_path)
    with pytest.raises(nube.RequiereLogin):
        c.tareas(ahora() - timedelta(days=7))


def test_consulta_con_bearer_y_filtra_por_fecha_y_dispositivo(tmp_path):
    vistas = []

    def man(req):
        vistas.append(req)
        fin_viejo = ahora() - timedelta(days=30)
        viejo = tarea_cruda(
            id=1, endTime=fin_viejo.isoformat(),
            startTime=(fin_viejo - timedelta(hours=1)).isoformat(),
        )  # fmt: skip
        return httpx.Response(200, json={"hits": [
            tarea_cruda(id=2), tarea_cruda(id=3, deviceId="OTRA"),
            tarea_cruda(id=4, status=1), viejo,
        ]})  # fmt: skip

    c, _ = cliente_http(man, tmp_path, Sesion("TOKEN", "R", time.time() + 3600))
    ts = c.tareas(ahora() - timedelta(days=7), "SERIE1")
    assert [t.id for t in ts] == ["2"]  # solo esta impresora, cerrada y dentro de la ventana
    assert vistas[0].headers["authorization"] == "Bearer TOKEN"
    assert "misimpresiones" in vistas[0].headers["user-agent"]


def test_token_vencido_se_renueva_y_se_guarda(tmp_path):
    def man(req):
        if req.url.path.endswith("/refreshtoken"):
            assert json.loads(req.content) == {"refreshToken": "R1"}
            return httpx.Response(
                200, json={"accessToken": "NUEVO", "refreshToken": "R2", "expiresIn": 7776000}
            )
        assert req.headers["authorization"] == "Bearer NUEVO"
        return httpx.Response(200, json={"hits": [tarea_cruda()]})

    c, a = cliente_http(man, tmp_path, Sesion("VIEJO", "R1", time.time() - 10))
    assert len(c.tareas(ahora() - timedelta(days=7))) == 1
    s = a.cargar()
    assert (s.access_token, s.refresh_token) == ("NUEVO", "R2") and s.expira_en > time.time()


def test_401_renueva_una_vez_y_si_falla_pide_login(tmp_path):
    def man(req):
        return httpx.Response(401 if not req.url.path.endswith("refreshtoken") else 401, json={})

    c, _ = cliente_http(man, tmp_path, Sesion("T", "R", time.time() + 3600))
    with pytest.raises(nube.RequiereLogin):
        c.tareas(ahora() - timedelta(days=7))
    c, _ = cliente_http(man, tmp_path / "x", Sesion("T", "", time.time() + 3600))  # sin refresh
    with pytest.raises(nube.RequiereLogin):
        c.tareas(ahora() - timedelta(days=7))


def test_errores_de_la_nube_son_errores_controlados(tmp_path):
    sesion = Sesion("T", "R", time.time() + 3600)
    for codigo in (403, 429, 500):
        c, _ = cliente_http(lambda r, k=codigo: httpx.Response(k), tmp_path, sesion)
        with pytest.raises(nube.ErrorNube):
            c.tareas(ahora() - timedelta(days=7))
    c, _ = cliente_http(lambda r: httpx.Response(200, text="<html>"), tmp_path, sesion)
    with pytest.raises(nube.ErrorNube):
        c.tareas(ahora() - timedelta(days=7))

    def sin_red(req):
        raise httpx.ConnectError("sin red")

    c, _ = cliente_http(sin_red, tmp_path, sesion)
    with pytest.raises(nube.ErrorNube):
        c.tareas(ahora() - timedelta(days=7))


def test_paginacion_se_detiene_si_la_api_ignora_el_cursor(tmp_path):
    paginas = []

    def man(req):
        paginas.append(dict(req.url.params))
        return httpx.Response(
            200, json={"hits": [tarea_cruda(id=i) for i in range(50)]}
        )  # siempre igual

    c, _ = cliente_http(man, tmp_path, Sesion("T", "R", time.time() + 3600))
    assert len(c.tareas(ahora() - timedelta(days=7))) == 50
    assert len(paginas) == 2  # la segunda página no trajo nada nuevo: se corta


# --------------------------------------------------------------------- unión con la base
async def test_tarea_nueva_se_crea_por_revisar(db):
    t = tarea_de(tarea_cruda())
    r = await sincronizacion.aplicar(db, [t])
    await db.commit()
    assert r == {"creadas": 1, "completadas": 0}
    j = (await db.execute(select(TrabajoImpresora))).scalar_one()
    assert (j.origen, j.gestion, j.estado, j.nube_id, j.minutos_medidos) == (
        "nube",
        "pendiente",
        "terminado",
        "1440858776",
        66,  # tiempo real (inicio→fin); el costTime (65) queda como estimado
    )
    assert j.minutos_estimados == 65
    assert float(j.gramos_total) == 22.57 and j.filamentos[0]["color"] == "#443089"


async def test_es_idempotente(db):
    t = tarea_de(tarea_cruda())
    await sincronizacion.aplicar(db, [t])
    await db.commit()
    r = await sincronizacion.aplicar(db, [t])
    await db.commit()
    assert r == {"creadas": 0, "completadas": 0}
    assert len((await db.execute(select(TrabajoImpresora))).scalars().all()) == 1


async def test_une_con_el_trabajo_detectado_en_vivo_por_task_id(db):
    t = tarea_de(tarea_cruda())
    en_vivo = TrabajoImpresora(nombre="tfic-angled", tarea_id="1440858776", estado="terminado",
                               inicio_en=t.inicio, fin_en=t.fin, inicio_observado=True,
                               minutos_estimados=66, gramos_total=22.6)  # fmt: skip
    db.add(en_vivo)
    await db.commit()
    r = await sincronizacion.aplicar(db, [t])
    await db.commit()
    assert r == {"creadas": 0, "completadas": 1}
    await db.refresh(en_vivo)
    assert en_vivo.nube_id == "1440858776" and en_vivo.minutos_medidos == 66
    # Los gramos de la nube (los que muestra Bambu web) corrigen lo leído en vivo del .3mf.
    assert float(en_vivo.gramos_total) == 22.57 and en_vivo.origen == "impresora"
    assert len((await db.execute(select(TrabajoImpresora))).scalars().all()) == 1


async def test_une_por_nombre_y_hora_si_no_hay_id_comun(db):
    t = tarea_de(tarea_cruda(id=999))
    en_vivo = TrabajoImpresora(nombre="TFIC angled", tarea_id="0", estado="terminado",
                               inicio_en=t.inicio + timedelta(minutes=3), fin_en=t.fin)  # fmt: skip
    otro = TrabajoImpresora(nombre="Otra cosa", tarea_id="0", estado="terminado",
                            inicio_en=t.inicio, fin_en=t.fin)  # fmt: skip
    db.add_all([en_vivo, otro])
    await db.commit()
    await sincronizacion.aplicar(db, [t])
    await db.commit()
    await db.refresh(en_vivo)
    await db.refresh(otro)
    assert en_vivo.nube_id == "999" and otro.nube_id is None
    assert len((await db.execute(select(TrabajoImpresora))).scalars().all()) == 2


async def test_un_trabajo_en_curso_no_se_toca_con_datos_de_la_nube(db):
    t = tarea_de(tarea_cruda())
    vivo = TrabajoImpresora(nombre="x", tarea_id=t.id, estado="en_curso", inicio_en=t.inicio,
                            minutos_estimados=383)  # fmt: skip
    db.add(vivo)
    await db.commit()
    r = await sincronizacion.aplicar(db, [t])
    await db.commit()
    await db.refresh(vivo)
    assert r == {"creadas": 0, "completadas": 0}
    assert vivo.minutos_medidos is None and vivo.nube_id is None and vivo.fin_en is None


async def test_api_no_muestra_tiempo_medido_de_un_trabajo_en_curso(admin, db):
    ahora_ = ahora()
    db.add(TrabajoImpresora(nombre="x", tarea_id="9", estado="en_curso", inicio_en=ahora_,
                            minutos_medidos=2, minutos_estimados=383))  # fmt: skip
    await db.commit()
    j = (await admin.get("/api/impresora/trabajos")).json()[0]
    assert j["minutos"] == 383 and j["minutos_origen"] == "estimado"  # no el «2 min (medido)»


async def test_corrige_el_tiempo_si_antes_se_guardo_el_estimado(db):
    t = tarea_de(tarea_cruda())
    viejo = TrabajoImpresora(nombre="x", tarea_id=t.id, nube_id=t.id, origen="nube",
                             estado="terminado", inicio_en=t.inicio, fin_en=t.fin,
                             minutos_medidos=65)  # fmt: skip
    db.add(viejo)
    await db.commit()
    await sincronizacion.aplicar(db, [t])
    await db.commit()
    await db.refresh(viejo)
    assert viejo.minutos_medidos == 66 and viejo.minutos_estimados == 65


async def test_no_revierte_lo_ya_importado_ni_ignorado(db):
    t = tarea_de(tarea_cruda())
    for gestion in ("importado", "ignorado"):
        await db.execute(TrabajoImpresora.__table__.delete())
        j = TrabajoImpresora(nombre="x", tarea_id=t.id, estado="terminado", inicio_en=t.inicio,
                             fin_en=t.fin, gestion=gestion)  # fmt: skip
        db.add(j)
        await db.commit()
        await sincronizacion.aplicar(db, [t])
        await db.commit()
        await db.refresh(j)
        assert j.gestion == gestion  # la decisión de la persona se respeta
        if gestion == "importado":
            assert j.minutos_medidos is None and j.gramos_total is None  # ni se toca


async def test_el_tiempo_medido_de_la_nube_manda_sobre_el_visto_en_vivo(admin, db):
    t = tarea_de(tarea_cruda())
    fin = t.inicio + timedelta(minutes=90)
    db.add(TrabajoImpresora(nombre="x", tarea_id=t.id, estado="terminado", inicio_en=t.inicio,
                            fin_en=fin, inicio_observado=True))  # fmt: skip
    await db.commit()
    assert (await admin.get("/api/impresora/trabajos")).json()[0]["minutos"] == 90  # visto en vivo
    await sincronizacion.aplicar(db, [t])
    await db.commit()
    j = (await admin.get("/api/impresora/trabajos")).json()[0]
    assert j["minutos"] == 66 and j["minutos_origen"] == "medido"


async def test_api_muestra_origen_y_estado_de_la_nube(admin, db):
    await sincronizacion.aplicar(db, [tarea_de(tarea_cruda())])
    db.add(EstadoImpresora(id=1, conectada=True, datos={"estado": "lista"},
                           nube_estado="requiere_login",
                           nube_detalle="Falta iniciar sesión"))  # fmt: skip
    await db.commit()
    assert (await admin.get("/api/impresora/trabajos")).json()[0]["origen"] == "nube"
    j = (await admin.get("/api/impresora")).json()
    assert j["nube"]["estado"] == "requiere_login" and "iniciar sesión" in j["nube"]["detalle"]


# ------------------------------------------------------------------------------ servicio
class FalsaNube:
    def __init__(self, tareas=None, error=None):
        self.tareas_, self.error, self.llamadas = tareas or [], error, 0

    def tareas(self, desde, dispositivo=None):
        self.llamadas += 1
        if self.error:
            raise self.error
        return self.tareas_


async def servicio_con(db, cliente, nube_falsa, hay_token=True):
    """Servicio con la cuenta de Bambu vinculada (o no) en la base, como lo deja el panel."""
    from app.impresora import ajustes

    if hay_token:
        fila = await ajustes.obtener_o_crear(db)
        ajustes.poner_sesion(fila, Sesion("tok-" + "x" * 20, "ref", 0))
        await db.commit()
    return Servicio(cliente, nube_falsa)


async def estado_nube(db):
    db.expire_all()
    fila = await db.get(EstadoImpresora, 1)
    return fila.nube_estado, fila.nube_detalle, fila.nube_sincronizada_en


async def test_servicio_sin_token_no_llama_a_la_nube(db):
    from tests.test_impresora_servicio import FalsoCliente

    n = FalsaNube()
    s = await servicio_con(db, FalsoCliente(), n, hay_token=False)
    await s._sincronizar_nube()
    assert n.llamadas == 0 and (await estado_nube(db))[0] == "sin_configurar"


async def test_servicio_sincroniza_y_espera_para_la_proxima(db):
    from tests.test_impresora_servicio import FalsoCliente

    n = FalsaNube([tarea_de(tarea_cruda())])
    s = await servicio_con(db, FalsoCliente(), n)
    await s._sincronizar_nube()
    estado, _, cuando = await estado_nube(db)
    assert estado == "ok" and cuando is not None and n.llamadas == 1
    await s._sincronizar_nube()  # aún no toca
    assert n.llamadas == 1
    assert len((await db.execute(select(TrabajoImpresora))).scalars().all()) == 1


async def test_servicio_informa_login_vencido_y_errores_sin_caerse(db):
    from tests.test_impresora_servicio import FalsoCliente

    s = await servicio_con(
        db, FalsoCliente(), FalsaNube(error=nube.RequiereLogin("repite el login"))
    )
    await s._sincronizar_nube()
    assert (await estado_nube(db))[:2] == ("requiere_login", "repite el login")
    s = await servicio_con(
        db, FalsoCliente(), FalsaNube(error=nube.ErrorNube("Bambu Cloud bloqueó (403)"))
    )
    await s._sincronizar_nube()
    assert (await estado_nube(db))[:2] == ("error", "Bambu Cloud bloqueó (403)")
    assert s._nube_proxima < ahora() + timedelta(seconds=300)  # tras un fallo reintenta pronto


async def test_la_nube_corrige_gramos_de_un_3mf_equivocado_pero_no_toca_lo_importado(db):
    t = tarea_de(tarea_cruda())  # la nube dice 22,57 g (lo que ve la persona en Bambu web)
    mal = TrabajoImpresora(nombre="tfic-angled", tarea_id="1440858776", estado="terminado",
                           inicio_en=t.inicio, fin_en=t.fin, inicio_observado=True,
                           gramos_total=4.91, minutos_estimados=20,
                           filamentos=[{"tipo": "PLA", "color": "#0", "gramos": 4.91}])  # fmt: skip
    db.add(mal)
    await db.commit()
    await sincronizacion.aplicar(db, [t])
    await db.commit()
    await db.refresh(mal)
    assert float(mal.gramos_total) == 22.57 and mal.minutos_estimados == 65
    assert mal.filamentos == [{"tipo": "PLA", "color": "#443089", "gramos": 22.57}]

    # Ya importado como producción: queda como está (el lote tiene sus propios datos).
    mal.gestion, mal.gramos_total = "importado", 5
    await db.commit()
    await sincronizacion.aplicar(db, [t])
    await db.commit()
    await db.refresh(mal)
    assert float(mal.gramos_total) == 5
