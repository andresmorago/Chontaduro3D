from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select

from app.api.articulos import url_imagen
from app.config import settings
from app.core.cliente import origen_hash
from app.core.deps import DB
from app.core.inventario import stock_de
from app.core.tokens import ahora
from app.models import Articulo, Pedido
from app.schemas.dominio import ArticuloPublico, CatalogoPublico, PedidoCreado, PedidoPublicoIn

router = APIRouter(prefix="/publico", tags=["publico"])

PEDIDOS_POR_ORIGEN_HORA = 5
PEDIDOS_GLOBALES_HORA = 60


@router.get("/articulos", response_model=CatalogoPublico)
async def catalogo(db: DB) -> CatalogoPublico:
    """Solo artículos publicados. Nunca expone el stock exacto: solo si hay o no."""
    articulos = (
        (
            await db.execute(
                select(Articulo)
                .where(Articulo.publicado.is_(True), Articulo.activo.is_(True))
                .order_by(Articulo.codigo)
            )
        )
        .scalars()
        .all()
    )
    stock = await stock_de(db, [a.id for a in articulos])
    return CatalogoPublico(
        articulos=[
            ArticuloPublico(
                id=a.id, codigo=a.codigo, nombre=a.nombre, descripcion=a.descripcion,
                imagen_url=url_imagen(a.imagen), precio=a.precio_venta, disponible=stock[a.id] > 0,
            )
            for a in articulos
        ],
        whatsapp_negocio=settings.whatsapp_negocio,
    )  # fmt: skip


@router.post("/pedidos", response_model=PedidoCreado, status_code=status.HTTP_201_CREATED)
async def crear_pedido(datos: PedidoPublicoIn, request: Request, db: DB) -> PedidoCreado:
    """Un pedido es una solicitud: NO descuenta stock ni crea una venta."""
    ok = PedidoCreado(mensaje="¡Listo! Recibimos tu pedido y te escribiremos por WhatsApp.")
    if datos.sitio_web:
        return ok  # robot: se responde como si hubiera funcionado, sin guardar nada

    origen = origen_hash(request)
    desde = ahora() - timedelta(hours=1)
    del_origen = (
        await db.execute(
            select(func.count()).select_from(Pedido)
            .where(Pedido.origen_hash == origen, Pedido.creado_en >= desde)
        )
    ).scalar_one()  # fmt: skip
    globales = (
        await db.execute(select(func.count()).select_from(Pedido).where(Pedido.creado_en >= desde))
    ).scalar_one()
    if del_origen >= PEDIDOS_POR_ORIGEN_HORA or globales >= PEDIDOS_GLOBALES_HORA:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Has enviado varios pedidos seguidos. Inténtalo de nuevo en un rato.",
        )

    articulo = await db.get(Articulo, datos.articulo_id)
    if articulo is None or not articulo.publicado or not articulo.activo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese artículo ya no está disponible.")

    db.add(
        Pedido(
            articulo_id=articulo.id, nombre=datos.nombre, whatsapp=datos.whatsapp,
            cantidad=datos.cantidad, origen_hash=origen,
        )
    )  # fmt: skip
    await db.commit()
    return ok
