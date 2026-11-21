"""Producción ↔ Spoolman: cada línea de filamento de un lote puede apuntar a una bobina."""

import pytest

from app.config import settings
from app.main import app
from app.spoolman.dependencia import cliente_spoolman_opcional
from tests.conftest import crear_articulo
from tests.test_spoolman import AZUL, ROJO, FalsoSpoolman


@pytest.fixture
def spool(monkeypatch):
    """Spoolman de mentira conectado al backend web."""
    falso = FalsoSpoolman()
    monkeypatch.setattr(settings, "spoolman_url", "http://spoolman:8000")

    async def dependencia():
        yield falso

    app.dependency_overrides[cliente_spoolman_opcional] = dependencia
    yield falso
    app.dependency_overrides.pop(cliente_spoolman_opcional, None)


async def lote(admin, filamentos, *, articulo=None, **extra):
    a = articulo or await crear_articulo(admin, nombre="Llavero")
    cuerpo = {"items": [{"articulo_id": a["id"], "cantidad": 2}], "filamentos": filamentos, **extra}
    return await admin.post("/api/produccion", json=cuerpo)


async def listado(admin):
    r = await admin.get("/api/produccion")
    assert r.status_code == 200, r.text
    return r.json()


async def test_la_linea_con_bobina_toma_su_nombre_y_color_de_spoolman(admin, spool):
    spool.agregar(7, nombre="Bambu Lab · Basic Red", color=ROJO)
    r = await lote(admin, [{"spool_id": 7, "gramos": 24.5}])
    assert r.status_code == 201, r.text
    (f,) = r.json()["filamentos"]
    assert (f["spool_id"], f["gramos"], f["descripcion"]) == (7, 24.5, "Bambu Lab · Basic Red")
    assert (f["bobina"], f["color"]) == ("Bambu Lab · Basic Red", ROJO)
    assert r.json()["gramos_total"] == 24.5


async def test_el_texto_libre_sigue_funcionando_con_o_sin_spoolman(admin, spool, monkeypatch):
    r = await lote(admin, [{"descripcion": "PLA Fucsia", "gramos": 10}])
    assert r.status_code == 201, r.text
    (f,) = r.json()["filamentos"]
    assert (f["descripcion"], f["spool_id"], f["bobina"]) == ("PLA Fucsia", None, None)
    monkeypatch.setattr(settings, "spoolman_url", "")  # Spoolman apagado
    app.dependency_overrides.pop(cliente_spoolman_opcional)
    assert (await lote(admin, [{"descripcion": "PLA Blanco", "gramos": 5}])).status_code == 201
    assert len(await listado(admin)) == 2


async def test_una_bobina_que_no_existe_se_rechaza(admin, spool):
    spool.agregar(7)
    r = await lote(admin, [{"spool_id": 99, "gramos": 5}])
    assert r.status_code == 422 and "n.º 99" in r.json()["detail"]
    assert await listado(admin) == []  # no quedó ningún lote a medias


async def test_elegir_una_bobina_sin_spoolman_conectado_se_rechaza(admin, monkeypatch):
    monkeypatch.setattr(settings, "spoolman_url", "")
    r = await lote(admin, [{"spool_id": 7, "gramos": 5}])
    assert r.status_code == 422 and "Spoolman no está conectado" in r.json()["detail"]


async def test_una_bobina_archivada_se_puede_citar(admin, spool):
    spool.archivadas["AABBCCDD00112233"] = 55  # un rollo terminado y archivado
    assert (await lote(admin, [{"spool_id": 55, "gramos": 8}])).status_code == 201


async def test_si_spoolman_no_responde_no_se_guarda_pero_el_listado_sigue(admin, spool):
    spool.agregar(7, nombre="Bambu Lab · Basic Red", color=ROJO)
    assert (await lote(admin, [{"spool_id": 7, "gramos": 24.5}])).status_code == 201
    spool.caido = True
    r = await lote(admin, [{"spool_id": 7, "gramos": 1}])
    assert r.status_code == 502 and "Spoolman" in r.json()["detail"]
    (p,) = await listado(admin)  # el historial se ve igual, con el nombre que se guardó
    (f,) = p["filamentos"]
    assert (f["descripcion"], f["bobina"], f["color"]) == ("Bambu Lab · Basic Red", None, None)


async def test_si_la_bobina_se_renombra_en_spoolman_el_lote_muestra_el_nombre_nuevo(admin, spool):
    spool.agregar(7, nombre="Bambu Lab · PLA Basic", color=ROJO)
    assert (await lote(admin, [{"spool_id": 7, "gramos": 24.5}])).status_code == 201
    from app.spoolman.cliente import Bobina

    viejo = spool.bobinas_[7]
    spool.bobinas_[7] = Bobina(**{**viejo.__dict__, "nombre": "Bambu Lab · Basic Red"})
    (f,) = (await listado(admin))[0]["filamentos"]
    assert f["bobina"] == "Bambu Lab · Basic Red"  # el vivo
    assert f["descripcion"] == "Bambu Lab · PLA Basic"  # la copia de cuando se guardó


