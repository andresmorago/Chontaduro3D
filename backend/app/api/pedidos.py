from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.core import auditoria
from app.core.deps import DB, PROTEGIDO, Admin
from app.core.inventario import colores_de_articulos, stock_por_clave
from app.models import Articulo, ArticuloColor, Pedido, PedidoItem, Venta, VentaItem
from app.schemas.dominio import (
    DemandaArticuloOut,
    DemandaColorOut,
    EstadoPedido,
    PedidoEstadoIn,
    PedidoItemOut,
    PedidoOut,
    PedidoVentaOut,
)

router = APIRouter(prefix="/pedidos", tags=["pedidos"], dependencies=PROTEGIDO)

ABIERTOS = ("nuevo", "contactado")


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
    ventas: dict[UUID, list[PedidoVentaOut]] = defaultdict(list)
    if ids:
        for v in (
            await db.execute(
                select(Venta).where(Venta.pedido_id.in_(ids)).order_by(Venta.fecha, Venta.creado_en)
            )
        ).scalars():
            ventas[v.pedido_id].append(
                PedidoVentaOut(id=v.id, fecha=v.fecha, total=v.total, anulada=v.anulada)
            )
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
            ventas=ventas[p.id],
            total_vendido=sum((v.total for v in ventas[p.id] if not v.anulada), Decimal(0)),
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


@router.get("/demanda", response_model=list[DemandaArticuloOut])
async def demanda(db: DB) -> list[DemandaArticuloOut]:
    """Lo que piden los pedidos por atender, agrupado por artículo (y color), contra el stock.

    Lo ya vendido a un pedido (ventas no anuladas asociadas) no cuenta como pendiente, porque esas
    piezas ya salieron del inventario. El stock «sin color asignado» de un artículo con colores
    puede cubrir lo que falte de cualquiera de sus colores."""
    filas = (
        await db.execute(
            select(PedidoItem, Articulo)
            .join(Pedido, Pedido.id == PedidoItem.pedido_id)
            .join(Articulo, Articulo.id == PedidoItem.articulo_id)
            .where(Pedido.estado.in_(ABIERTOS))
        )
    ).all()
    if not filas:
        return []
    ids_pedidos = {i.pedido_id for i, _ in filas}

    # Piezas ya vendidas a cada pedido, por (pedido, artículo, color en minúsculas).
    vendidas: dict[tuple[UUID, UUID, str | None], int] = {}
    for pedido_id, articulo_id, color, n in await db.execute(
        select(
            Venta.pedido_id,
            VentaItem.articulo_id,
            ArticuloColor.nombre,
            func.sum(VentaItem.cantidad),
        )
        .join(Venta, Venta.id == VentaItem.venta_id)
        .outerjoin(ArticuloColor, ArticuloColor.id == VentaItem.color_id)
        .where(Venta.pedido_id.in_(ids_pedidos), Venta.anulada.is_(False))
        .group_by(Venta.pedido_id, VentaItem.articulo_id, ArticuloColor.nombre)
    ):
        vendidas[(pedido_id, articulo_id, color.lower() if color else None)] = int(n)

    # Lo pedido por (pedido, artículo, color) menos lo vendido; nunca negativo.
    pedido_por_clave: dict[tuple[UUID, UUID, str | None], int] = defaultdict(int)
    articulos: dict[UUID, Articulo] = {}
    for i, a in filas:
        articulos[a.id] = a
        pedido_por_clave[(i.pedido_id, a.id, i.color.lower() if i.color else None)] += i.cantidad
    pendiente: dict[UUID, dict[str | None, int]] = defaultdict(lambda: defaultdict(int))
    quienes: dict[UUID, set[UUID]] = defaultdict(set)
    for (pedido_id, articulo_id, color), n in pedido_por_clave.items():
        resto = n - vendidas.get((pedido_id, articulo_id, color), 0)
        if resto > 0:
            pendiente[articulo_id][color] += resto
            quienes[articulo_id].add(pedido_id)

    colores = await colores_de_articulos(db, pendiente.keys())
    stock = await stock_por_clave(db, pendiente.keys())
    salida: list[DemandaArticuloOut] = []
    for articulo_id, por_color in pendiente.items():
        a = articulos[articulo_id]
        nombres = {nombre.lower(): cid for cid, nombre in colores[articulo_id].items()}
        sin_color = stock.get((articulo_id, None), 0)
        renglones: list[DemandaColorOut] = []
        faltan_con_color = 0
        faltan_sin_color = 0
        for color in sorted(por_color, key=lambda c: (c is None, c or "")):
            n = por_color[color]
            hay = sin_color if color is None else stock.get((articulo_id, nombres.get(color)), 0)
            faltan = max(0, n - max(0, hay))
            if color is None:
                faltan_sin_color = faltan
            else:
                faltan_con_color += faltan
            nombre = next((v for v in colores[articulo_id].values() if v.lower() == color), color)
            renglones.append(DemandaColorOut(color=nombre, pendiente=n, stock=hay, faltan=faltan))
        # El stock sin color asignado que sobra cubre lo que falte de los colores con nombre.
        sobrante = (
            max(0, sin_color - por_color.get(None, 0)) if None in por_color else max(0, sin_color)
        )
        faltan = faltan_sin_color + max(0, faltan_con_color - sobrante)
        salida.append(
            DemandaArticuloOut(
                articulo_id=a.id, codigo=a.codigo, articulo=a.nombre,
                pedidos=len(quienes[articulo_id]), pendiente=sum(por_color.values()),
                stock=sum(max(0, v) for (aid, _), v in stock.items() if aid == articulo_id),
                faltan=faltan,
                colores=renglones if (len(renglones) > 1 or renglones[0].color is not None) else [],
            )
        )  # fmt: skip
    return sorted(salida, key=lambda d: (-d.faltan, d.codigo))


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
