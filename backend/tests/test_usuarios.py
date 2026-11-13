"""Módulo de administración: usuarios y contraseñas (sin roles por ahora)."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.models import RegistroAuditoria
from tests.conftest import CSRF, EMAIL, PASSWORD

NUEVO = {"nombre": "Luisa Gómez", "email": "luisa@ejemplo.co", "password": "ClaveSegura-2468"}


@pytest.fixture
async def otro():
    """Cliente aparte (otra «persona»)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=CSRF
    ) as c:
        yield c


async def entrar(c, email, password):
    return await c.post("/api/auth/login", json={"email": email, "password": password})


async def test_requiere_sesion(publico):
    for metodo, ruta in (
        ("GET", "/api/usuarios"), ("POST", "/api/usuarios"),
        ("POST", "/api/usuarios/yo/contrasena"),
        ("PATCH", "/api/usuarios/00000000-0000-0000-0000-000000000000"),
        ("POST", "/api/usuarios/00000000-0000-0000-0000-000000000000/contrasena"),
    ):  # fmt: skip
        r = await publico.request(metodo, ruta, json={} if metodo != "GET" else None)
        assert r.status_code == 401, (metodo, ruta)


async def test_crear_usuario_y_entrar_con_el(admin, otro):
    r = await admin.post("/api/usuarios", json=NUEVO)
    assert r.status_code == 201
    u = r.json()
    assert (
        u["email"] == "luisa@ejemplo.co"
        and u["nombre"] == "Luisa Gómez"
        and u["activo"]
        and not u["es_yo"]
    )
    assert "password" not in str(u) and "hash" not in str(u)
    assert (await entrar(otro, NUEVO["email"], NUEVO["password"])).status_code == 200
    assert (await otro.get("/api/auth/yo")).json()["nombre"] == "Luisa Gómez"
    lista = (await admin.get("/api/usuarios")).json()
    assert [x["es_yo"] for x in lista].count(True) == 1 and len(lista) == 2


async def test_el_correo_es_unico_sin_importar_mayusculas(admin):
    assert (await admin.post("/api/usuarios", json=NUEVO)).status_code == 201
    r = await admin.post("/api/usuarios", json={**NUEVO, "email": "LUISA@Ejemplo.co"})
    assert r.status_code == 409
    assert (
        await admin.post("/api/usuarios", json={**NUEVO, "email": EMAIL.upper()})
    ).status_code == 409


async def test_validaciones_de_alta(admin):
    for malo in (
        {**NUEVO, "password": "corta1"}, {**NUEVO, "password": "1234567890123"},
        {**NUEVO, "password": NUEVO["email"]}, {**NUEVO, "email": "no-es-correo"},
        {**NUEVO, "nombre": ""}, {**NUEVO, "extra": 1},
    ):  # fmt: skip
        assert (await admin.post("/api/usuarios", json=malo)).status_code == 422, malo


async def test_cambiar_mi_contrasena_cierra_las_demas_sesiones_pero_no_la_mia(admin, otro):
    # Dos equipos con la misma cuenta.
    assert (await entrar(otro, EMAIL, PASSWORD)).status_code == 200
    r = await admin.post(
        "/api/usuarios/yo/contrasena", json={"actual": PASSWORD, "nueva": "OtraClaveNueva-7788"}
    )
    assert r.status_code == 204
    assert (await admin.get("/api/auth/yo")).status_code == 200  # este equipo sigue dentro
    assert (await otro.get("/api/auth/yo")).status_code == 401  # el otro quedó fuera
    assert (await entrar(otro, EMAIL, PASSWORD)).status_code == 401  # la vieja ya no entra
    assert (await entrar(otro, EMAIL, "OtraClaveNueva-7788")).status_code == 200


async def test_cambiar_mi_contrasena_pide_la_actual_y_la_limita(admin):
    ruta = "/api/usuarios/yo/contrasena"
    mala = await admin.post(ruta, json={"actual": "no-es-esa-123", "nueva": "OtraClaveNueva-7788"})
    assert mala.status_code == 400
    assert (await admin.post(ruta, json={"actual": PASSWORD, "nueva": PASSWORD})).status_code == 422
    assert (await admin.post(ruta, json={"actual": PASSWORD, "nueva": "corta"})).status_code == 422
    for _ in range(4):
        await admin.post(ruta, json={"actual": "no-es-esa-123", "nueva": "OtraClaveNueva-7788"})
    # Tras 5 fallos ni la contraseña correcta pasa (evita adivinarla desde una sesión robada).
    assert (
        await admin.post(ruta, json={"actual": PASSWORD, "nueva": "OtraClaveNueva-7788"})
    ).status_code == 429


