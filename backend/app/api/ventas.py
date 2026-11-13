from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.produccion import hoy, validar_fecha
from app.core import auditoria
from app.core.deps import DB, PROTEGIDO, Admin
from app.core.inventario import bloquear_articulos, exigir_stock_suficiente, stock_de
from app.core.tokens import ahora
from app.models import Articulo, MovimientoInventario, Venta, VentaItem
from app.schemas.dominio import VentaIn, VentaItemOut, VentaOut

router = APIRouter(prefix="/ventas", tags=["ventas"], dependencies=PROTEGIDO)


async def _salida(db, venta: Venta) -> VentaOut:
    filas = await db.execute(
        select(VentaItem, Articulo)
        .join(Articulo, Articulo.id == VentaItem.articulo_id)
        .where(VentaItem.venta_id == venta.id)
        .order_by(Articulo.codigo)
    )
    items = [
        VentaItemOut(
            articulo_id=a.id, codigo=a.codigo, nombre=a.nombre,
            cantidad=i.cantidad, precio_unitario=i.precio_unitario,
        )
        for i, a in filas
    ]  # fmt: skip
    return VentaOut(
        id=venta.id, fecha=venta.fecha, cliente=venta.cliente, metodo_pago=venta.metodo_pago,
        nota=venta.nota, total=venta.total, anulada=venta.anulada, creado_en=venta.creado_en,
        items=items,
    )  # fmt: skip


@router.post("", response_model=VentaOut, status_code=status.HTTP_201_CREATED)
async def registrar(datos: VentaIn, db: DB, usuario: Admin) -> VentaOut:
    # Un mismo artículo en varias líneas con distinto precio es legítimo (una con descuento);
    # el stock se valida sobre la suma.
    por_articulo: dict[UUID, int] = defaultdict(int)
    for item in datos.items:
        por_articulo[item.articulo_id] += item.cantidad

    articulos = await bloquear_articulos(db, por_articulo)
    desconocidos = set(por_articulo) - set(articulos)
    archivados = [a.nombre for a in articulos.values() if not a.activo]
    if desconocidos or archivados:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Hay artículos que no existen o están archivados"
            + (f": {', '.join(archivados)}." if archivados else "."),
        )

    exigir_stock_suficiente(por_articulo, await stock_de(db, por_articulo), articulos)

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
                venta_id=venta.id, articulo_id=item.articulo_id,
                cantidad=item.cantidad, precio_unitario=precio,
            )
        )  # fmt: skip
    for articulo_id, cantidad in por_articulo.items():
        db.add(
            MovimientoInventario(
                articulo_id=articulo_id, tipo="venta", cantidad=-cantidad, venta_id=venta.id
            )
        )
    if total > Decimal("9999999999"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "El total de la venta es demasiado alto."
        )
    venta.total = total
    auditoria.registrar(
        db, "venta_registrada", usuario_id=usuario.id,
        detalle={"total": float(total), "unidades": sum(por_articulo.values())},
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
    devolver: dict[UUID, int] = defaultdict(int)
    for i in items:
        devolver[i.articulo_id] += i.cantidad
    await bloquear_articulos(db, devolver)
    for articulo_id, cantidad in devolver.items():
        db.add(
            MovimientoInventario(
                articulo_id=articulo_id, tipo="anulacion", cantidad=cantidad,
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
