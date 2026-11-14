from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, UploadFile, status
from sqlalchemy import select

from app.config import settings
from app.core import auditoria, imagenes
from app.core.deps import DB, PROTEGIDO, Admin
from app.core.inventario import Clave, bloquear_articulos, stock_de, stock_por_clave
from app.models import Articulo, ArticuloColor, PrecioHistorial
from app.schemas.dominio import (
    ArticuloIn,
    ArticuloOut,
    ArticuloUpdate,
    ColorIn,
    ColorOut,
    PrecioHistorialOut,
    StockColor,
)

router = APIRouter(prefix="/articulos", tags=["articulos"], dependencies=PROTEGIDO)


def url_imagen(nombre: str | None) -> str | None:
    return f"/api/media/{nombre}" if nombre else None


async def colores_de(db, ids: list[UUID]) -> dict[UUID, list[ColorOut]]:
    """Colores de varios artículos de una vez, en el orden en que se definieron."""
    resultado: dict[UUID, list[ColorOut]] = {i: [] for i in ids}
    if not ids:
        return resultado
    filas = await db.execute(
        select(ArticuloColor)
        .where(ArticuloColor.articulo_id.in_(ids))
        .order_by(ArticuloColor.articulo_id, ArticuloColor.orden)
    )
    for c in filas.scalars():
        resultado[c.articulo_id].append(
            ColorOut(
                id=c.id,
                nombre=c.nombre,
                hex=c.hex,
                imagen_url=url_imagen(c.imagen),
                foto_x=c.foto_x,
                foto_y=c.foto_y,
                foto_zoom=c.foto_zoom,
            )  # fmt: skip
        )
    return resultado


def _poner_colores(db, articulo_id: UUID, colores: list[ColorIn]) -> None:
    for n, c in enumerate(colores):
        db.add(
            ArticuloColor(
                articulo_id=articulo_id,
                orden=n,
                nombre=c.nombre,
                hex=c.hex,
                foto_x=c.foto_x,
                foto_y=c.foto_y,
                foto_zoom=c.foto_zoom,
            )  # fmt: skip
        )


def stock_colores_de(
    articulo_id: UUID, colores: list[ColorOut], por_clave: dict[Clave, int]
) -> list[StockColor]:
    """Desglose de stock por color de un artículo (vacío si no tiene colores). El stock «sin color
    asignado» (anterior a los colores) solo aparece mientras haya."""
    if not colores:
        return []
    filas = [
        StockColor(
            color_id=c.id, nombre=c.nombre, hex=c.hex, stock=por_clave.get((articulo_id, c.id), 0)
        )
        for c in colores
    ]
    sin_color = por_clave.get((articulo_id, None), 0)
    if sin_color:
        filas.append(StockColor(color_id=None, nombre=None, hex=None, stock=sin_color))
    return filas


async def salidas(db, articulos: list[Articulo]) -> list[ArticuloOut]:
    """Los artículos con su stock total, sus colores y el stock de cada color."""
    ids = [a.id for a in articulos]
    stock = await stock_de(db, ids)
    colores = await colores_de(db, ids)
    por_clave = await stock_por_clave(db, ids)
    return [
        a_salida(a, stock[a.id], colores[a.id], stock_colores_de(a.id, colores[a.id], por_clave))
        for a in articulos
    ]


async def _salida(db, a: Articulo) -> ArticuloOut:
    return (await salidas(db, [a]))[0]


def a_salida(
    a: Articulo,
    stock: int,
    colores: list[ColorOut] | None = None,
    stock_colores: list[StockColor] | None = None,
) -> ArticuloOut:
    return ArticuloOut(
        id=a.id, codigo=a.codigo, nombre=a.nombre, descripcion=a.descripcion,
        imagen_url=url_imagen(a.imagen), foto_x=a.foto_x, foto_y=a.foto_y, foto_zoom=a.foto_zoom,
        precio_venta=a.precio_venta,
        stock_minimo=a.stock_minimo, stock=stock, publicado=a.publicado, activo=a.activo,
        colores=colores or [], stock_colores=stock_colores or [],
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
    return await salidas(db, list((await db.execute(consulta)).scalars().all()))


@router.post("", response_model=ArticuloOut, status_code=status.HTTP_201_CREATED)
async def crear(datos: ArticuloIn, db: DB, usuario: Admin) -> ArticuloOut:
    a = Articulo(**datos.model_dump(exclude={"colores"}))
    db.add(a)
    await db.flush()
    await db.refresh(a)  # trae el código generado por la base
    _poner_colores(db, a.id, datos.colores)
    db.add(PrecioHistorial(articulo_id=a.id, precio=a.precio_venta))
    auditoria.registrar(db, "articulo_creado", usuario_id=usuario.id, detalle={"codigo": a.codigo})
    await db.commit()
    return await _salida(db, a)


@router.get("/{articulo_id}", response_model=ArticuloOut)
async def ver(articulo_id: UUID, db: DB) -> ArticuloOut:
    a = await _obtener(db, articulo_id)
    return await _salida(db, a)


async def _reemplazar_colores(db, a: Articulo, colores: list[ColorIn]) -> list[str]:
    """Deja los colores del artículo como pide la lista. Un color con `id` se conserva (con su
    foto); sin `id` es nuevo; los que no aparecen se borran. Devuelve las fotos huérfanas."""
    existentes = {
        c.id: c
        for c in (
            await db.execute(select(ArticuloColor).where(ArticuloColor.articulo_id == a.id))
        ).scalars()
    }
    ids = [c.id for c in colores if c.id is not None]
    if len(set(ids)) != len(ids) or any(i not in existentes for i in ids):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Hay colores que ya no existen. Recarga e inténtalo.",
        )
    conservar = set(ids)
    por_clave = await stock_por_clave(db, [a.id])
    con_stock = [
        f"{c.nombre} ({por_clave[(a.id, i)]})"
        for i, c in existentes.items()
        if i not in conservar and por_clave.get((a.id, i), 0) != 0
    ]
    if con_stock:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No se pueden quitar colores con unidades en inventario: "
            + ", ".join(con_stock)
            + ". Ajusta su stock a 0 antes (Inventario → Ajustar).",
        )
    huerfanas = []
    for i, c in existentes.items():
        if i not in conservar:
            if c.imagen:
                huerfanas.append(c.imagen)
            await db.delete(c)
    # Dos pasos: los nombres son únicos por artículo y una lista puede intercambiarlos.
    for i in conservar:
        existentes[i].nombre = f"~{i.hex[:20]}"
    await db.flush()
    for n, c in enumerate(colores):
        if c.id is None:
            db.add(
                ArticuloColor(
                    articulo_id=a.id,
                    orden=n,
                    nombre=c.nombre,
                    hex=c.hex,
                    foto_x=c.foto_x,
                    foto_y=c.foto_y,
                    foto_zoom=c.foto_zoom,
                )  # fmt: skip
            )
            continue
        o = existentes[c.id]
        o.orden, o.nombre, o.hex = n, c.nombre, c.hex
        o.foto_x, o.foto_y, o.foto_zoom = c.foto_x, c.foto_y, c.foto_zoom
    return huerfanas


