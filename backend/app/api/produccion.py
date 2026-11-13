from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.config import settings
from app.core import auditoria, energia
from app.core.deps import DB, PROTEGIDO, Admin
from app.core.inventario import bloquear_articulos
from app.models import (
    Articulo,
    MovimientoInventario,
    Produccion,
    ProduccionFilamento,
    ProduccionItem,
)
from app.schemas.dominio import FilamentoOut, ProduccionIn, ProduccionItemOut, ProduccionOut

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
    filamentos = [
        FilamentoOut(descripcion=f.descripcion, gramos=f.gramos)
        for f in (
            await db.execute(
                select(ProduccionFilamento)
                .where(ProduccionFilamento.produccion_id == produccion.id)
                .order_by(ProduccionFilamento.orden)
            )
        ).scalars()
    ]
    return ProduccionOut(
        id=produccion.id, fecha=produccion.fecha, nota=produccion.nota,
        creado_en=produccion.creado_en, items=items, gramos_total=produccion.gramos_total,
        filamentos=filamentos, minutos_impresion=produccion.minutos_impresion,
        potencia_w=produccion.potencia_w, precio_kwh=produccion.precio_kwh,
        kwh=produccion.kwh, costo_energia=produccion.costo_energia,
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

    # Filamento: o el total directo, o por filamento (el total es la suma). Si vienen los dos,
    # deben cuadrar.
    gramos_total = datos.gramos_total
    if datos.filamentos:
        suma = sum((f.gramos for f in datos.filamentos), Decimal(0))
        if gramos_total is not None and abs(gramos_total - suma) > Decimal("0.01"):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"El total ({gramos_total} g) no coincide con la suma por filamento ({suma} g).",
            )
        gramos_total = suma

    # Energía con los parámetros de HOY, congelados en el lote (cambiarlos después no
    # reescribe el pasado).
    param = await energia.parametros(db)
    kwh, costo = energia.calcular(
        datos.minutos_impresion, param.potencia_impresora_w, param.precio_kwh
    )

    p = Produccion(
        fecha=validar_fecha(datos.fecha), nota=datos.nota or None, gramos_total=gramos_total,
        minutos_impresion=datos.minutos_impresion,
        potencia_w=param.potencia_impresora_w if datos.minutos_impresion else None,
        precio_kwh=param.precio_kwh if datos.minutos_impresion else None,
        kwh=kwh, costo_energia=costo,
    )  # fmt: skip
    db.add(p)
    await db.flush()
    for n, f in enumerate(datos.filamentos):
        db.add(
            ProduccionFilamento(
                produccion_id=p.id, orden=n, descripcion=f.descripcion, gramos=f.gramos
            )
        )
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
