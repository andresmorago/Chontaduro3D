from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core import auditoria
from app.core.deps import DB, PROTEGIDO, Admin
from app.models import Articulo, Pedido
from app.schemas.dominio import EstadoPedido, PedidoEstadoIn, PedidoOut

router = APIRouter(prefix="/pedidos", tags=["pedidos"], dependencies=PROTEGIDO)


def _salida(p: Pedido, a: Articulo) -> PedidoOut:
    return PedidoOut(
        id=p.id, articulo_id=a.id, codigo=a.codigo, articulo=a.nombre, nombre=p.nombre,
        whatsapp=p.whatsapp, cantidad=p.cantidad, color=p.color, estado=p.estado,
        creado_en=p.creado_en,
    )  # fmt: skip


@router.get("", response_model=list[PedidoOut])
async def listar(db: DB, estado: EstadoPedido | None = None, limite: int = 100) -> list[PedidoOut]:
    limite = max(1, min(limite, 200))
    consulta = (
        select(Pedido, Articulo)
        .join(Articulo, Articulo.id == Pedido.articulo_id)
        .order_by(Pedido.creado_en.desc())
        .limit(limite)
    )
    if estado:
        consulta = consulta.where(Pedido.estado == estado)
    return [_salida(p, a) for p, a in await db.execute(consulta)]


@router.patch("/{pedido_id}", response_model=PedidoOut)
async def cambiar_estado(
    pedido_id: UUID, datos: PedidoEstadoIn, db: DB, usuario: Admin
) -> PedidoOut:
    # Cambiar el estado de un pedido NO toca el inventario: la venta se registra aparte.
    fila = (
        await db.execute(
            select(Pedido, Articulo)
            .join(Articulo, Articulo.id == Pedido.articulo_id)
            .where(Pedido.id == pedido_id)
        )
    ).first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese pedido no existe.")
    pedido, articulo = fila
    anterior, pedido.estado = pedido.estado, datos.estado
    auditoria.registrar(
        db, "pedido_estado", usuario_id=usuario.id,
        detalle={"codigo": articulo.codigo, "antes": anterior, "despues": datos.estado},
    )  # fmt: skip
    await db.commit()
    return _salida(pedido, articulo)
