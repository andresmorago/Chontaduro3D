import pytest
from sqlalchemy import select

from app.models import SesionRefresh
from tests.conftest import CSRF, EMAIL, PASSWORD

RUTAS_PROTEGIDAS = [
    ("GET", "/api/articulos"),
    ("GET", "/api/inventario"),
    ("GET", "/api/ventas"),
    ("GET", "/api/produccion"),
    ("GET", "/api/pedidos"),
    ("GET", "/api/panel"),
    ("GET", "/api/auth/yo"),
    ("POST", "/api/articulos"),
    ("POST", "/api/ventas"),
]


@pytest.mark.parametrize(("metodo", "ruta"), RUTAS_PROTEGIDAS)
async def test_sin_sesion_no_hay_acceso(publico, metodo, ruta):
    r = await publico.request(metodo, ruta, json={} if metodo == "POST" else None)
    assert r.status_code == 401


async def test_login_correcto_y_cookies_httponly(publico, admin):
    r = await publico.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200
    cookies = r.headers.get_list("set-cookie")
    assert len(cookies) == 2
    assert all("httponly" in c.lower() and "samesite=lax" in c.lower() for c in cookies)
    assert (await publico.get("/api/auth/yo")).json()["email"] == EMAIL


async def test_login_incorrecto_no_distingue_usuario_de_clave(publico, admin):
    mala = await publico.post(
        "/api/auth/login", json={"email": EMAIL, "password": "otra-clave-xyz"}
    )
    inexistente = await publico.post(
        "/api/auth/login", json={"email": "nadie@x.co", "password": "otra-clave-xyz"}
    )
    assert mala.status_code == inexistente.status_code == 401
    assert mala.json() == inexistente.json()


async def test_limite_de_intentos(publico, admin):
    for _ in range(5):
        r = await publico.post(
            "/api/auth/login", json={"email": EMAIL, "password": "mala-clave-123"}
        )
        assert r.status_code == 401
    # Aun con la clave correcta, el correo quedó bloqueado un rato.
    r = await publico.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 429


async def test_mutaciones_exigen_cabecera_csrf(admin):
    r = await admin.post(
        "/api/articulos",
        json={"nombre": "X", "precio_venta": 1},
        headers={"X-Requested-With": ""},
    )
    assert r.status_code == 403


async def test_refresh_rota_y_detecta_reutilizacion(admin, db):
    viejo = admin.cookies.get("mi_refresh")
    assert (await admin.post("/api/auth/refresh")).status_code == 204
    nuevo = admin.cookies.get("mi_refresh")
    assert nuevo != viejo

    # Presentar el token ya usado = robo: se cierran TODAS las sesiones.
    admin.cookies.set("mi_refresh", viejo)
    assert (await admin.post("/api/auth/refresh")).status_code == 401
    activas = (
        await db.execute(select(SesionRefresh).where(SesionRefresh.revocada.is_(False)))
    ).all()
    assert activas == []


async def test_logout_revoca_la_sesion(admin):
    assert (await admin.post("/api/auth/logout")).status_code == 204
    assert (await admin.post("/api/auth/refresh", headers=CSRF)).status_code == 401
    assert (await admin.get("/api/articulos")).status_code == 401


async def test_token_de_acceso_manipulado_se_rechaza(publico):
    publico.cookies.set("mi_access", "no.es.un.jwt")
    assert (await publico.get("/api/articulos")).status_code == 401
