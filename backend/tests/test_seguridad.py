"""Pruebas de regresión de la auditoría de seguridad (run-1): cada una cubre un registro
`needs_validation` o una nota de endurecimiento, y comprueba el comportamiento YA corregido."""

import asyncio
import io

import jwt
import pytest
from PIL import Image
from sqlalchemy import func, select

from app.config import Settings, settings
from app.core import imagenes
from app.core.cliente import _agrupar
from app.core.tokens import ALGORITMO
from app.models import Pedido, RegistroAuditoria
from app.seeds.create_admin import crear_o_actualizar
from tests.conftest import CSRF, EMAIL, PASSWORD, crear_articulo


# --- auth-password-reset-no-session-revocation -----------------------------------------------
async def test_reset_de_contrasena_cierra_todas_las_sesiones(admin):
    refresh = admin.cookies.get("mi_refresh")
    assert (await admin.get("/api/auth/yo")).status_code == 200

    await crear_o_actualizar(EMAIL, "NuevaContrasena-9876")  # recuperación del operador

    # El JWT de acceso que ya estaba emitido deja de valer al instante…
    assert (await admin.get("/api/auth/yo")).status_code == 401
    # …y el refresh robado ya no sirve para recuperar la sesión.
    admin.cookies.set("mi_refresh", refresh)
    assert (await admin.post("/api/auth/refresh")).status_code == 401


async def test_reutilizar_un_refresh_tambien_invalida_los_jwt_de_acceso(admin):
    viejo = admin.cookies.get("mi_refresh")
    assert (await admin.post("/api/auth/refresh")).status_code == 204  # rota
    assert (await admin.get("/api/auth/yo")).status_code == 200
    admin.cookies.set("mi_refresh", viejo)  # el token ya usado reaparece = robo
    assert (await admin.post("/api/auth/refresh")).status_code == 401
    # El JWT de acceso vigente (de la sesión legítima) también murió.
    admin.cookies.set("mi_refresh", "")
    assert (await admin.get("/api/auth/yo")).status_code == 401


async def test_refresh_fallido_borra_las_cookies(publico):
    publico.cookies.set("mi_refresh", "token-que-no-existe")
    r = await publico.post("/api/auth/refresh")
    assert r.status_code == 401
    borradas = " ".join(r.headers.get_list("set-cookie")).lower()
    assert "mi_refresh=" in borradas and "max-age=0" in borradas


async def test_jwt_sin_exp_se_rechaza(admin):
    sub = jwt.decode(admin.cookies.get("mi_access"), options={"verify_signature": False})["sub"]
    sin_exp = jwt.encode(
        {"sub": sub, "iat": 1, "typ": "access", "ver": 0}, settings.secret_key, algorithm=ALGORITMO
    )
    admin.cookies.set("mi_access", sin_exp)
    assert (await admin.get("/api/auth/yo")).status_code == 401


# --- auth-login-throttle-check-then-act-race -------------------------------------------------
async def test_ráfaga_de_logins_no_supera_el_limite_por_correo(publico):
    await crear_o_actualizar(EMAIL, PASSWORD)

    async def intento():
        return await publico.post(
            "/api/auth/login", json={"email": EMAIL, "password": "clave-equivocada-1"}
        )

    respuestas = await asyncio.gather(*[intento() for _ in range(24)])
    codigos = [r.status_code for r in respuestas]
    assert codigos.count(401) <= 5, codigos  # antes: la ráfaga las dejaba pasar casi todas
    assert codigos.count(429) >= 19


# --- publico-pedidos-cuota-carrera-sin-atomicidad --------------------------------------------
async def test_ráfaga_de_pedidos_no_supera_el_limite_por_origen(admin, publico, db):
    a = await crear_articulo(admin)
    cuerpo = {
        "articulo_id": a["id"],
        "nombre": "Ana Pérez",
        "whatsapp": "3001234567",
        "cantidad": 1,
    }
    respuestas = await asyncio.gather(
        *[publico.post("/api/publico/pedidos", json=cuerpo) for _ in range(20)]
    )
    creados = [r.status_code for r in respuestas].count(201)
    assert creados == 5
    assert (await db.execute(select(func.count()).select_from(Pedido))).scalar_one() == 5


