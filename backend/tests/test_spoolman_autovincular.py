"""Rollos sin chip que se vinculan solos a su ranura, y la actividad del AMS en el panel."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config import settings
from app.models import RanuraBobina, RegistroAuditoria
from app.spoolman.cliente import Bobina, ErrorSpoolman
from tests.test_spoolman import (  # noqa: F401  (limpiar_spoolman es autouse)
    TAG,
    bandeja_cruda,
    ams_con,
    ciclo,
    limpiar_spoolman,
    servicio_con,
    spool,
)

VIOLETA = "#8000ff"
SIN_CHIP = "0" * 16


def sin_chip(id_, color="8000FFFF", tipo="PLA", marca=""):
    return bandeja_cruda(id_, SIN_CHIP, color=color, tipo=tipo, marca=marca)


async def estable(s):
    """Un ciclo con todo lo visto desde hace rato (si no, espera a que se vea estable)."""
    vieja = timedelta(minutes=1)
    for registro in (s._firmas_ranura, s._ams_visto):
        for k, (firma, desde) in list(registro.items()):
            registro[k] = (firma, desde - vieja)
    s._autovincular_proximo = datetime.min.replace(tzinfo=UTC)
    await ciclo(s)


async def vinculos(db):
    db.expire_all()
    return {r.ranura: r for r in (await db.execute(select(RanuraBobina))).scalars()}


async def auditorias(db, accion):
    db.expire_all()
    q = select(RegistroAuditoria).where(RegistroAuditoria.accion == accion)
    return list((await db.execute(q.order_by(RegistroAuditoria.id))).scalars())


def sunlu(spool, id_=1, color=VIOLETA, **kw):
    spool.agregar(id_, nombre=f"Sunlu · PLA {id_}", color=color, proveedor="Sunlu", **kw)


# ============================================================================= autovincular
async def test_una_sola_candidata_se_vincula_tras_la_espera(spool, db):
    spool.agregar(1, nombre="Sunlu · PLA Violet", color="#8010f0", proveedor="Sunlu")
    spool.agregar(2, nombre="Sunlu · PLA Rojo", color="#ff0000", proveedor="Sunlu")
    _, s = await servicio_con(None, spool, sin_chip("2"))
    await ciclo(s)  # recién vista: aún no se actúa
    assert await vinculos(db) == {}
    await estable(s)
    v = (await vinculos(db))["2"]
    assert (v.spool_id, v.tipo, v.color) == (1, "PLA", "#8000ff")
    (a,) = await auditorias(db, "spoolman_ranura_autovinculada")
    assert a.detalle == {"ranura": "2", "spool_id": 1, "bobina": "Sunlu · PLA Violet"}
    await estable(s)  # ya vinculada: no se repite
    assert len(await auditorias(db, "spoolman_ranura_autovinculada")) == 1


async def test_pla_mas_y_pla_basic_son_el_mismo_material(spool, db):
    sunlu(spool)
    _, s = await servicio_con(None, spool, sin_chip("0", tipo="PLA+"))
    await estable(s)
    assert (await vinculos(db))["0"].spool_id == 1
    # …pero otro material no cuenta
    spool.bobinas_[1] = Bobina(**{**spool.bobinas_[1].__dict__, "material": "PETG"})
    await db.execute(RanuraBobina.__table__.delete())
    await db.commit()
    await estable(s)
    assert await vinculos(db) == {}


async def test_con_dos_candidatas_no_adivina(spool, db):
    sunlu(spool, 1)
    sunlu(spool, 2, color="#8a10f5")
    _, s = await servicio_con(None, spool, sin_chip("1"))
    await estable(s)
    assert await vinculos(db) == {}
    assert await auditorias(db, "spoolman_ranura_autovinculada") == []


async def test_sin_candidatas_no_hace_nada(spool, db):
    sunlu(spool, 1, color="#00ff00")  # otro color
    _, s = await servicio_con(None, spool, sin_chip("1"))
    await estable(s)
    assert await vinculos(db) == {}


async def test_una_bobina_con_chip_no_cuenta(spool, db):
    sunlu(spool, 1, tags=[TAG])
    _, s = await servicio_con(None, spool, sin_chip("1"))
    await estable(s)
    assert await vinculos(db) == {}


async def test_una_bobina_ya_vinculada_a_otra_ranura_no_cuenta(spool, db):
    sunlu(spool, 1)
    db.add(RanuraBobina(ranura="0", spool_id=1, tipo="PLA", color=VIOLETA))
    await db.commit()
    _, s = await servicio_con(None, spool, sin_chip("0"), sin_chip("1"))
    await estable(s)
    v = await vinculos(db)
    assert set(v) == {"0"} and v["0"].spool_id == 1  # la 1 se queda sin vincular


async def test_un_vinculo_vigente_no_se_toca(spool, db):
    sunlu(spool, 5)
    sunlu(spool, 6)  # candidata libre, pero la ranura ya tiene la suya
    db.add(RanuraBobina(ranura="1", spool_id=5, tipo="PLA", color=VIOLETA))
    await db.commit()
    _, s = await servicio_con(None, spool, sin_chip("1"))
    await estable(s)
    assert (await vinculos(db))["1"].spool_id == 5
    assert await auditorias(db, "spoolman_ranura_autovinculada") == []


async def test_una_ranura_desactualizada_se_revincula_a_la_nueva_unica_candidata(spool, db):
    sunlu(spool, 5, color="#ff0000")  # el rojo de antes
    sunlu(spool, 6)  # el violeta que se cargó ahora
    db.add(RanuraBobina(ranura="1", spool_id=5, tipo="PLA", color="#ff0000"))
    db.add(RanuraBobina(ranura="3", spool_id=6, tipo="PLA", color=VIOLETA))  # ya no está allí
    await db.commit()
    _, s = await servicio_con(None, spool, sin_chip("1"))  # la ranura 4 ya no informa nada
    await estable(s)
    v = await vinculos(db)
    assert (v["1"].spool_id, v["1"].color) == (6, VIOLETA)
    assert "3" not in v  # una bobina solo está en una ranura a la vez


async def test_se_puede_apagar(spool, db, monkeypatch):
    monkeypatch.setattr(settings, "spoolman_autovincular", False)
    sunlu(spool)
    _, s = await servicio_con(None, spool, sin_chip("1"))
    await estable(s)
    assert await vinculos(db) == {}


async def test_un_error_de_spoolman_no_tumba_el_ciclo(spool, db, caplog):
    sunlu(spool)
    _, s = await servicio_con(None, spool, sin_chip("1"))
    original = spool.bobinas
    llamadas = []

    async def falla_la_primera(*, archivadas=False):
        llamadas.append(archivadas)
        if len(llamadas) == 1:
            raise ErrorSpoolman("Spoolman no respondió a tiempo (ReadTimeout).")
        return await original(archivadas=archivadas)

    spool.bobinas = falla_la_primera
    s._ubicaciones_proximo = datetime.min.replace(tzinfo=UTC)
    with caplog.at_level(logging.WARNING, logger="impresora"):
        await estable(s)
    assert await vinculos(db) == {}
    assert len(llamadas) >= 2  # después del fallo el ciclo siguió (ubicaciones)
    assert "ranuras sin chip" in caplog.text
    await estable(s)  # y al recuperarse, se vincula
    assert (await vinculos(db))["1"].spool_id == 1


# ======================================================================= actividad del AMS
async def test_un_cambio_estable_del_ams_queda_en_la_auditoria_y_la_primera_foto_no(spool, db):
    cli, s = await servicio_con(None, spool, sin_chip("2", color="000000FF"))
    await estable(s)
    await estable(s)
    assert await auditorias(db, "ams_cambio") == []  # la primera foto no genera eventos

    ams_con(cli, sin_chip("2"))  # PLA negro → PLA violeta
    await estable(s)  # recién cambiada: aún no es estable
    assert await auditorias(db, "ams_cambio") == []
    await estable(s)
    (a,) = await auditorias(db, "ams_cambio")
    assert a.detalle == {
        "ranura": "2",
        "antes": {"tipo": "PLA", "color": "#000000", "tag": None},
        "despues": {"tipo": "PLA", "color": "#8000ff", "tag": None},
    }
    await estable(s)
    assert len(await auditorias(db, "ams_cambio")) == 1

    ams_con(cli, {"id": "2"})  # se vacía
    await estable(s)
    await estable(s)
    ultima = (await auditorias(db, "ams_cambio"))[-1]
    assert ultima.detalle["despues"] == {"tipo": None, "color": None, "tag": None}


async def test_un_parpadeo_no_es_un_cambio(spool, db):
    cli, s = await servicio_con(None, spool, sin_chip("2", color="000000FF"))
    await estable(s)
    ams_con(cli, sin_chip("2"))  # una lectura a medias…
    await ciclo(s)
    ams_con(cli, sin_chip("2", color="000000FF"))  # …y vuelve a lo de antes
    await estable(s)
    await estable(s)
    assert await auditorias(db, "ams_cambio") == []


# ================================================================== endpoint /spoolman/actividad
async def test_la_actividad_cuenta_lo_que_paso_y_no_muestra_logins(admin, db):
    def a(accion, detalle=None):
        db.add(RegistroAuditoria(accion=accion, detalle=detalle))

    a("login", {"email": "x@y.co"})
    a("login_fallido", {"email": "x@y.co"})
    a("ams_cambio", {
        "ranura": "2",
        "antes": {"tipo": "PLA", "color": "#000000", "tag": None},
        "despues": {"tipo": "PLA", "color": "#8000ff", "tag": None},
    })  # fmt: skip
    a("spoolman_ranura_autovinculada", {"ranura": "2", "spool_id": 1, "bobina": "Sunlu · PLA Violet"})
    a("spoolman_bobina_autoregistrada", {"ranura": "1", "spool_id": 7, "bobina": "PLA Basic"})
    a("spoolman_bobina_adoptada", {"ranura": "0", "spool_id": 8, "bobina": "PLA Basic"})
    a("spoolman_vinculo", {"ranura": "3", "spool_id": 4, "rfid": False})
    a("spoolman_vinculo", {"ranura": "3", "spool_id": None, "rfid": False})
    a("spoolman_bobina_creada", {"ranura": "254", "spool_id": 9, "rfid": False})
    a("spoolman_bobina_editada", {"spool_id": 7, "restante_g": 350.0, "precio": None, "archivar": None})
    a("spoolman_bobina_editada", {"spool_id": 7, "restante_g": None, "precio": None, "archivar": True})
    await db.commit()

    r = await admin.get("/api/spoolman/actividad", params={"limite": 50})
    assert r.status_code == 200, r.text
    filas = r.json()
    assert all(set(f) == {"id", "en", "tipo", "texto"} for f in filas)
    textos = [f["texto"] for f in filas]  # lo más nuevo primero
    assert textos == [
        "Bobina n.º 7: archivada (rollo terminado)",
        "Bobina n.º 7: quedan 350 g",
        "Externa: se creó en Spoolman la bobina n.º 9",
        "Ranura 4: se quitó la bobina asociada",
        "Ranura 4: se asoció a mano la bobina n.º 4",
        "Ranura 1: el chip del rollo Bambu se vinculó a «PLA Basic» (n.º 8)",
        "Ranura 2: rollo Bambu registrado en Spoolman como «PLA Basic» (n.º 7)",
        "Ranura 3: se unió sola a «Sunlu · PLA Violet» (n.º 1)",
        "Ranura 3: PLA negro → PLA violeta",
    ]  # fmt: skip
    assert [f["tipo"] for f in filas][-2:] == ["autovinculada", "cambio"]

    r = await admin.get("/api/spoolman/actividad", params={"limite": 2})
    assert len(r.json()) == 2
    assert (await admin.get("/api/spoolman/actividad", params={"limite": 0})).status_code == 422


async def test_la_actividad_exige_sesion(publico):
    assert (await publico.get("/api/spoolman/actividad")).status_code == 401


# ============================================================ colores de paleta (mismo tono)
def test_color_parecido_por_tono():
    from app.spoolman.asignacion import color_parecido

    assert color_parecido("#753bbd", "#443089")  # el violeta de Spoolman y el elegido en la impresora
    assert color_parecido("#ff0000", "#f01010")  # cercanos en RGB
    assert not color_parecido("#753bbd", "#ff0000")  # violeta vs rojo
    assert not color_parecido("#753bbd", "#2e7d32")  # violeta vs verde
    assert not color_parecido("#000000", "#443089")  # el negro solo cuenta por cercanía
    assert not color_parecido("#ffffff", "#808080")
    assert not color_parecido(None, "#443089")


async def test_el_mismo_rollo_con_otro_violeta_de_la_paleta_se_confirma_solo(spool, db):
    # Pasó de verdad: el Sunlu #753bbd se vinculó a la ranura cuando decía negro; luego se eligió
    # otro violeta (#443089) en Bambu Studio y el vínculo quedó «desactualizado».
    spool.agregar(1, nombre="Sunlu · PLA+ Violet", color="#753bbd", proveedor="Sunlu")
    db.add(RanuraBobina(ranura="2", spool_id=1, tipo="PLA", color="#000000"))
    await db.commit()
    _, s = await servicio_con(None, spool, sin_chip("2", color="443089FF"))
    await estable(s)
    v = (await vinculos(db))["2"]
    assert (v.spool_id, v.tipo, v.color) == (1, "PLA", "#443089")  # sigue siendo la 1, ya vigente
    (a,) = await auditorias(db, "spoolman_ranura_autovinculada")
    assert a.detalle["spool_id"] == 1


async def test_si_la_bobina_vinculada_ya_no_se_parece_no_se_confirma(spool, db):
    spool.agregar(1, nombre="Sunlu · PLA Rojo", color="#ff0000", proveedor="Sunlu")
    db.add(RanuraBobina(ranura="2", spool_id=1, tipo="PLA", color="#ff0000"))
    await db.commit()
    _, s = await servicio_con(None, spool, sin_chip("2", color="443089FF"))  # ahora hay un violeta
    await estable(s)
    v = (await vinculos(db))["2"]
    assert (v.spool_id, v.color) == (1, "#ff0000")  # el vínculo viejo se queda desactualizado
    assert await auditorias(db, "spoolman_ranura_autovinculada") == []


async def test_un_violeta_de_paleta_encuentra_a_la_unica_candidata_del_mismo_tono(spool, db):
    spool.agregar(1, nombre="Sunlu · PLA+ Violet", color="#753bbd", proveedor="Sunlu")
    spool.agregar(2, nombre="Sunlu · PLA Verde", color="#2e7d32", proveedor="Sunlu")
    _, s = await servicio_con(None, spool, sin_chip("1", color="443089FF"))
    await estable(s)
    assert (await vinculos(db))["1"].spool_id == 1