async def test_corregir_un_lote_viejo_no_exige_que_su_bobina_siga_existiendo(admin, spool):
    spool.agregar(7, nombre="Bambu Lab · Basic Red", color=ROJO).agregar(8, color=AZUL)
    a = await crear_articulo(admin, nombre="Maceta")
    creado = (await lote(admin, [{"spool_id": 7, "gramos": 24.5}], articulo=a)).json()
    spool.bobinas_.pop(7)  # la persona borró la bobina en Spoolman
    cuerpo = {
        "items": [{"articulo_id": a["id"], "cantidad": 2}],
        "filamentos": [{"spool_id": 7, "gramos": 30}],  # corrige los gramos; sin texto
        "nota": "corregido",
    }
    r = await admin.put(f"/api/produccion/{creado['id']}", json=cuerpo)
    assert r.status_code == 200, r.text
    (f,) = r.json()["filamentos"]
    assert (f["gramos"], f["spool_id"], f["descripcion"], f["bobina"]) == (
        30, 7, "Bambu Lab · Basic Red", None,  # conserva el nombre que ya tenía
    )  # fmt: skip
    # Pero una bobina NUEVA inexistente sigue rechazándose al editar.
    cuerpo["filamentos"] = [{"spool_id": 99, "gramos": 30}]
    assert (await admin.put(f"/api/produccion/{creado['id']}", json=cuerpo)).status_code == 422
    # Y cambiarla por otra que sí existe funciona.
    cuerpo["filamentos"] = [{"spool_id": 8, "gramos": 12}]
    r = await admin.put(f"/api/produccion/{creado['id']}", json=cuerpo)
    assert r.status_code == 200 and r.json()["filamentos"][0]["spool_id"] == 8


async def test_el_listado_pide_los_nombres_a_spoolman_una_sola_vez(admin, spool, monkeypatch):
    spool.agregar(7, nombre="Bambu Lab · Basic Red", color=ROJO)
    for _ in range(3):
        assert (await lote(admin, [{"spool_id": 7, "gramos": 5}])).status_code == 201
    llamadas = []
    original = spool.bobinas

    async def contada(*a, **k):
        llamadas.append(1)
        return await original(*a, **k)

    monkeypatch.setattr(spool, "bobinas", contada)
    assert len(await listado(admin)) == 3
    assert len(llamadas) == 1


# ----------------------------------------------------------------- costo del filamento
async def test_el_costo_del_filamento_sale_del_precio_del_rollo(admin, spool):
    spool.agregar(7, precio=60000.0).agregar(8, nombre="Sunlu", precio=40000.0)  # 60 y 40 por g
    r = await lote(admin, [{"spool_id": 7, "gramos": 24.5}, {"spool_id": 8, "gramos": 10}])
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert [f["costo"] for f in cuerpo["filamentos"]] == [1470.0, 400.0]
    assert cuerpo["costo_filamento"] == 1870.0 and cuerpo["costo_filamento_parcial"] is False


async def test_si_una_linea_no_tiene_precio_el_costo_es_parcial(admin, spool):
    spool.agregar(7, precio=60000.0).agregar(8, precio=None)
    r = await lote(
        admin,
        [{"spool_id": 7, "gramos": 10}, {"spool_id": 8, "gramos": 10}, {"descripcion": "PLA", "gramos": 5}],
    )
    cuerpo = r.json()
    assert [f["costo"] for f in cuerpo["filamentos"]] == [600.0, None, None]
    assert cuerpo["costo_filamento"] == 600.0 and cuerpo["costo_filamento_parcial"] is True
    sin = await lote(admin, [{"descripcion": "PLA Fucsia", "gramos": 10}])
    assert sin.json()["costo_filamento"] is None and sin.json()["costo_filamento_parcial"] is False


async def test_el_costo_se_congela_aunque_el_precio_cambie_despues(admin, spool):
    from app.spoolman.cliente import Bobina

    spool.agregar(7, precio=60000.0)
    a = await crear_articulo(admin, nombre="Maceta")
    creado = (await lote(admin, [{"spool_id": 7, "gramos": 10}], articulo=a)).json()
    viejo = spool.bobinas_[7]
    spool.bobinas_[7] = Bobina(**{**viejo.__dict__, "precio": 90000.0})  # subió el rollo
    (p,) = await listado(admin)
    assert p["costo_filamento"] == 600.0  # el lote conserva el precio de cuando se hizo
    # Corregir otra cosa del lote no lo recalcula; cambiar los gramos sí, con el precio de hoy.
    cuerpo = {"items": [{"articulo_id": a["id"], "cantidad": 2}], "filamentos": [{"spool_id": 7, "gramos": 10}],
              "nota": "x"}  # fmt: skip
    r = await admin.put(f"/api/produccion/{creado['id']}", json=cuerpo)
    assert r.json()["costo_filamento"] == 600.0
    cuerpo["filamentos"] = [{"spool_id": 7, "gramos": 20}]
    r = await admin.put(f"/api/produccion/{creado['id']}", json=cuerpo)
    assert r.json()["costo_filamento"] == 1800.0