# --- publico-pedidos-cuota-compartida-bloqueo-clientes (IPv6) ----------------------------------
def test_ipv6_se_agrupa_por_64():
    assert _agrupar("2001:db8:1:2:aaaa:bbbb:cccc:dddd") == _agrupar(
        "2001:db8:1:2:1111:2222:3333:4444"
    )
    assert _agrupar("2001:db8:1:2::1") != _agrupar("2001:db8:1:3::1")
    assert _agrupar("203.0.113.7") == "203.0.113.7"
    assert _agrupar("no-es-una-ip") == "no-es-una-ip"


# --- articulos-imagen-multipart-preauth-buffering --------------------------------------------
async def test_subida_enorme_sin_sesion_se_corta_antes_de_leerla(publico):
    grande = b"0" * ((settings.max_upload_mb + 2) * 1024 * 1024)
    r = await publico.put(
        "/api/articulos/00000000-0000-0000-0000-000000000000/imagen",
        files={"archivo": ("a.png", grande, "image/png")},
    )
    assert r.status_code == 413  # ni siquiera llegó a la autenticación (que daría 401)


async def test_cuerpo_chunked_sin_content_length_tambien_se_corta(publico):
    async def trozos():
        yield (
            b'--x\r\nContent-Disposition: form-data; name="archivo"; filename="a.png"\r\n'
            b"Content-Type: image/png\r\n\r\n"
        )
        for _ in range(settings.max_upload_mb + 3):
            yield b"0" * (1024 * 1024)

    r = await publico.put(
        "/api/articulos/00000000-0000-0000-0000-000000000000/imagen",
        content=trozos(),
        headers={"content-type": "multipart/form-data; boundary=x"},
    )
    assert r.status_code == 413


async def test_json_de_la_api_tiene_tope(admin):
    r = await admin.post("/api/articulos", json={"nombre": "x" * 400_000, "precio_venta": 1})
    assert r.status_code == 413


# --- hardening: cota estricta de píxeles ------------------------------------------------------
async def test_imagen_con_demasiados_pixeles_se_rechaza(admin, monkeypatch):
    monkeypatch.setattr(imagenes, "PIXELES_MAXIMOS", 1000)
    a = await crear_articulo(admin)
    b = io.BytesIO()
    Image.new("RGB", (100, 100), (1, 2, 3)).save(b, "PNG")  # 10 000 px > 1000
    r = await admin.put(
        f"/api/articulos/{a['id']}/imagen", files={"archivo": ("a.png", b.getvalue(), "image/png")}
    )
    assert r.status_code == 422 and "píxeles" in r.json()["detail"]


# --- hardening: auditoría de pedidos y configuración -----------------------------------------
async def test_cambiar_estado_de_pedido_queda_auditado(admin, publico, db):
    a = await crear_articulo(admin)
    await publico.post(
        "/api/publico/pedidos",
        json={
            "articulo_id": a["id"],
            "nombre": "Ana Pérez",
            "whatsapp": "3001234567",
            "cantidad": 1,
        },
    )
    pedido = (await admin.get("/api/pedidos")).json()[0]
    await admin.patch(f"/api/pedidos/{pedido['id']}", json={"estado": "contactado"})
    fila = (
        await db.execute(
            select(RegistroAuditoria).where(RegistroAuditoria.accion == "pedido_estado")
        )
    ).scalar_one()
    assert fila.detalle["antes"] == "nuevo" and fila.detalle["despues"] == "contactado"


def test_no_se_firma_con_la_clave_publica_detras_de_un_tunel():
    with pytest.raises(ValueError, match="SECRET_KEY vacía"):
        Settings(secret_key="", trust_proxy=True)
    with pytest.raises(ValueError, match="SECRET_KEY vacía"):
        Settings(secret_key="", proxy_shared_secret="x" * 20)
    Settings(secret_key="")  # desarrollo normal sigue funcionando


async def test_cabecera_csrf_sigue_siendo_obligatoria_en_login(publico):
    r = await publico.post(
        "/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        headers={"X-Requested-With": ""},
    )
    assert r.status_code == 403
    assert CSRF["X-Requested-With"] == "fetch"
