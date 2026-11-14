from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, func, select

from app.config import settings
from app.core import auditoria, energia
from app.core.deps import DB, PROTEGIDO, Admin
from app.core.inventario import (
    Clave,
    bloquear_articulos,
    colores_de_articulos,
    etiqueta,
    stock_por_clave,
    validar_colores,
)
from app.models import (
    Articulo,
    ArticuloColor,
    MovimientoInventario,
    Produccion,
    ProduccionFilamento,
    ProduccionItem,
    TrabajoImpresora,
)
from app.schemas.dominio import FilamentoOut, ProduccionIn, ProduccionItemOut, ProduccionOut

router = APIRouter(prefix="/produccion", tags=["produccion"], dependencies=PROTEGIDO)


def hoy() -> date:
    from datetime import datetime

    return datetime.now(ZoneInfo(settings.app_timezone)).date()


DIAS_ATRAS_VENTAS = 31
# La producción admite carga retrospectiva: hasta 5 años hacia atrás.
DIAS_ATRAS_PRODUCCION = 5 * 366


def validar_fecha(fecha: date | None, max_dias: int = DIAS_ATRAS_VENTAS) -> date:
    """Hoy por defecto; se permite registrar hacia atrás hasta `max_dias`, nunca el futuro."""
    h = hoy()
    f = fecha or h
    if f > h:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "La fecha no puede ser futura.")
    if f < h - timedelta(days=max_dias):
        limite = "31 días" if max_dias == DIAS_ATRAS_VENTAS else "5 años"
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Solo puedes registrar hasta {limite} atrás."
        )
    return f


async def _salida(db, produccion: Produccion) -> ProduccionOut:
    filas = await db.execute(
        select(ProduccionItem, Articulo, ArticuloColor)
        .join(Articulo, Articulo.id == ProduccionItem.articulo_id)
        .outerjoin(ArticuloColor, ArticuloColor.id == ProduccionItem.color_id)
        .where(ProduccionItem.produccion_id == produccion.id)
        .order_by(Articulo.codigo, ArticuloColor.orden)
    )
    items = [
        ProduccionItemOut(
            articulo_id=a.id, color_id=i.color_id, color=c.nombre if c else None,
            color_hex=c.hex if c else None, codigo=a.codigo, nombre=a.nombre, cantidad=i.cantidad,
        )
        for i, a, c in filas
    ]  # fmt: skip
    filamentos = [
        FilamentoOut(descripcion=f.descripcion, gramos=f.gramos)
        for f in (
            await db.execute(
                select(ProduccionFilamento)
                .where(ProduccionFilamento.produccion_id == produccion.id)
                .order_by(ProduccionFilamento.orden)
            )
        ).scalars()
    ]
    desde = (
        await db.execute(
            select(TrabajoImpresora.nombre).where(TrabajoImpresora.produccion_id == produccion.id)
        )
    ).scalar_one_or_none()
    return ProduccionOut(
        desde_impresora=desde,
        id=produccion.id, fecha=produccion.fecha, nota=produccion.nota,
        afecta_inventario=produccion.afecta_inventario,
        creado_en=produccion.creado_en, items=items, gramos_total=produccion.gramos_total,
        filamentos=filamentos, minutos_impresion=produccion.minutos_impresion,
        potencia_w=produccion.potencia_w, precio_kwh=produccion.precio_kwh,
        kwh=produccion.kwh, costo_energia=produccion.costo_energia,
    )  # fmt: skip


def _cantidades(datos: ProduccionIn) -> dict[Clave, int]:
    """Piezas por (artículo, color): la misma pareja en varias líneas se suma."""
    cantidades: dict[Clave, int] = defaultdict(int)
    for item in datos.items:
        cantidades[(item.articulo_id, item.color_id)] += item.cantidad
    return dict(cantidades)


def _gramos_del_lote(datos: ProduccionIn) -> Decimal | None:
    """Filamento: o el total directo, o por filamento (el total es la suma). Si vienen los dos,
    deben cuadrar."""
    gramos_total = datos.gramos_total
    if datos.filamentos:
        suma = sum((f.gramos for f in datos.filamentos), Decimal(0))
        if gramos_total is not None and abs(gramos_total - suma) > Decimal("0.01"):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"El total ({gramos_total} g) no coincide con la suma por filamento ({suma} g).",
            )
        gramos_total = suma
    return gramos_total


def _poner_detalle(db, p: Produccion, datos: ProduccionIn, cantidades: dict[Clave, int]) -> None:
    for n, f in enumerate(datos.filamentos):
        db.add(
            ProduccionFilamento(
                produccion_id=p.id, orden=n, descripcion=f.descripcion, gramos=f.gramos
            )
        )
    for (articulo_id, color_id), cantidad in cantidades.items():
        db.add(
            ProduccionItem(
                produccion_id=p.id, articulo_id=articulo_id, color_id=color_id, cantidad=cantidad
            )
        )


