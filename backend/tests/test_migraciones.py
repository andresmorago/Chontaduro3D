"""Las migraciones deben poder repetirse, revertirse y no divergir de los modelos.

Corren en una base propia (`misimpresiones_mig`), creada y destruida aquí, para no
pisar a las demás pruebas.
"""

import gzip
import os
import subprocess
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app import migrar
from app.config import settings

BASE = make_url(settings.database_url)
NOMBRE = "misimpresiones_mig"
URL_MIG = BASE.set(database=NOMBRE).render_as_string(hide_password=False)
TABLAS = {
    "usuarios", "sesiones_refresh", "articulos", "precio_historial", "producciones",
    "produccion_items", "ventas", "venta_items", "movimientos_inventario", "pedidos",
    "registro_auditoria", "parametros", "produccion_filamentos",
}  # fmt: skip


def alembic(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": URL_MIG}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args], env=env, capture_output=True, text=True
    )


def exito(r: subprocess.CompletedProcess) -> None:
    assert r.returncode == 0, f"alembic falló:\n{r.stdout}\n{r.stderr}"


@pytest_asyncio.fixture
async def mig():
    """Motor sobre una base vacía y recién creada."""
    admin = create_async_engine(
        BASE.render_as_string(hide_password=False), isolation_level="AUTOCOMMIT"
    )
    async with admin.connect() as c:
        await c.execute(text(f'DROP DATABASE IF EXISTS "{NOMBRE}" WITH (FORCE)'))
        await c.execute(text(f'CREATE DATABASE "{NOMBRE}"'))
    motor = create_async_engine(URL_MIG)
    yield motor
    await motor.dispose()
    async with admin.connect() as c:
        await c.execute(text(f'DROP DATABASE IF EXISTS "{NOMBRE}" WITH (FORCE)'))
    await admin.dispose()


async def tablas(motor) -> set[str]:
    async with motor.connect() as c:
        filas = await c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        return {f[0] for f in filas} - {"alembic_version"}


async def test_upgrade_dos_veces_es_inocuo(mig):
    exito(alembic("upgrade", "head"))
    exito(alembic("upgrade", "head"))
    assert await tablas(mig) == TABLAS


async def test_downgrade_y_upgrade_de_nuevo(mig):
    exito(alembic("upgrade", "head"))
    exito(alembic("downgrade", "base"))
    assert await tablas(mig) == set()
    exito(alembic("downgrade", "base"))  # revertir lo ya revertido tampoco falla
    exito(alembic("upgrade", "head"))
    assert await tablas(mig) == TABLAS


async def test_upgrade_sobre_esquema_parcial(mig):
    """Un fallo a medias o un retoque manual dejó parte de lo que la migración crea."""
    async with mig.begin() as c:
        await c.execute(text("CREATE SEQUENCE articulos_codigo_seq"))
        await c.execute(
            text(
                "CREATE TABLE usuarios (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
                "email varchar(254) NOT NULL UNIQUE, password_hash varchar(255) NOT NULL, "
                "activo boolean NOT NULL DEFAULT true, "
                "creado_en timestamptz NOT NULL DEFAULT now())"
            )
        )
        await c.execute(text("INSERT INTO usuarios (email, password_hash) VALUES ('a@b.co', 'x')"))
    exito(alembic("upgrade", "head"))
    assert await tablas(mig) == TABLAS
    async with mig.connect() as c:  # lo que ya existía se conserva
        assert (await c.execute(text("SELECT count(*) FROM usuarios"))).scalar_one() == 1


async def test_los_modelos_y_las_migraciones_no_divergen(mig):
    exito(alembic("upgrade", "head"))
    r = alembic("check")
    assert r.returncode == 0, f"Los modelos tienen cambios sin migración:\n{r.stdout}\n{r.stderr}"


async def test_el_codigo_legible_y_la_vista_de_stock_existen(mig):
    exito(alembic("upgrade", "head"))
    async with mig.begin() as c:
        await c.execute(
            text("INSERT INTO articulos (nombre, precio_venta) VALUES ('a', 1), ('b', 2)")
        )
        codigos = (
            (await c.execute(text("SELECT codigo FROM articulos ORDER BY codigo"))).scalars().all()
        )
        assert codigos == ["IMP-0001", "IMP-0002"]
        assert (await c.execute(text("SELECT count(*) FROM v_stock"))).scalar_one() == 2


async def test_check_impide_stock_o_precios_invalidos(mig):
    exito(alembic("upgrade", "head"))
    async with mig.connect() as c:
        with pytest.raises(Exception, match="precio_no_negativo"):
            await c.execute(text("INSERT INTO articulos (nombre, precio_venta) VALUES ('a', -1)"))


def test_respaldo_previo_a_migrar(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(migrar, "RESPALDOS", tmp_path)
    destino = migrar.respaldar("a", "b")
    assert destino.exists() and destino.stat().st_mode & 0o077 == 0  # solo el dueño lo lee
    with gzip.open(destino) as f:
        assert b"PostgreSQL database dump complete" in f.read()


def test_rotacion_conserva_solo_los_ultimos(tmp_path: Path):
    for i in range(14):
        (tmp_path / f"{migrar.PREFIJO}2026010{i:02d}-a-b.sql.gz").write_bytes(b"x")
    (tmp_path / "otro-archivo.sql.gz").write_bytes(b"x")  # lo ajeno no se toca
    borrados = migrar.rotar(tmp_path, 10)
    assert len(borrados) == 4 and len(list(tmp_path.glob(f"{migrar.PREFIJO}*"))) == 10
    assert (tmp_path / "otro-archivo.sql.gz").exists()
