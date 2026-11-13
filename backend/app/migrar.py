"""Migra la base al arrancar, con respaldo antes y sin carreras.

Lo corre `arrancar.sh` cada vez que arranca el contenedor del backend (y
`make migrate`). Si no hay migraciones pendientes no hace nada; si las hay:

1. toma un candado de Postgres, para que dos procesos nunca migren a la vez;
2. saca un respaldo comprimido ANTES de tocar nada, y si no puede, no migra;
3. corre `alembic upgrade head` (migraciones idempotentes);
4. deja solo los últimos respaldos.

Una base nueva (sin historial de migraciones) no tiene nada que respaldar.
`MIGRAR_AL_ARRANCAR=0` lo apaga por completo.
"""

import asyncio
import gzip
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings

CLAVE_CANDADO = 7_260_913
RESPALDOS = Path(os.environ.get("RESPALDOS_DIR", "/respaldos"))
CONSERVAR = int(os.environ.get("RESPALDOS_CONSERVAR", "10"))
PREFIJO = "antes-de-migrar-"
FIN_DE_VOLCADO = b"PostgreSQL database dump complete"


def log(mensaje: str) -> None:
    print(f"[migrar] {mensaje}", flush=True)


def revision_cabeza() -> str:
    return ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()


async def revision_actual(conexion) -> str | None:
    existe = (await conexion.execute(text("SELECT to_regclass('alembic_version')"))).scalar()
    if existe is None:
        return None
    return (await conexion.execute(text("SELECT version_num FROM alembic_version"))).scalar()


def respaldar(desde: str | None, hasta: str) -> Path:
    """Vuelca la base a un .sql.gz y comprueba que quedó completo."""
    if not RESPALDOS.is_dir() or not os.access(RESPALDOS, os.W_OK):
        raise RuntimeError(
            f"No puedo escribir en {RESPALDOS}. Monta ahí ./data/respaldos "
            "o apaga la migración automática con MIGRAR_AL_ARRANCAR=0."
        )
    url = make_url(settings.database_url)
    destino = RESPALDOS / f"{PREFIJO}{datetime.now():%Y%m%d-%H%M%S}-{desde}-a-{hasta}.sql.gz"
    entorno = {**os.environ, "PGPASSWORD": url.password or ""}
    comando = [
        "pg_dump",
        "-h", url.host or "db",
        "-p", str(url.port or 5432),
        "-U", url.username or "",
        "-d", url.database or "",
        "--no-owner", "--no-privileges",
    ]  # fmt: skip

    ultimo = b""
    with subprocess.Popen(comando, stdout=subprocess.PIPE, env=entorno) as proceso:
        fd = os.open(destino, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with gzip.GzipFile(fileobj=os.fdopen(fd, "wb"), mode="wb") as salida:
            for trozo in iter(lambda: proceso.stdout.read(1 << 20), b""):
                salida.write(trozo)
                ultimo = (ultimo + trozo)[-512:]

    if proceso.returncode != 0 or FIN_DE_VOLCADO not in ultimo:
        destino.unlink(missing_ok=True)
        raise RuntimeError("pg_dump no terminó bien; el respaldo se descartó.")
    return destino


def rotar(carpeta: Path, conservar: int) -> list[Path]:
    """Borra los respaldos más viejos de esta rutina y deja `conservar`."""
    propios = sorted(carpeta.glob(f"{PREFIJO}*.sql.gz"))
    sobrantes = propios[: max(len(propios) - conservar, 0)]
    for f in sobrantes:
        f.unlink(missing_ok=True)
    return sobrantes


async def migrar() -> None:
    cabeza = revision_cabeza()
    motor = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        # El candado vive en esta conexión y se suelta al cerrarla.
        async with motor.connect() as conexion:
            await conexion.execution_options(isolation_level="AUTOCOMMIT")
            log("esperando el candado de migración…")
            await conexion.execute(text("SELECT pg_advisory_lock(:k)"), {"k": CLAVE_CANDADO})

            # Se mira DESPUÉS del candado: otro proceso pudo migrar mientras se esperaba.
            actual = await revision_actual(conexion)
            if actual == cabeza:
                log(f"la base ya está en {cabeza}; nada que migrar.")
                return

            log(f"pendiente: {actual or 'base nueva'} → {cabeza}")
            if actual is not None:
                copia = await asyncio.to_thread(respaldar, actual, cabeza)
                log(f"respaldo listo: {copia} ({copia.stat().st_size // 1024} KB)")
                for f in rotar(RESPALDOS, CONSERVAR):
                    log(f"respaldo viejo borrado: {f.name}")

            await asyncio.to_thread(
                subprocess.run, [sys.executable, "-m", "alembic", "upgrade", "head"], check=True
            )
            log(f"migrado a {cabeza}.")
    finally:
        await motor.dispose()


def main() -> int:
    if os.environ.get("MIGRAR_AL_ARRANCAR", "1") == "0":
        log("apagado con MIGRAR_AL_ARRANCAR=0; no se migra.")
        return 0
    try:
        asyncio.run(migrar())
    except Exception as e:  # noqa: BLE001 — cualquier fallo debe detener el arranque
        log(f"FALLÓ: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
