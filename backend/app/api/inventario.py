from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.articulos import a_salida
from app.core import auditoria
from app.core.deps import DB, PROTEGIDO, Admin
from app.core.inventario import bloquear_articulos, stock_de
from app.models import Articulo, MovimientoInventario
from app.schemas.dominio import AjusteIn, ArticuloOut, MovimientoOut

router = APIRouter(prefix="/inventario", tags=["inventario"], dependencies=PROTEGIDO)


@router.get("", response_model=list[ArticuloOut])
async def existencias(db: DB) -> list[ArticuloOut]:
    """Stock actual de cada artículo activo."""
    articulos = (
        (
            await db.execute(
                select(Articulo).where(Articulo.activo.is_(True)).order_by(Articulo.codigo)
            )
        )
        .scalars()
        .all()
    )
    stock = await stock_de(db, [a.id for a in articulos])
    return [a_salida(a, stock[a.id]) for a in articulos]


@router.get("/movimientos", response_model=list[MovimientoOut])
async def kardex(
    db: DB, articulo_id: UUID | None = None, limite: int = 50, desplazar: int = 0
) -> list[MovimientoOut]:
    limite = max(1, min(limite, 200))
    consulta = (
        select(MovimientoInventario, Articulo)
        .join(Articulo, Articulo.id == MovimientoInventario.articulo_id)
        .order_by(MovimientoInventario.creado_en.desc(), MovimientoInventario.id.desc())
        .limit(limite)
        .offset(max(desplazar, 0))
    )
    if articulo_id:
        consulta = consulta.where(MovimientoInventario.articulo_id == articulo_id)
    return [
        MovimientoOut(
            id=m.id, articulo_id=a.id, codigo=a.codigo, nombre=a.nombre, tipo=m.tipo,
            cantidad=m.cantidad, nota=m.nota, creado_en=m.creado_en,
        )
        for m, a in await db.execute(consulta)
    ]  # fmt: skip


@router.post("/ajustes", response_model=ArticuloOut, status_code=status.HTTP_201_CREATED)
async def ajustar(datos: AjusteIn, db: DB, usuario: Admin) -> ArticuloOut:
    """Corrección manual (conteo físico, pieza dañada…). Nunca deja el stock en negativo."""
    articulos = await bloquear_articulos(db, [datos.articulo_id])
    articulo = articulos.get(datos.articulo_id)
    if articulo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese artículo no existe.")
    actual = (await stock_de(db, [articulo.id]))[articulo.id]
    if actual + datos.cantidad < 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Ese ajuste dejaría el stock en {actual + datos.cantidad}. Hay {actual} unidades.",
        )
    db.add(
        MovimientoInventario(
            articulo_id=articulo.id, tipo="ajuste", cantidad=datos.cantidad, nota=datos.nota
        )
    )
    auditoria.registrar(
        db, "ajuste_inventario", usuario_id=usuario.id,
        detalle={"codigo": articulo.codigo, "cantidad": datos.cantidad},
    )  # fmt: skip
    await db.commit()
    return a_salida(articulo, actual + datos.cantidad)
