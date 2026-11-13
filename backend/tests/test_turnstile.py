"""Cloudflare Turnstile: el servidor decide (no el navegador) y falla cerrado."""

import httpx
import pytest

from app.config import settings
from app.core import turnstile
from app.seeds.create_admin import crear_o_actualizar
from tests.conftest import EMAIL, PASSWORD, crear_articulo


@pytest.fixture
def activo(monkeypatch):
    monkeypatch.setattr(settings, "turnstile_secretkey", "secreto-de-prueba")
    monkeypatch.setattr(settings, "turnstile_sitekey", "llave-publica-de-prueba")
    llamadas = []

    async def consultar(token, ip):
        llamadas.append((token, ip))
        return {"success": token == "token-bueno"}

    monkeypatch.setattr(turnstile, "_consultar", consultar)
    return llamadas


def pedido(articulo_id, **extra):
    return {
        "articulo_id": articulo_id,
        "nombre": "Ana Pérez",
        "whatsapp": "3001234567",
        "cantidad": 1,
        **extra,
    }


async def test_apagado_no_exige_nada(admin, publico):
    a = await crear_articulo(admin)
    assert (await publico.get("/api/publico/config")).json() == {"turnstile_sitekey": ""}
    assert (await publico.post("/api/publico/pedidos", json=pedido(a["id"]))).status_code == 201


async def test_la_config_publica_expone_solo_la_llave_publica(activo, publico):
    r = (await publico.get("/api/publico/config")).json()
    assert r == {"turnstile_sitekey": "llave-publica-de-prueba"}
    assert "secreto" not in str((await publico.get("/api/publico/articulos")).json())
    assert (await publico.get("/api/publico/articulos")).json()[
        "turnstile_sitekey"
    ] == "llave-publica-de-prueba"


async def test_pedido_exige_token_valido(admin, publico, activo):
    a = await crear_articulo(admin)
    sin = await publico.post("/api/publico/pedidos", json=pedido(a["id"]))
    malo = await publico.post("/api/publico/pedidos", json=pedido(a["id"], turnstile="token-falso"))
    assert sin.status_code == malo.status_code == 400
    bueno = await publico.post(
        "/api/publico/pedidos", json=pedido(a["id"], turnstile="token-bueno")
    )
    assert bueno.status_code == 201
    assert activo[-1][0] == "token-bueno"  # se consultó a Cloudflare con el token del cliente
    assert len((await admin.get("/api/pedidos")).json()) == 1  # los rechazados no se guardaron


async def test_login_exige_token_valido(activo, publico):
    await crear_o_actualizar(EMAIL, PASSWORD)
    cuerpo = {"email": EMAIL, "password": PASSWORD}
    assert (await publico.post("/api/auth/login", json=cuerpo)).status_code == 400
    assert (
        await publico.post("/api/auth/login", json={**cuerpo, "turnstile": "token-falso"})
    ).status_code == 400
    assert (
        await publico.post("/api/auth/login", json={**cuerpo, "turnstile": "token-bueno"})
    ).status_code == 200


async def test_si_cloudflare_no_responde_se_rechaza(monkeypatch, admin, publico):
    monkeypatch.setattr(settings, "turnstile_secretkey", "s")
    monkeypatch.setattr(settings, "turnstile_sitekey", "k")

    async def caido(token, ip):
        raise httpx.ConnectError("sin red")

    monkeypatch.setattr(turnstile, "_consultar", caido)
    a = await crear_articulo(admin)
    r = await publico.post("/api/publico/pedidos", json=pedido(a["id"], turnstile="token-bueno"))
    assert r.status_code == 503  # falla cerrado


async def test_el_robot_del_honeypot_no_gasta_verificaciones(admin, publico, activo):
    a = await crear_articulo(admin)
    r = await publico.post(
        "/api/publico/pedidos", json=pedido(a["id"], sitio_web="http://spam.example")
    )
    assert (
        r.status_code == 201 and activo == []
    )  # respondió «ok» sin llamar a Cloudflare ni guardar
