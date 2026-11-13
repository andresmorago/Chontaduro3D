"""Reglas de inventario. El stock es la suma de movimientos; vender o ajustar
bloquea las filas de los artículos para que dos operaciones simultáneas no
puedan dejar el stock en negativo."""

from collections.abc import Iterable
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Articulo, MovimientoInventario


async def bloquear_articulos(db: AsyncSession, ids: Iterable[UUID]) -> dict[UUID, Articulo]:
    """SELECT … FOR UPDATE ordenado por id (el orden evita interbloqueos entre ventas)."""
    unicos = sorted(set(ids))
    filas = (
        await db.execute(
            select(Articulo).where(Articulo.id.in_(unicos)).order_by(Articulo.id).with_for_update()
        )
    ).scalars()
    return {a.id: a for a in filas}


async def stock_de(db: AsyncSession, ids: Iterable[UUID]) -> dict[UUID, int]:
    ids = list(set(ids))
    if not ids:
        return {}
    filas = await db.execute(
        select(MovimientoInventario.articulo_id, func.sum(MovimientoInventario.cantidad))
        .where(MovimientoInventario.articulo_id.in_(ids))
        .group_by(MovimientoInventario.articulo_id)
    )
    resultado = {i: 0 for i in ids}
    resultado.update({a: int(c) for a, c in filas})
    return resultado


def exigir_stock_suficiente(
    pedido: dict[UUID, int], stock: dict[UUID, int], articulos: dict[UUID, Articulo]
) -> None:
    faltan = [
        f"{articulos[i].nombre}: pides {n}, hay {stock.get(i, 0)}"
        for i, n in pedido.items()
        if stock.get(i, 0) < n
    ]
    if faltan:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No hay suficiente stock para esta operación. " + "; ".join(faltan) + ".",
        )
