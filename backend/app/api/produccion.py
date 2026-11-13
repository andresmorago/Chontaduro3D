from collections import defaultdict
from datetime import date, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.config import settings
from app.core import auditoria
from app.core.deps import DB, PROTEGIDO, Admin
from app.core.inventario import bloquear_articulos
from app.models import Articulo, MovimientoInventario, Produccion, ProduccionItem
from app.schemas.dominio import ProduccionIn, ProduccionItemOut, ProduccionOut

router = APIRouter(prefix="/produccion", tags=["produccion"], dependencies=PROTEGIDO)


def hoy() -> date:
    from datetime import datetime

    return datetime.now(ZoneInfo(settings.app_timezone)).date()


def validar_fecha(fecha: date | None) -> date:
    """Hoy por defecto; se permite registrar algo olvidado hasta 31 días atrás, nunca el futuro."""
    h = hoy()
    f = fecha or h
    if f > h:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "La fecha no puede ser futura.")
    if f < h - timedelta(days=31):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Solo puedes registrar hasta 31 días atrás."
        )
    return f


async def _salida(db, produccion: Produccion) -> ProduccionOut:
    filas = await db.execute(
        select(ProduccionItem, Articulo)
        .join(Articulo, Articulo.id == ProduccionItem.articulo_id)
        .where(ProduccionItem.produccion_id == produccion.id)
        .order_by(Articulo.codigo)
    )
    items = [
        ProduccionItemOut(articulo_id=a.id, codigo=a.codigo, nombre=a.nombre, cantidad=i.cantidad)
        for i, a in filas
    ]
    return ProduccionOut(
        id=produccion.id, fecha=produccion.fecha, nota=produccion.nota,
        creado_en=produccion.creado_en, items=items,
    )  # fmt: skip


@router.post("", response_model=ProduccionOut, status_code=status.HTTP_201_CREATED)
async def registrar(datos: ProduccionIn, db: DB, usuario: Admin) -> ProduccionOut:
    cantidades: dict[UUID, int] = defaultdict(int)
    for item in datos.items:
        cantidades[item.articulo_id] += item.cantidad
    articulos = await bloquear_articulos(db, cantidades)

    desconocidos = set(cantidades) - set(articulos)
    archivados = [a.nombre for a in articulos.values() if not a.activo]
    if desconocidos or archivados:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Hay artículos que no existen o están archivados"
            + (f": {', '.join(archivados)}." if archivados else "."),
        )

    p = Produccion(fecha=validar_fecha(datos.fecha), nota=datos.nota or None)
    db.add(p)
    await db.flush()
    for articulo_id, cantidad in cantidades.items():
        db.add(ProduccionItem(produccion_id=p.id, articulo_id=articulo_id, cantidad=cantidad))
        db.add(
            MovimientoInventario(
                articulo_id=articulo_id, tipo="produccion", cantidad=cantidad, produccion_id=p.id
            )
        )
    auditoria.registrar(
        db, "produccion_registrada", usuario_id=usuario.id,
        detalle={"unidades": sum(cantidades.values())},
    )  # fmt: skip
    await db.commit()
    await db.refresh(p)
    return await _salida(db, p)


@router.get("", response_model=list[ProduccionOut])
async def listar(db: DB, limite: int = 30) -> list[ProduccionOut]:
    limite = max(1, min(limite, 100))
    filas = (
        await db.execute(
            select(Produccion)
            .order_by(Produccion.fecha.desc(), Produccion.creado_en.desc())
            .limit(limite)
        )
    ).scalars()
    return [await _salida(db, p) for p in filas]
