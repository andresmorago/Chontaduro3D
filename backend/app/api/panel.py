from datetime import timedelta

from fastapi import APIRouter
from sqlalchemy import func, select, text

from app.api.produccion import hoy
from app.core.deps import DB, PROTEGIDO
from app.models import Articulo, Pedido, Venta
from app.schemas.dominio import PanelOut, StockBajo, VentasDia

router = APIRouter(prefix="/panel", tags=["panel"], dependencies=PROTEGIDO)


@router.get("", response_model=PanelOut)
async def resumen(db: DB) -> PanelOut:
    h = hoy()
    desde = h - timedelta(days=6)
    filas = await db.execute(
        select(Venta.fecha, func.coalesce(func.sum(Venta.total), 0), func.count())
        .where(Venta.anulada.is_(False), Venta.fecha >= desde, Venta.fecha <= h)
        .group_by(Venta.fecha)
    )
    por_dia = {f: (t, n) for f, t, n in filas}
    dias = [
        VentasDia(fecha=d, total=por_dia.get(d, (0, 0))[0], cantidad=por_dia.get(d, (0, 0))[1])
        for d in (desde + timedelta(days=i) for i in range(7))
    ]

    stock = (
        await db.execute(
            text(
                "SELECT a.id, a.codigo, a.nombre, s.stock, a.stock_minimo "
                "FROM articulos a JOIN v_stock s ON s.articulo_id = a.id "
                "WHERE a.activo ORDER BY a.codigo"
            )
        )
    ).all()
    bajos = [
        StockBajo(articulo_id=i, codigo=c, nombre=n, stock=s, stock_minimo=m)
        for i, c, n, s, m in stock
        if s <= m
    ]
    nuevos = (
        await db.execute(select(func.count()).select_from(Pedido).where(Pedido.estado == "nuevo"))
    ).scalar_one()
    activos = (
        await db.execute(
            select(func.count()).select_from(Articulo).where(Articulo.activo.is_(True))
        )
    ).scalar_one()
    return PanelOut(
        hoy=dias[-1], ultimos_dias=dias, stock_bajo=bajos, pedidos_nuevos=nuevos,
        articulos_activos=activos, unidades_en_stock=sum(s for _, _, _, s, _ in stock),
    )  # fmt: skip
