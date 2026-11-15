"""Pruebas contra un Postgres real y desechable (servicio tests-db de compose).

Nunca contra la base de datos de desarrollo o producción: el docker-compose
fija DATABASE_URL a `misimpresiones_test`, en tmpfs, solo bajo el perfil `test`.
"""

import os
import subprocess
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

assert os.environ.get("APP_ENV") == "test", "Las pruebas solo corren con APP_ENV=test (make test)."
assert "misimpresiones_test" in os.environ["DATABASE_URL"], "La BD de pruebas debe ser desechable."

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seeds.create_admin import crear_o_actualizar  # noqa: E402

EMAIL = os.environ["ADMIN_EMAIL"]
PASSWORD = os.environ["ADMIN_PASSWORD"]
CSRF = {"X-Requested-With": "fetch"}


@pytest.fixture(scope="session", autouse=True)
def esquema():
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)


@pytest_asyncio.fixture(autouse=True)
async def limpiar(esquema):
    async with engine.begin() as c:
        await c.execute(
            text(
                "TRUNCATE usuarios, articulos, producciones, ventas, pedidos, registro_auditoria, "
                "impresora_estado, impresora_config "
                "RESTART IDENTITY CASCADE"
            )
        )
        await c.execute(text("ALTER SEQUENCE articulos_codigo_seq RESTART WITH 1"))
        await c.execute(
            text("UPDATE parametros SET precio_kwh = NULL, potencia_impresora_w = NULL")
        )
    yield


@pytest_asyncio.fixture
async def publico():
    """Cliente sin sesión."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=CSRF
    ) as c:
        yield c


@pytest_asyncio.fixture
async def admin():
    """Cliente con la sesión del administrador abierta."""
    await crear_o_actualizar(EMAIL, PASSWORD)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=CSRF
    ) as c:
        r = await c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        assert r.status_code == 200, r.text
        yield c


async def crear_articulo(c: AsyncClient, nombre="Llavero", precio=6000, **extra) -> dict:
    r = await c.post("/api/articulos", json={"nombre": nombre, "precio_venta": precio, **extra})
    assert r.status_code == 201, r.text
    return r.json()


async def producir(c: AsyncClient, articulo_id: str, cantidad: int) -> None:
    r = await c.post(
        "/api/produccion", json={"items": [{"articulo_id": articulo_id, "cantidad": cantidad}]}
    )
    assert r.status_code == 201, r.text


async def stock(c: AsyncClient, articulo_id: str) -> int:
    r = await c.get(f"/api/articulos/{articulo_id}")
    assert r.status_code == 200, r.text
    return r.json()["stock"]


@pytest_asyncio.fixture
async def db():
    async with SessionLocal() as s:
        yield s