async def test_restablecer_la_contrasena_de_otro_cierra_sus_sesiones(admin, otro):
    nuevo = (await admin.post("/api/usuarios", json=NUEVO)).json()
    assert (await entrar(otro, NUEVO["email"], NUEVO["password"])).status_code == 200
    r = await admin.post(
        f"/api/usuarios/{nuevo['id']}/contrasena", json={"nueva": "ClaveRestablecida-135"}
    )
    assert r.status_code == 204
    assert (await otro.get("/api/auth/yo")).status_code == 401
    assert (await entrar(otro, NUEVO["email"], NUEVO["password"])).status_code == 401
    assert (await entrar(otro, NUEVO["email"], "ClaveRestablecida-135")).status_code == 200


async def test_restablecer_valida_y_no_aplica_a_uno_mismo(admin):
    yo = next(u for u in (await admin.get("/api/usuarios")).json() if u["es_yo"])
    nuevo = (await admin.post("/api/usuarios", json=NUEVO)).json()
    assert (
        await admin.post(
            f"/api/usuarios/{yo['id']}/contrasena", json={"nueva": "OtraClaveNueva-7788"}
        )
    ).status_code == 400
    assert (
        await admin.post(f"/api/usuarios/{nuevo['id']}/contrasena", json={"nueva": "corta"})
    ).status_code == 422
    assert (
        await admin.post(
            "/api/usuarios/00000000-0000-0000-0000-000000000000/contrasena",
            json={"nueva": "OtraClaveNueva-7788"},
        )
    ).status_code == 404


async def test_desactivar_corta_el_acceso_al_instante_y_se_puede_reactivar(admin, otro):
    nuevo = (await admin.post("/api/usuarios", json=NUEVO)).json()
    assert (await entrar(otro, NUEVO["email"], NUEVO["password"])).status_code == 200
    r = await admin.patch(f"/api/usuarios/{nuevo['id']}", json={"activo": False})
    assert r.status_code == 200 and r.json()["activo"] is False
    assert (
        await otro.get("/api/auth/yo")
    ).status_code == 401  # su sesión murió ya, no a los 15 min
    assert (await entrar(otro, NUEVO["email"], NUEVO["password"])).status_code == 401
    assert (await admin.patch(f"/api/usuarios/{nuevo['id']}", json={"activo": True})).json()[
        "activo"
    ] is True
    assert (await entrar(otro, NUEVO["email"], NUEVO["password"])).status_code == 200


async def test_no_se_puede_desactivar_a_uno_mismo_ni_al_ultimo(admin):
    yo = next(u for u in (await admin.get("/api/usuarios")).json() if u["es_yo"])
    assert (
        await admin.patch(f"/api/usuarios/{yo['id']}", json={"activo": False})
    ).status_code == 409
    assert (await admin.get("/api/auth/yo")).status_code == 200


async def test_el_ultimo_usuario_activo_no_puede_desactivarse(admin, otro):
    nuevo = (await admin.post("/api/usuarios", json=NUEVO)).json()
    yo = next(u for u in (await admin.get("/api/usuarios")).json() if u["es_yo"])
    await entrar(otro, NUEVO["email"], NUEVO["password"])
    await admin.patch(f"/api/usuarios/{nuevo['id']}", json={"activo": False})
    # Queda un solo activo (el admin): nadie puede desactivarlo, ni él a sí mismo.
    assert (
        await admin.patch(f"/api/usuarios/{yo['id']}", json={"activo": False})
    ).status_code == 409


async def test_editar_el_nombre(admin):
    nuevo = (await admin.post("/api/usuarios", json=NUEVO)).json()
    r = await admin.patch(f"/api/usuarios/{nuevo['id']}", json={"nombre": "  Luisa G.  "})
    assert r.status_code == 200 and r.json()["nombre"] == "Luisa G."
    assert (
        await admin.patch(f"/api/usuarios/{nuevo['id']}", json={"nombre": ""})
    ).status_code == 422
    assert (
        await admin.patch(
            "/api/usuarios/00000000-0000-0000-0000-000000000000", json={"nombre": "x"}
        )
    ).status_code == 404


async def test_las_acciones_quedan_auditadas_sin_secretos(admin, db):
    nuevo = (await admin.post("/api/usuarios", json=NUEVO)).json()
    await admin.post(
        f"/api/usuarios/{nuevo['id']}/contrasena", json={"nueva": "ClaveRestablecida-135"}
    )
    await admin.patch(f"/api/usuarios/{nuevo['id']}", json={"activo": False})
    acciones = {
        f.accion: f
        for f in (
            await db.execute(
                select(RegistroAuditoria).where(
                    RegistroAuditoria.accion.like("usuario_%")
                    | RegistroAuditoria.accion.like("contrasena_%")
                )
            )
        ).scalars()
    }
    assert {"usuario_creado", "contrasena_restablecida", "usuario_desactivado"} <= set(acciones)
    assert "ClaveSegura" not in str([a.detalle for a in acciones.values()])
    assert "ClaveRestablecida" not in str([a.detalle for a in acciones.values()])
