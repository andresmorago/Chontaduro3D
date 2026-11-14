from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.produccion import hoy, validar_fecha
from app.core import auditoria
from app.core.deps import DB, PROTEGIDO, Admin
from app.core.inventario import (
    Clave,
    bloquear_articulos,
    colores_de_articulos,
    exigir_stock_por_clave,
    stock_por_clave,
    validar_colores,
)
from app.core.tokens import ahora
from app.models import Articulo, ArticuloColor, MovimientoInventario, Venta, VentaItem
from app.schemas.dominio import VentaIn, VentaItemOut, VentaOut

router = APIRouter(prefix="/ventas", tags=["ventas"], dependencies=PROTEGIDO)


async def _salida(db, venta: Venta) -> VentaOut:
    filas = await db.execute(
        select(VentaItem, Articulo, ArticuloColor)
        .join(Articulo, Articulo.id == VentaItem.articulo_id)
        .outerjoin(ArticuloColor, ArticuloColor.id == VentaItem.color_id)
        .where(VentaItem.venta_id == venta.id)
        .order_by(Articulo.codigo, ArticuloColor.orden)
    )
    items = [
        VentaItemOut(
            articulo_id=a.id, color_id=i.color_id, color=c.nombre if c else None,
            color_hex=c.hex if c else None, codigo=a.codigo, nombre=a.nombre,
            cantidad=i.cantidad, precio_unitario=i.precio_unitario,
        )
        for i, a, c in filas
    ]  # fmt: skip
    return VentaOut(
        id=venta.id, fecha=venta.fecha, cliente=venta.cliente, metodo_pago=venta.metodo_pago,
        nota=venta.nota, total=venta.total, anulada=venta.anulada, creado_en=venta.creado_en,
        items=items,
    )  # fmt: skip


@router.post("", response_model=VentaOut, status_code=status.HTTP_201_CREATED)
async def registrar(datos: VentaIn, db: DB, usuario: Admin) -> VentaOut:
    # Un mismo artículo (y color) en varias líneas con distinto precio es legítimo (una con
    # descuento); el stock se valida sobre la suma, por (artículo, color).
    por_clave: dict[Clave, int] = defaultdict(int)
    for item in datos.items:
        por_clave[(item.articulo_id, item.color_id)] += item.cantidad
    ids = {a for a, _ in por_clave}

    articulos = await bloquear_articulos(db, ids)
    desconocidos = ids - set(articulos)
    archivados = [a.nombre for a in articulos.values() if not a.activo]
    if desconocidos or archivados:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Hay artículos que no existen o están archivados"
            + (f": {', '.join(archivados)}." if archivados else "."),
        )

    colores = await colores_de_articulos(db, ids)
    # En un artículo con colores se vende de un color; el stock «sin color asignado» (anterior a los
    # colores) también se puede vender, mientras quede.
    validar_colores(por_clave, articulos, colores, permitir_sin_color=True)
    exigir_stock_por_clave(por_clave, await stock_por_clave(db, ids), articulos, colores)

    venta = Venta(
        fecha=validar_fecha(datos.fecha), cliente=datos.cliente, metodo_pago=datos.metodo_pago,
        nota=datos.nota, total=Decimal(0),
    )  # fmt: skip
    db.add(venta)
    await db.flush()

    total = Decimal(0)
    for item in datos.items:
        precio = (
            item.precio_unitario
            if item.precio_unitario is not None
            else articulos[item.articulo_id].precio_venta
        )
        total += precio * item.cantidad
        db.add(
            VentaItem(
                venta_id=venta.id, articulo_id=item.articulo_id, color_id=item.color_id,
                cantidad=item.cantidad, precio_unitario=precio,
            )
        )  # fmt: skip
    for (articulo_id, color_id), cantidad in por_clave.items():
        db.add(
            MovimientoInventario(
                articulo_id=articulo_id, color_id=color_id, tipo="venta", cantidad=-cantidad,
                venta_id=venta.id,
            )
        )  # fmt: skip
    if total > Decimal("9999999999"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "El total de la venta es demasiado alto."
        )
    venta.total = total
    auditoria.registrar(
        db, "venta_registrada", usuario_id=usuario.id,
        detalle={"total": float(total), "unidades": sum(por_clave.values())},
    )  # fmt: skip
    await db.commit()
    await db.refresh(venta)
    return await _salida(db, venta)


@router.get("", response_model=list[VentaOut])
async def listar(
    db: DB, desde: date | None = None, hasta: date | None = None, limite: int = 100
) -> list[VentaOut]:
    limite = max(1, min(limite, 200))
    consulta = select(Venta).order_by(Venta.fecha.desc(), Venta.creado_en.desc()).limit(limite)
    if desde is None and hasta is None:
        desde = hasta = hoy()
    if desde:
        consulta = consulta.where(Venta.fecha >= desde)
    if hasta:
        consulta = consulta.where(Venta.fecha <= hasta)
    return [await _salida(db, v) for v in (await db.execute(consulta)).scalars()]


@router.post("/{venta_id}/anular", response_model=VentaOut)
async def anular(venta_id: UUID, db: DB, usuario: Admin) -> VentaOut:
    venta = (
        await db.execute(select(Venta).where(Venta.id == venta_id).with_for_update())
    ).scalar_one_or_none()
    if venta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa venta no existe.")
    if venta.anulada:
        return await _salida(db, venta)  # ya anulada: repetir no devuelve el stock dos veces

    items = (
        (await db.execute(select(VentaItem).where(VentaItem.venta_id == venta.id))).scalars().all()
    )
    devolver: dict[Clave, int] = defaultdict(int)
    for i in items:
        devolver[(i.articulo_id, i.color_id)] += i.cantidad
    await bloquear_articulos(db, {a for a, _ in devolver})
    for (articulo_id, color_id), cantidad in devolver.items():
        # La pieza vuelve al mismo color de donde salió.
        db.add(
            MovimientoInventario(
                articulo_id=articulo_id, color_id=color_id, tipo="anulacion", cantidad=cantidad,
                venta_id=venta.id, nota="Venta anulada",
            )
        )  # fmt: skip
    venta.anulada = True
    venta.anulada_en = ahora()
    auditoria.registrar(
        db, "venta_anulada", usuario_id=usuario.id, detalle={"total": float(venta.total)}
    )
    await db.commit()
    return await _salida(db, venta)
