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


# --- Inventario por color -------------------------------------------------------------------------
# Una «clave» es (artículo, color). Un artículo sin colores usa siempre color None. En un artículo
# CON colores, None es el stock «sin color asignado» (el que había antes de existir los colores).
Clave = tuple[UUID, UUID | None]


async def colores_de_articulos(
    db: AsyncSession, ids: Iterable[UUID]
) -> dict[UUID, dict[UUID, str]]:
    """{artículo: {color_id: nombre}} (en el orden en que se definieron los colores)."""
    from app.models import ArticuloColor

    ids = list(set(ids))
    resultado: dict[UUID, dict[UUID, str]] = {i: {} for i in ids}
    if not ids:
        return resultado
    filas = await db.execute(
        select(ArticuloColor.articulo_id, ArticuloColor.id, ArticuloColor.nombre)
        .where(ArticuloColor.articulo_id.in_(ids))
        .order_by(ArticuloColor.articulo_id, ArticuloColor.orden)
    )
    for articulo_id, color_id, nombre in filas:
        resultado[articulo_id][color_id] = nombre
    return resultado


async def stock_por_clave(db: AsyncSession, ids: Iterable[UUID]) -> dict[Clave, int]:
    """Stock de cada (artículo, color) que tenga movimientos."""
    ids = list(set(ids))
    if not ids:
        return {}
    filas = await db.execute(
        select(
            MovimientoInventario.articulo_id,
            MovimientoInventario.color_id,
            func.sum(MovimientoInventario.cantidad),
        )
        .where(MovimientoInventario.articulo_id.in_(ids))
        .group_by(MovimientoInventario.articulo_id, MovimientoInventario.color_id)
    )
    return {(a, c): int(n) for a, c, n in filas}


def validar_colores(
    claves: Iterable[Clave],
    articulos: dict[UUID, Articulo],
    colores: dict[UUID, dict[UUID, str]],
    *,
    permitir_sin_color: bool = False,
) -> None:
    """Cada línea debe traer un color si el artículo se ofrece en colores (y uno de los suyos), y no
    traerlo si no los tiene. `permitir_sin_color` deja usar el stock «sin color asignado» de un
    artículo con colores (ventas y ajustes que lo reducen; nunca para producir)."""
    errores: list[str] = []
    for articulo_id, color_id in claves:
        a = articulos.get(articulo_id)
        propios = colores.get(articulo_id, {})
        if a is None:
            continue
        if propios and color_id is None and not permitir_sin_color:
            errores.append(f"«{a.nombre}» se ofrece en colores: elige uno")
        elif propios and color_id is not None and color_id not in propios:
            errores.append(f"«{a.nombre}» no tiene ese color")
        elif not propios and color_id is not None:
            errores.append(f"«{a.nombre}» no tiene colores")
    if errores:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "; ".join(errores) + ".")


def etiqueta(a: Articulo, color_id: UUID | None, colores: dict[UUID, dict[UUID, str]]) -> str:
    """«Llavero (Rojo)» / «Llavero (sin color asignado)» / «Llavero»."""
    propios = colores.get(a.id, {})
    if color_id is not None:
        return f"{a.nombre} ({propios.get(color_id, 'color eliminado')})"
    return f"{a.nombre} (sin color asignado)" if propios else a.nombre


def exigir_stock_por_clave(
    pedido: dict[Clave, int],
    stock: dict[Clave, int],
    articulos: dict[UUID, Articulo],
    colores: dict[UUID, dict[UUID, str]],
) -> None:
    faltan = [
        f"{etiqueta(articulos[a], c, colores)}: pides {n}, hay {stock.get((a, c), 0)}"
        for (a, c), n in pedido.items()
        if stock.get((a, c), 0) < n
    ]
    if faltan:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No hay suficiente stock para esta operación. " + "; ".join(faltan) + ".",
        )