@router.post("", response_model=ProduccionOut, status_code=status.HTTP_201_CREATED)
async def registrar(datos: ProduccionIn, db: DB, usuario: Admin) -> ProduccionOut:
    cantidades = _cantidades(datos)
    ids = {a for a, _ in cantidades}
    articulos = await bloquear_articulos(db, ids)

    desconocidos = ids - set(articulos)
    archivados = [a.nombre for a in articulos.values() if not a.activo]
    if desconocidos or archivados:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Hay artículos que no existen o están archivados"
            + (f": {', '.join(archivados)}." if archivados else "."),
        )
    # Producir un artículo con colores exige decir de qué color salió cada pieza.
    validar_colores(cantidades, articulos, await colores_de_articulos(db, ids))

    gramos_total = _gramos_del_lote(datos)

    # Si viene de un trabajo de la impresora: debe existir, haber terminado de imprimirse y no
    # haberse importado ya. Se bloquea la fila para que dos importaciones a la vez no lo dupliquen.
    trabajo = None
    if datos.trabajo_id is not None:
        trabajo = (
            await db.execute(
                select(TrabajoImpresora)
                .where(TrabajoImpresora.id == datos.trabajo_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if trabajo is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Ese trabajo no existe.")
        if trabajo.estado == "en_curso":
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Ese trabajo sigue imprimiéndose: espera a que termine."
            )
        if trabajo.gestion != "pendiente":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Ese trabajo ya se importó." if trabajo.gestion == "importado"
                else "Ese trabajo está ignorado: restáuralo para importarlo.",
            )  # fmt: skip

    # Energía con los parámetros de HOY (o los propios del lote), congelados en él: cambiarlos
    # después no reescribe el pasado.
    param = await energia.parametros(db)
    potencia = datos.potencia_w if datos.potencia_w is not None else param.potencia_impresora_w
    precio = datos.precio_kwh if datos.precio_kwh is not None else param.precio_kwh
    kwh, costo = energia.calcular(datos.minutos_impresion, potencia, precio)

    p = Produccion(
        fecha=validar_fecha(datos.fecha, DIAS_ATRAS_PRODUCCION), nota=datos.nota or None,
        afecta_inventario=datos.afecta_inventario, gramos_total=gramos_total,
        minutos_impresion=datos.minutos_impresion,
        potencia_w=potencia if datos.minutos_impresion else None,
        precio_kwh=precio if datos.minutos_impresion else None,
        kwh=kwh, costo_energia=costo,
    )  # fmt: skip
    db.add(p)
    await db.flush()
    if trabajo is not None:
        trabajo.gestion, trabajo.produccion_id = "importado", p.id
    _poner_detalle(db, p, datos, cantidades)
    if datos.afecta_inventario:  # carga histórica: solo historial y métricas, sin tocar el stock
        for (articulo_id, color_id), cantidad in cantidades.items():
            db.add(
                MovimientoInventario(
                    articulo_id=articulo_id,
                    color_id=color_id,
                    tipo="produccion",
                    cantidad=cantidad,
                    produccion_id=p.id,
                )
            )
    auditoria.registrar(
        db, "produccion_registrada", usuario_id=usuario.id,
        detalle={
            "unidades": sum(cantidades.values()),
            "fecha": datos.fecha.isoformat() if datos.fecha else None,
            "afecta_inventario": datos.afecta_inventario,
            "trabajo_impresora": trabajo.nombre if trabajo else None,
        },
    )  # fmt: skip
    await db.commit()
    await db.refresh(p)
    return await _salida(db, p)


@router.put("/{produccion_id}", response_model=ProduccionOut)
async def modificar(
    produccion_id: UUID, datos: ProduccionIn, db: DB, usuario: Admin
) -> ProduccionOut:
    """Corrige un lote ya guardado (reemplaza sus datos). El inventario se ajusta SOLO por la
    diferencia, con un movimiento de ajuste: el libro mayor nunca se reescribe."""
    p = (
        await db.execute(select(Produccion).where(Produccion.id == produccion_id).with_for_update())
    ).scalar_one_or_none()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese lote no existe.")

    cantidades = _cantidades(datos)
    previos: dict[Clave, int] = {
        (a, c): n
        for a, c, n in await db.execute(
            select(
                ProduccionItem.articulo_id, ProduccionItem.color_id, ProduccionItem.cantidad
            ).where(ProduccionItem.produccion_id == p.id)
        )
    }
    # Lo que este lote tiene hoy en el libro mayor (su alta y las correcciones anteriores).
    efecto_actual: dict[Clave, int] = {
        (a, c): int(n)
        for a, c, n in await db.execute(
            select(
                MovimientoInventario.articulo_id,
                MovimientoInventario.color_id,
                func.sum(MovimientoInventario.cantidad),
            )
            .where(MovimientoInventario.produccion_id == p.id)
            .group_by(MovimientoInventario.articulo_id, MovimientoInventario.color_id)
        )
    }
    ids = {a for a, _ in cantidades} | {a for a, _ in previos} | {a for a, _ in efecto_actual}
    articulos = await bloquear_articulos(db, ids)
    colores = await colores_de_articulos(db, ids)

    desconocidos = {a for a, _ in cantidades} - set(articulos)
    # Un artículo archivado después de producirse puede seguir en su lote, pero no entrar a otro.
    previos_articulos = {a for a, _ in previos}
    archivados = [
        articulos[a].nombre
        for a in {a for a, _ in cantidades}
        if a in articulos and not articulos[a].activo and a not in previos_articulos
    ]
    if desconocidos or archivados:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Hay artículos que no existen o están archivados"
            + (f": {', '.join(archivados)}." if archivados else "."),
        )
    # Las líneas nuevas deben traer color si el artículo los tiene; una línea que ya estaba (p. ej.
    # de antes de que existieran los colores) puede seguir sin él.
    validar_colores([k for k in cantidades if k not in previos], articulos, colores)

    efecto_nuevo = cantidades if datos.afecta_inventario else {}
    delta = {
        k: efecto_nuevo.get(k, 0) - efecto_actual.get(k, 0)
        for k in set(efecto_nuevo) | set(efecto_actual)
    }
    delta = {k: d for k, d in delta.items() if d != 0}
    quitan = {k: -d for k, d in delta.items() if d < 0}
    if quitan:
        stock = await stock_por_clave(db, {a for a, _ in quitan})
        faltan = [
            f"{etiqueta(articulos[a], c, colores)}: quitarías {n} y solo hay {stock.get((a, c), 0)}"
            for (a, c), n in quitan.items()
            if stock.get((a, c), 0) < n
        ]
        if faltan:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "No se puede reducir este lote: parte de esas piezas ya salió del inventario. "
                + "; ".join(faltan)
                + ".",
            )

    gramos_total = _gramos_del_lote(datos)
    # La energía del lote ya estaba congelada: se conserva salvo que se indiquen otros valores.
    # Si antes no tenía tiempo, se usan los parámetros de hoy.
    param = await energia.parametros(db)
    potencia = (
        datos.potencia_w if datos.potencia_w is not None
        else p.potencia_w if p.potencia_w is not None
        else param.potencia_impresora_w
    )  # fmt: skip
    precio = (
        datos.precio_kwh if datos.precio_kwh is not None
        else p.precio_kwh if p.precio_kwh is not None
        else param.precio_kwh
    )  # fmt: skip
    kwh, costo = energia.calcular(datos.minutos_impresion, potencia, precio)

    antes = {
        "fecha": p.fecha.isoformat(), "afecta_inventario": p.afecta_inventario,
        "unidades": sum(previos.values()),
    }  # fmt: skip
    p.fecha = validar_fecha(datos.fecha, DIAS_ATRAS_PRODUCCION)
    p.nota = datos.nota or None
    p.afecta_inventario = datos.afecta_inventario
    p.gramos_total = gramos_total
    p.minutos_impresion = datos.minutos_impresion
    p.potencia_w = potencia if datos.minutos_impresion else None
    p.precio_kwh = precio if datos.minutos_impresion else None
    p.kwh, p.costo_energia = kwh, costo

    await db.execute(delete(ProduccionItem).where(ProduccionItem.produccion_id == p.id))
    await db.execute(delete(ProduccionFilamento).where(ProduccionFilamento.produccion_id == p.id))
    _poner_detalle(db, p, datos, cantidades)
    for (articulo_id, color_id), d in sorted(
        delta.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))
    ):
        db.add(
            MovimientoInventario(
                articulo_id=articulo_id, color_id=color_id, tipo="ajuste", cantidad=d,
                produccion_id=p.id, nota=f"Corrección del lote del {p.fecha.isoformat()}",
            )
        )  # fmt: skip
    auditoria.registrar(
        db, "produccion_modificada", usuario_id=usuario.id,
        detalle={
            "antes": antes,
            "despues": {
                "fecha": p.fecha.isoformat(), "afecta_inventario": p.afecta_inventario,
                "unidades": sum(cantidades.values()),
            },
        },
    )  # fmt: skip
    await db.commit()
    await db.refresh(p)
    return await _salida(db, p)


@router.get("", response_model=list[ProduccionOut])
async def listar(db: DB, limite: int = 30) -> list[ProduccionOut]:
    limite = max(1, min(limite, 100))
    filas = (
        await db.execute(
            select(Produccion)
            .order_by(Produccion.fecha.desc(), Produccion.creado_en.desc())
            .limit(limite)
        )
    ).scalars()
    return [await _salida(db, p) for p in filas]
