from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.articulos import salidas
from app.core import auditoria
from app.core.deps import DB, PROTEGIDO, Admin
from app.core.inventario import (
    bloquear_articulos,
    colores_de_articulos,
    exigir_stock_por_clave,
    stock_por_clave,
    validar_colores,
)
from app.models import Articulo, ArticuloColor, MovimientoInventario
from app.schemas.dominio import AjusteIn, ArticuloOut, MovimientoOut

router = APIRouter(prefix="/inventario", tags=["inventario"], dependencies=PROTEGIDO)


@router.get("", response_model=list[ArticuloOut])
async def existencias(db: DB) -> list[ArticuloOut]:
    """Stock actual de cada artículo activo, con el desglose por color."""
    articulos = (
        (
            await db.execute(
                select(Articulo).where(Articulo.activo.is_(True)).order_by(Articulo.codigo)
            )
        )
        .scalars()
        .all()
    )
    return await salidas(db, list(articulos))


@router.get("/movimientos", response_model=list[MovimientoOut])
async def kardex(
    db: DB, articulo_id: UUID | None = None, limite: int = 50, desplazar: int = 0
) -> list[MovimientoOut]:
    limite = max(1, min(limite, 200))
    consulta = (
        select(MovimientoInventario, Articulo, ArticuloColor.nombre)
        .join(Articulo, Articulo.id == MovimientoInventario.articulo_id)
        .outerjoin(ArticuloColor, ArticuloColor.id == MovimientoInventario.color_id)
        .order_by(MovimientoInventario.creado_en.desc(), MovimientoInventario.id.desc())
        .limit(limite)
        .offset(max(desplazar, 0))
    )
    if articulo_id:
        consulta = consulta.where(MovimientoInventario.articulo_id == articulo_id)
    return [
        MovimientoOut(
            id=m.id, articulo_id=a.id, codigo=a.codigo, nombre=a.nombre, tipo=m.tipo,
            cantidad=m.cantidad, color=nombre_color, nota=m.nota, creado_en=m.creado_en,
        )
        for m, a, nombre_color in await db.execute(consulta)
    ]  # fmt: skip


@router.post("/ajustes", response_model=ArticuloOut, status_code=status.HTTP_201_CREATED)
async def ajustar(datos: AjusteIn, db: DB, usuario: Admin) -> ArticuloOut:
    """Corrección manual (conteo físico, pieza dañada, o mover stock «sin color asignado» a su
    color). En un artículo con colores se indica de cuál. Nunca deja un stock en negativo."""
    articulos = await bloquear_articulos(db, [datos.articulo_id])
    articulo = articulos.get(datos.articulo_id)
    if articulo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese artículo no existe.")
    colores = await colores_de_articulos(db, [articulo.id])
    clave = (articulo.id, datos.color_id)
    # El stock «sin color asignado» solo se puede REDUCIR (para pasarlo a un color); sumarle no.
    validar_colores([clave], articulos, colores, permitir_sin_color=datos.cantidad < 0)
    if datos.cantidad < 0:
        stock = await stock_por_clave(db, [articulo.id])
        exigir_stock_por_clave({clave: -datos.cantidad}, stock, articulos, colores)
    db.add(
        MovimientoInventario(
            articulo_id=articulo.id, color_id=datos.color_id, tipo="ajuste",
            cantidad=datos.cantidad, nota=datos.nota,
        )
    )  # fmt: skip
    auditoria.registrar(
        db, "ajuste_inventario", usuario_id=usuario.id,
        detalle={
            "codigo": articulo.codigo, "cantidad": datos.cantidad,
            "color": colores[articulo.id].get(datos.color_id) if datos.color_id else None,
        },
    )  # fmt: skip
    await db.commit()
    return (await salidas(db, [articulo]))[0]