@router.patch("/{articulo_id}", response_model=ArticuloOut)
async def actualizar(
    articulo_id: UUID, datos: ArticuloUpdate, db: DB, usuario: Admin
) -> ArticuloOut:
    await bloquear_articulos(db, [articulo_id])
    a = await _obtener(db, articulo_id)
    cambios = datos.model_dump(exclude_unset=True)
    colores = datos.colores if "colores" in cambios else None
    cambios.pop("colores", None)
    for campo in (
        "nombre", "precio_venta", "stock_minimo", "publicado", "activo",
        "foto_x", "foto_y", "foto_zoom",
    ):  # fmt: skip
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
    fotos_a_borrar: list[str] = []
    if colores is not None:
        fotos_a_borrar = await _reemplazar_colores(db, a, colores)
        auditoria.registrar(
            db, "colores_cambiados", usuario_id=usuario.id,
            detalle={"codigo": a.codigo, "colores": [c.nombre for c in colores]},
        )  # fmt: skip
    await db.commit()
    for nombre in fotos_a_borrar:  # solo después de confirmar: nunca dejar un color sin su foto
        imagenes.borrar(nombre)
    return await _salida(db, a)


@router.get("/{articulo_id}/precios", response_model=list[PrecioHistorialOut])
async def historial_de_precios(articulo_id: UUID, db: DB) -> list[PrecioHistorial]:
    await _obtener(db, articulo_id)
    filas = await db.execute(
        select(PrecioHistorial)
        .where(PrecioHistorial.articulo_id == articulo_id)
        .order_by(PrecioHistorial.cambiado_en.desc())
    )
    return list(filas.scalars())


def _exigir_tamano(request: Request) -> None:
    """Rechazo temprano por tamaño declarado (antes de leer el cuerpo entero)."""
    declarado = request.headers.get("content-length", "0")
    if declarado.isdigit() and int(declarado) > (settings.max_upload_mb + 1) * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"La imagen pesa más de {settings.max_upload_mb} MB. Achícala e inténtalo de nuevo.",
        )


@router.put("/{articulo_id}/imagen", response_model=ArticuloOut)
async def subir_imagen(
    articulo_id: UUID, archivo: UploadFile, request: Request, db: DB
) -> ArticuloOut:
    _exigir_tamano(request)
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
    return await _salida(db, a)


@router.delete("/{articulo_id}/imagen", response_model=ArticuloOut)
async def quitar_imagen(articulo_id: UUID, db: DB) -> ArticuloOut:
    await bloquear_articulos(db, [articulo_id])
    a = await _obtener(db, articulo_id)
    anterior, a.imagen = a.imagen, None
    await db.commit()
    imagenes.borrar(anterior)
    return await _salida(db, a)


async def _color_de(db, articulo_id: UUID, color_id: UUID) -> ArticuloColor:
    c = await db.get(ArticuloColor, color_id)
    if c is None or c.articulo_id != articulo_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese color no existe.")
    return c


@router.put("/{articulo_id}/colores/{color_id}/imagen", response_model=ArticuloOut)
async def subir_imagen_de_color(
    articulo_id: UUID, color_id: UUID, archivo: UploadFile, request: Request, db: DB
) -> ArticuloOut:
    """Foto opcional de un color: si la tiene, el catálogo la muestra al elegir ese color."""
    _exigir_tamano(request)
    await bloquear_articulos(db, [articulo_id])
    a = await _obtener(db, articulo_id)
    c = await _color_de(db, articulo_id, color_id)
    nueva = await imagenes.guardar(archivo)
    anterior, c.imagen = c.imagen, nueva
    try:
        await db.commit()
    except Exception:
        imagenes.borrar(nueva)
        raise
    imagenes.borrar(anterior)
    return await _salida(db, a)


@router.delete("/{articulo_id}/colores/{color_id}/imagen", response_model=ArticuloOut)
async def quitar_imagen_de_color(articulo_id: UUID, color_id: UUID, db: DB) -> ArticuloOut:
    await bloquear_articulos(db, [articulo_id])
    a = await _obtener(db, articulo_id)
    c = await _color_de(db, articulo_id, color_id)
    anterior, c.imagen = c.imagen, None
    await db.commit()
    imagenes.borrar(anterior)
    return await _salida(db, a)
