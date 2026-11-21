"""Purga periódica de intentos de ingreso fallidos y de sesiones de refresco viejas."""

import asyncio
import contextlib
from datetime import timedelta

from sqlalchemy import func, select

from app.core import limpieza
from app.core.tokens import ahora
from app.models import RegistroAuditoria, SesionRefresh, Usuario
from tests.conftest import EMAIL


async def _cuenta(db, modelo) -> int:
    db.expire_all()
    return (await db.execute(select(func.count()).select_from(modelo))).scalar_one()


async def test_purgar_borra_solo_lo_viejo(admin, db):
    dias = lambda n: ahora() - timedelta(days=n)  # noqa: E731
    uid = (await db.execute(select(Usuario.id).where(Usuario.email == EMAIL))).scalar_one()
    for accion, hace in (
        ("login_fallido", 91), ("login_fallido", 89), ("login", 400), ("pedido_estado", 400),
    ):  # fmt: skip
        db.add(RegistroAuditoria(accion=accion, creado_en=dias(hace)))
    for i, (expira, revocada_en) in enumerate(
        [
            (dias(-30), None),  # vigente: se queda
            (dias(31), None),  # caducada hace 31 días: se va
            (dias(-5), dias(31)),  # revocada hace 31 días: se va
            (dias(-5), dias(2)),  # revocada hace poco: se queda
            (dias(10), None),  # caducada hace poco: se queda
        ]
    ):
        db.add(
            SesionRefresh(
                usuario_id=uid, token_hash=f"hash{i}".ljust(64, "0"), expira_en=expira,
                revocada=revocada_en is not None, revocada_en=revocada_en,
            )
        )  # fmt: skip
    await db.commit()
    antes = await _cuenta(db, SesionRefresh)  # las 5 de arriba + la del login del admin

    quitadas = await limpieza.purgar()

    assert quitadas == {"login_fallido": 1, "sesiones_refresh": 2}
    assert await _cuenta(db, SesionRefresh) == antes - 2
    acciones = (await db.execute(select(RegistroAuditoria.accion))).scalars().all()
    assert sorted(acciones).count("login_fallido") == 1
    assert "login" in acciones and "pedido_estado" in acciones
    assert await limpieza.purgar() == {"login_fallido": 0, "sesiones_refresh": 0}  # idempotente


async def test_el_bucle_sobrevive_a_un_fallo_y_se_cancela(monkeypatch, caplog):
    llamadas = 0

    async def falla():
        nonlocal llamadas
        llamadas += 1
        raise RuntimeError("base caída")

    monkeypatch.setattr(limpieza, "purgar", falla)
    tarea = asyncio.create_task(limpieza.bucle_limpieza(cada_s=0.01))
    await asyncio.sleep(0.1)
    assert not tarea.done() and llamadas >= 2  # el fallo no lo tumbó
    tarea.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await tarea
    assert tarea.cancelled()
    assert "Falló la limpieza periódica" in caplog.text


