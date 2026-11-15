"""Administración → Conexión: configurar la impresora y vincular Bambu Cloud desde el panel."""

import json
from datetime import timedelta

import pytest
from sqlalchemy import select, text

from app.api import impresora_conexion
from app.core import secretos
from app.core.tokens import ahora
from app.impresora import ajustes, nube_login
from app.impresora.nube import Sesion
from app.models import ConfigImpresora, EstadoImpresora, RegistroAuditoria

BUENA = {"ip": "10.0.4.244", "serial": "03919d550007e91", "codigo_acceso": "12345678"}
URL = "/api/impresora/conexion"


async def fila(db) -> ConfigImpresora:
    db.expire_all()
    return await db.get(ConfigImpresora, 1)


# ---------------------------------------------------------------------------- cifrado
def test_cifrado_ida_y_vuelta_y_no_deja_el_texto_en_claro():
    c = secretos.cifrar("12345678")
    assert "12345678" not in c and secretos.descifrar(c) == "12345678"
    assert secretos.descifrar(None) is None and secretos.descifrar("basura") is None


# ------------------------------------------------------------------------ impresora
async def test_hay_que_iniciar_sesion(publico):
    assert (await publico.get(URL)).status_code == 401
    assert (await publico.put(URL, json=BUENA)).status_code == 401


async def test_vacia_al_principio(admin):
    j = (await admin.get(URL)).json()
    assert j["ip"] is None and j["codigo_guardado"] is False and j["nube"]["vinculada"] is False


async def test_guardar_cifra_el_codigo_y_nunca_lo_devuelve(admin, db):
    r = await admin.put(URL, json=BUENA)
    assert r.status_code == 200, r.text
    assert "12345678" not in r.text and "codigo_acceso" not in r.json()
    j = r.json()
    assert (j["ip"], j["serial"], j["codigo_guardado"]) == (
        "10.0.4.244", "03919D550007E91", True,
    )  # fmt: skip
    f = await fila(db)
    assert f.codigo_acceso != "12345678" and secretos.descifrar(f.codigo_acceso) == "12345678"
    assert (
        await db.execute(text("SELECT codigo_acceso FROM impresora_config"))
    ).scalar() != "12345678"
    auditoria = (await db.execute(select(RegistroAuditoria))).scalars().all()
    assert any(a.accion == "impresora_conexion" for a in auditoria)
    assert "12345678" not in json.dumps([a.detalle for a in auditoria])


async def test_cambiar_ip_conserva_el_codigo_y_sube_la_version(admin, db):
    await admin.put(URL, json=BUENA)
    v1 = (await fila(db)).version
    r = await admin.put(URL, json={"ip": "192.168.1.9", "serial": BUENA["serial"]})
    assert r.status_code == 200, r.text
    f = await fila(db)
    assert f.ip == "192.168.1.9" and f.version == v1 + 1
    assert secretos.descifrar(f.codigo_acceso) == "12345678"


async def test_la_primera_vez_exige_el_codigo(admin):
    r = await admin.put(URL, json={"ip": "10.0.4.244", "serial": BUENA["serial"]})
    assert r.status_code == 422 and "código de acceso" in r.text


@pytest.mark.parametrize(
    "malo",
    [
        {"ip": "8.8.8.8"},  # de internet
        {"ip": "127.0.0.1"},
        {"ip": "169.254.169.254"},
        {"ip": "0.0.0.0"},
        {"ip": "impresora.local"},
        {"serial": "ab/cd#12345678"},  # no puede colar comodines MQTT
        {"serial": "corto"},
        {"codigo_acceso": "con espacio"},
        {"extra": 1},
    ],
)
async def test_rechaza_datos_peligrosos_o_mal_formados(admin, malo):
    r = await admin.put(URL, json={**BUENA, **malo})
    assert r.status_code == 422, r.text


async def test_acepta_ips_de_vpn(admin):
    for ip in ("10.0.4.244", "172.16.5.4", "192.168.0.7", "100.64.1.2"):
        assert (await admin.put(URL, json={**BUENA, "ip": ip})).status_code == 200, ip


