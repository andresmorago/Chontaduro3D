from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core import auditoria
from app.core.deps import DB, PROTEGIDO, Admin
from app.models import Articulo, Pedido, PedidoItem
from app.schemas.dominio import EstadoPedido, PedidoEstadoIn, PedidoItemOut, PedidoOut

router = APIRouter(prefix="/pedidos", tags=["pedidos"], dependencies=PROTEGIDO)


async def _salidas(db, pedidos: list[Pedido]) -> list[PedidoOut]:
    """Los pedidos con sus renglones (artículo, color, cantidad) y el total de referencia."""
    ids = [p.id for p in pedidos]
    renglones: dict[UUID, list[PedidoItemOut]] = defaultdict(list)
    if ids:
        filas = await db.execute(
            select(PedidoItem, Articulo)
            .join(Articulo, Articulo.id == PedidoItem.articulo_id)
            .where(PedidoItem.pedido_id.in_(ids))
            .order_by(Articulo.codigo, PedidoItem.color)
        )
        for i, a in filas:
            renglones[i.pedido_id].append(
                PedidoItemOut(
                    articulo_id=a.id, codigo=a.codigo, articulo=a.nombre, color=i.color,
                    cantidad=i.cantidad, precio=a.precio_venta,
                    subtotal=a.precio_venta * i.cantidad,
                )
            )  # fmt: skip
    return [
        PedidoOut(
            id=p.id,
            nombre=p.nombre,
            whatsapp=p.whatsapp,
            items=renglones[p.id],
            piezas=sum(i.cantidad for i in renglones[p.id]),
            total_estimado=sum((i.subtotal for i in renglones[p.id]), Decimal(0)),
            estado=p.estado,
            creado_en=p.creado_en,
        )  # fmt: skip
        for p in pedidos
    ]


@router.get("", response_model=list[PedidoOut])
async def listar(db: DB, estado: EstadoPedido | None = None, limite: int = 100) -> list[PedidoOut]:
    limite = max(1, min(limite, 200))
    consulta = select(Pedido).order_by(Pedido.creado_en.desc()).limit(limite)
    if estado:
        consulta = consulta.where(Pedido.estado == estado)
    return await _salidas(db, list((await db.execute(consulta)).scalars().all()))


@router.patch("/{pedido_id}", response_model=PedidoOut)
async def cambiar_estado(
    pedido_id: UUID, datos: PedidoEstadoIn, db: DB, usuario: Admin
) -> PedidoOut:
    # Cambiar el estado de un pedido NO toca el inventario: la venta se registra aparte.
    pedido = (
        await db.execute(select(Pedido).where(Pedido.id == pedido_id).with_for_update())
    ).scalar_one_or_none()
    if pedido is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese pedido no existe.")
    anterior, pedido.estado = pedido.estado, datos.estado
    auditoria.registrar(
        db, "pedido_estado", usuario_id=usuario.id,
        detalle={"pedido": str(pedido.id), "antes": anterior, "despues": datos.estado},
    )  # fmt: skip
    await db.commit()
    return (await _salidas(db, [pedido]))[0]
