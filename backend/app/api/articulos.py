from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, UploadFile, status
from sqlalchemy import select

from app.config import settings
from app.core import auditoria, imagenes
from app.core.deps import DB, PROTEGIDO, Admin
from app.core.inventario import bloquear_articulos, stock_de
from app.models import Articulo, PrecioHistorial
from app.schemas.dominio import (
    ArticuloIn,
    ArticuloOut,
    ArticuloUpdate,
    PrecioHistorialOut,
)

router = APIRouter(prefix="/articulos", tags=["articulos"], dependencies=PROTEGIDO)


def url_imagen(nombre: str | None) -> str | None:
    return f"/api/media/{nombre}" if nombre else None


def a_salida(a: Articulo, stock: int) -> ArticuloOut:
    return ArticuloOut(
        id=a.id, codigo=a.codigo, nombre=a.nombre, descripcion=a.descripcion,
        imagen_url=url_imagen(a.imagen), precio_venta=a.precio_venta,
        stock_minimo=a.stock_minimo, stock=stock, publicado=a.publicado, activo=a.activo,
    )  # fmt: skip


async def _obtener(db, articulo_id: UUID) -> Articulo:
    a = await db.get(Articulo, articulo_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese artículo no existe.")
    return a


@router.get("", response_model=list[ArticuloOut])
async def listar(db: DB, incluir_inactivos: bool = False) -> list[ArticuloOut]:
    consulta = select(Articulo).order_by(Articulo.codigo)
    if not incluir_inactivos:
        consulta = consulta.where(Articulo.activo.is_(True))
    articulos = (await db.execute(consulta)).scalars().all()
    stock = await stock_de(db, [a.id for a in articulos])
    return [a_salida(a, stock[a.id]) for a in articulos]


@router.post("", response_model=ArticuloOut, status_code=status.HTTP_201_CREATED)
async def crear(datos: ArticuloIn, db: DB, usuario: Admin) -> ArticuloOut:
    a = Articulo(**datos.model_dump())
    db.add(a)
    await db.flush()
    await db.refresh(a)  # trae el código generado por la base
    db.add(PrecioHistorial(articulo_id=a.id, precio=a.precio_venta))
    auditoria.registrar(db, "articulo_creado", usuario_id=usuario.id, detalle={"codigo": a.codigo})
    await db.commit()
    return a_salida(a, 0)


@router.get("/{articulo_id}", response_model=ArticuloOut)
async def ver(articulo_id: UUID, db: DB) -> ArticuloOut:
    a = await _obtener(db, articulo_id)
    return a_salida(a, (await stock_de(db, [a.id]))[a.id])


@router.patch("/{articulo_id}", response_model=ArticuloOut)
async def actualizar(
    articulo_id: UUID, datos: ArticuloUpdate, db: DB, usuario: Admin
) -> ArticuloOut:
    await bloquear_articulos(db, [articulo_id])
    a = await _obtener(db, articulo_id)
    cambios = datos.model_dump(exclude_unset=True)
    for campo in ("nombre", "precio_venta", "stock_minimo", "publicado", "activo"):
        if campo in cambios and cambios[campo] is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"{campo} no puede quedar vacío."
            )
    precio_anterior = a.precio_venta
    for campo, valor in cambios.items():
        setattr(a, campo, valor)
    if "precio_venta" in cambios and a.precio_venta != precio_anterior:
        db.add(PrecioHistorial(articulo_id=a.id, precio=a.precio_venta))
        auditoria.registrar(
            db, "precio_cambiado", usuario_id=usuario.id,
            detalle={
                "codigo": a.codigo,
                "antes": float(precio_anterior),
                "despues": float(a.precio_venta),
            },
        )  # fmt: skip
    if cambios.get("activo") is False:
        a.publicado = False  # un artículo archivado no se muestra al público
    await db.commit()
    return a_salida(a, (await stock_de(db, [a.id]))[a.id])


@router.get("/{articulo_id}/precios", response_model=list[PrecioHistorialOut])
async def historial_de_precios(articulo_id: UUID, db: DB) -> list[PrecioHistorial]:
    await _obtener(db, articulo_id)
    filas = await db.execute(
        select(PrecioHistorial)
        .where(PrecioHistorial.articulo_id == articulo_id)
        .order_by(PrecioHistorial.cambiado_en.desc())
    )
    return list(filas.scalars())


@router.put("/{articulo_id}/imagen", response_model=ArticuloOut)
async def subir_imagen(
    articulo_id: UUID, archivo: UploadFile, request: Request, db: DB
) -> ArticuloOut:
    # Rechazo temprano por tamaño declarado (antes de leer el cuerpo entero).
    declarado = request.headers.get("content-length", "0")
    if declarado.isdigit() and int(declarado) > (settings.max_upload_mb + 1) * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"La imagen pesa más de {settings.max_upload_mb} MB. Achícala e inténtalo de nuevo.",
        )
    await bloquear_articulos(db, [articulo_id])
    a = await _obtener(db, articulo_id)
    nueva = await imagenes.guardar(archivo)
    anterior, a.imagen = a.imagen, nueva
    try:
        await db.commit()
    except Exception:
        imagenes.borrar(nueva)  # no dejar un archivo huérfano si la base no lo registró
        raise
    imagenes.borrar(anterior)
    return a_salida(a, (await stock_de(db, [a.id]))[a.id])


@router.delete("/{articulo_id}/imagen", response_model=ArticuloOut)
async def quitar_imagen(articulo_id: UUID, db: DB) -> ArticuloOut:
    await bloquear_articulos(db, [articulo_id])
    a = await _obtener(db, articulo_id)
    anterior, a.imagen = a.imagen, None
    await db.commit()
    imagenes.borrar(anterior)
    return a_salida(a, (await stock_de(db, [a.id]))[a.id])