async def test_pendiente_hasta_que_el_servicio_aplica_la_version(admin, db):
    await admin.put(URL, json=BUENA)
    assert (await admin.get(URL)).json()["pendiente"] is True
    f = await fila(db)
    db.add(EstadoImpresora(id=1, conectada=True, config_version=f.version,
                           actualizado_en=ahora(), datos={"estado": "lista"}))  # fmt: skip
    await db.commit()
    j = (await admin.get(URL)).json()
    assert j["pendiente"] is False and j["conectada"] is True and j["servicio_activo"] is True


async def test_informa_por_que_no_conecta(admin, db):
    await admin.put(URL, json=BUENA)
    f = await fila(db)
    db.add(EstadoImpresora(id=1, conectada=False, config_version=f.version,
                           conexion_error="credenciales", actualizado_en=ahora()))  # fmt: skip
    await db.commit()
    assert (await admin.get(URL)).json()["error"] == "credenciales"


async def test_con_otra_secret_key_se_marca_ilegible(admin, db):
    await admin.put(URL, json=BUENA)
    f = await fila(db)
    f.codigo_acceso = "texto-que-no-se-puede-descifrar"
    await db.commit()
    j = (await admin.get(URL)).json()
    assert j["ilegible"] is True
    # y se puede volver a escribir
    assert (await admin.put(URL, json=BUENA)).status_code == 200


# ---------------------------------------------------------------------- Bambu Cloud
class FalsoLogin:
    def __init__(self, resultado=None, error=None):
        self.resultado, self.error, self.llamadas = resultado, error, []

    async def entrar(self, correo, clave):
        self.llamadas.append(("entrar", correo))
        if self.error:
            raise self.error
        return self.resultado

    async def verificar_codigo(self, correo, codigo):
        self.llamadas.append(("codigo", correo, codigo))
        if self.error:
            raise self.error
        return self.resultado

    async def verificar_tfa(self, llave, codigo):
        self.llamadas.append(("tfa", llave, codigo))
        return self.resultado


def con_login(monkeypatch, falso):
    monkeypatch.setattr(impresora_conexion, "login_nube", lambda: falso)
    return falso


LISTO = nube_login.Resultado("listo", Sesion("tok-" + "a" * 30, "ref-1", 0))


async def test_entrar_con_clave_guarda_solo_el_token(admin, db, monkeypatch):
    falso = con_login(monkeypatch, FalsoLogin(LISTO))
    r = await admin.post(f"{URL}/nube/entrar", json={"correo": "a@b.co", "clave": "Secreta-123!"})
    assert r.status_code == 200 and r.json() == {"paso": "listo", "tfa_key": None}
    f = await fila(db)
    sesion = ajustes.sesion_de(f)
    assert sesion.access_token.startswith("tok-") and sesion.refresh_token == "ref-1"
    assert f.nube_correo == "a@b.co" and f.nube_solicitada_en is not None
    # la contraseña no queda en ningún lado
    volcado = json.dumps(
        (await db.execute(text("SELECT row_to_json(c) FROM impresora_config c"))).scalar()
    )
    assert "Secreta-123!" not in volcado and "tok-" not in volcado  # el token va cifrado
    assert "Secreta-123!" not in json.dumps(
        [a.detalle for a in (await db.execute(select(RegistroAuditoria))).scalars()]
    )
    assert falso.llamadas == [("entrar", "a@b.co")]
    j = (await admin.get(URL)).json()["nube"]
    assert j["vinculada"] is True and j["correo"] == "a@b.co" and j["pendiente"] is True
    assert "token" not in json.dumps(j)


async def test_entrar_con_codigo_por_correo_en_dos_pasos(admin, db, monkeypatch):
    falso = con_login(monkeypatch, FalsoLogin(nube_login.Resultado("codigo")))
    r = await admin.post(f"{URL}/nube/entrar", json={"correo": "a@b.co", "clave": "Secreta-123!"})
    assert r.json()["paso"] == "codigo" and (await fila(db)) is None  # aún nada guardado
    falso.resultado = LISTO
    r = await admin.post(f"{URL}/nube/verificar", json={"correo": "a@b.co", "codigo": "123456"})
    assert r.status_code == 200 and r.json()["paso"] == "listo"
    assert ajustes.sesion_de(await fila(db)) is not None
    assert falso.llamadas[-1] == ("codigo", "a@b.co", "123456")


