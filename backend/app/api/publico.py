from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select, text

from app.api.articulos import colores_de, url_imagen
from app.config import settings
from app.core import turnstile
from app.core.cliente import ip_cliente, origen_hash
from app.core.deps import DB
from app.core.inventario import stock_de
from app.core.tokens import ahora
from app.models import Articulo, Pedido
from app.schemas.dominio import (
    ArticuloPublico,
    CatalogoPublico,
    ConfigPublica,
    PedidoCreado,
    PedidoPublicoIn,
)

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
    colores = await colores_de(db, [a.id for a in articulos])
    return CatalogoPublico(
        articulos=[
            ArticuloPublico(
                id=a.id, codigo=a.codigo, nombre=a.nombre, descripcion=a.descripcion,
                imagen_url=url_imagen(a.imagen), foto_x=a.foto_x, foto_y=a.foto_y,
                foto_zoom=a.foto_zoom, precio=a.precio_venta, disponible=stock[a.id] > 0,
                colores=colores[a.id],
            )
            for a in articulos
        ],
        whatsapp_negocio=settings.whatsapp_negocio,
        turnstile_sitekey=settings.turnstile_sitekey if settings.turnstile_activo else "",
    )  # fmt: skip


@router.get("/config", response_model=ConfigPublica)
async def configuracion() -> ConfigPublica:
    """Lo que el navegador necesita antes de mostrar un formulario (la llave PÚBLICA del widget)."""
    return ConfigPublica(
        turnstile_sitekey=settings.turnstile_sitekey if settings.turnstile_activo else ""
    )


@router.post("/pedidos", response_model=PedidoCreado, status_code=status.HTTP_201_CREATED)
async def crear_pedido(datos: PedidoPublicoIn, request: Request, db: DB) -> PedidoCreado:
    """Un pedido es una solicitud: NO descuenta stock ni crea una venta."""
    ok = PedidoCreado(mensaje="¡Listo! Recibimos tu pedido y te escribiremos por WhatsApp.")
    if datos.sitio_web:
        return ok  # robot: se responde como si hubiera funcionado, sin guardar nada

    await turnstile.exigir(datos.turnstile, ip_cliente(request))
    origen = origen_hash(request)
    # Los límites son «contar y luego insertar»: se serializan con un candado de la transacción
    # (se suelta con el commit) para que una ráfaga concurrente no los sobrepase.
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('pedidos-publicos', 0))"))
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

    # Si el artículo se ofrece en colores, el cliente debe elegir uno de ellos; si no, ninguno.
    ofrecidos = (await colores_de(db, [articulo.id]))[articulo.id]
    color: str | None = None
    if ofrecidos:
        elegido = next(
            (
                c
                for c in ofrecidos
                if c.nombre.casefold() == " ".join(datos.color.split()).casefold()
            ),
            None,
        )
        if elegido is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Elige uno de los colores.")
        color = elegido.nombre

    db.add(
        Pedido(
            articulo_id=articulo.id, nombre=datos.nombre, whatsapp=datos.whatsapp,
            cantidad=datos.cantidad, color=color, origen_hash=origen,
        )
    )  # fmt: skip
    await db.commit()
    return ok