async def test_entrar_con_2fa(admin, monkeypatch):
    falso = con_login(monkeypatch, FalsoLogin(nube_login.Resultado("tfa", tfa_key="llave-1")))
    r = await admin.post(f"{URL}/nube/entrar", json={"correo": "a@b.co", "clave": "Secreta-123!"})
    assert r.json() == {"paso": "tfa", "tfa_key": "llave-1"}
    falso.resultado = LISTO
    r = await admin.post(f"{URL}/nube/verificar", json={"tfa_key": "llave-1", "codigo": "654321"})
    assert r.json()["paso"] == "listo" and falso.llamadas[-1] == ("tfa", "llave-1", "654321")


async def test_verificar_pide_correo_o_llave_pero_no_ambos(admin, monkeypatch):
    con_login(monkeypatch, FalsoLogin(LISTO))
    assert (await admin.post(f"{URL}/nube/verificar", json={"codigo": "123456"})).status_code == 422
    r = await admin.post(
        f"{URL}/nube/verificar", json={"codigo": "123456", "correo": "a@b.co", "tfa_key": "llave"}
    )
    assert r.status_code == 422


async def test_clave_mala_da_un_error_claro_y_no_guarda(admin, db, monkeypatch):
    con_login(
        monkeypatch, FalsoLogin(error=nube_login.ErrorLogin("Bambu no aceptó la clave (401)."))
    )
    r = await admin.post(f"{URL}/nube/entrar", json={"correo": "a@b.co", "clave": "mala"})
    assert r.status_code == 400 and "no aceptó" in r.json()["detail"]
    assert "mala" not in r.text and (await fila(db)) is None


async def test_la_clave_no_se_repite_en_los_errores_de_validacion(admin):
    r = await admin.post(f"{URL}/nube/entrar", json={"correo": "a@b.co", "clave": "", "x": 1})
    assert r.status_code == 422
    r = await admin.post(
        f"{URL}/nube/entrar", json={"correo": "a@b.co", "clave": "Secreta-123!", "x": 1}
    )
    assert r.status_code == 422 and "Secreta-123!" not in r.text


async def test_pegar_token(admin, db):
    r = await admin.post(f"{URL}/nube/token", json={"token": "token=" + "b" * 40})
    assert r.status_code == 200
    assert ajustes.sesion_de(await fila(db)).access_token == "b" * 40
    assert (
        await admin.post(f"{URL}/nube/token", json={"token": "corto con espacios aaaaaaaa"})
    ).status_code == 422


async def test_sincronizar_exige_cuenta_vinculada_y_pide_al_servicio(admin, db):
    assert (await admin.post(f"{URL}/nube/sincronizar")).status_code == 409
    await admin.post(f"{URL}/nube/token", json={"token": "c" * 40})
    f = await fila(db)
    f.nube_solicitada_en = ahora() - timedelta(minutes=5)
    await db.commit()
    db.add(
        EstadoImpresora(
            id=1, actualizado_en=ahora(), nube_atendida_en=ahora() - timedelta(minutes=1)
        )
    )
    await db.commit()
    assert (await admin.get(URL)).json()["nube"]["pendiente"] is False
    r = await admin.post(f"{URL}/nube/sincronizar")
    assert r.status_code == 202 and r.json()["nube"]["pendiente"] is True


async def test_desvincular_borra_el_token(admin, db):
    await admin.post(f"{URL}/nube/token", json={"token": "d" * 40})
    r = await admin.delete(f"{URL}/nube")
    assert r.status_code == 200 and r.json()["nube"]["vinculada"] is False
    f = await fila(db)
    assert f.nube_sesion is None and f.nube_correo is None


async def test_la_nube_exige_sesion_y_cabecera(publico, admin):
    assert (await publico.post(f"{URL}/nube/token", json={"token": "e" * 40})).status_code == 401
    sin = admin.headers.pop("X-Requested-With")
    try:
        assert (await admin.delete(f"{URL}/nube")).status_code == 403
    finally:
        admin.headers["X-Requested-With"] = sin
