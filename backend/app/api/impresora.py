"""Datos y controles de la impresora, y los trabajos que detectó.

El backend NO habla con la impresora: lee lo que guarda el servicio `impresora` y le deja las
órdenes en una tabla. Así las credenciales de la impresora no pasan por la API web."""

from datetime import timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.config import settings
from app.core import auditoria
from app.core.deps import DB, PROTEGIDO, Admin
from app.core.tokens import ahora
from app.impresora.bambu import LIMITES, VELOCIDADES, validar_numero
from app.models import ComandoImpresora, EstadoImpresora, TrabajoImpresora
from app.schemas.impresora import (
    ComandoIn,
    ComandoOut,
    DatosImpresoraOut,
    FilamentoTrabajoOut,
    ImpresoraOut,
    NubeOut,
    TrabajoOut,
)

router = APIRouter(prefix="/impresora", tags=["impresora"], dependencies=PROTEGIDO)

LATIDO_MAX_S = 40  # el servicio escribe cada ~10 s


# --------------------------------------------------------------------------- estado
async def _pendientes(db) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(TrabajoImpresora)
            .where(TrabajoImpresora.gestion == "pendiente", TrabajoImpresora.estado != "en_curso")
        )
    ).scalar_one()


async def _estado(db) -> EstadoImpresora | None:
    return await db.get(EstadoImpresora, 1)


def _vivo(fila: EstadoImpresora | None) -> bool:
    return fila is not None and (ahora() - fila.actualizado_en).total_seconds() < LATIDO_MAX_S


@router.get("", response_model=ImpresoraOut)
async def ver(db: DB) -> ImpresoraOut:
    fila = await _estado(db)
    activo = _vivo(fila)
    datos = None
    if fila is not None and fila.datos and activo:
        datos = DatosImpresoraOut.model_validate(fila.datos)
    return ImpresoraOut(
        servicio_activo=activo,
        conectada=bool(activo and fila and fila.conectada),
        actualizado_en=fila.actualizado_en if fila else None,
        datos=datos,
        trabajos_pendientes=await _pendientes(db),
        nube=NubeOut(
            estado=fila.nube_estado if fila else None,
            sincronizada_en=fila.nube_sincronizada_en if fila else None,
            detalle=fila.nube_detalle if fila else None,
        ),
    )


# -------------------------------------------------------------------------- órdenes
_REQUIERE = {
    "pausar": ("imprimiendo",),
    "reanudar": ("pausada",),
    "cancelar": ("imprimiendo", "pausada", "preparando"),
    "velocidad": ("imprimiendo", "pausada"),
}
_NOMBRE = {
    "pausar": "Pausar",
    "reanudar": "Reanudar",
    "cancelar": "Cancelar impresión",
    "luz": "Luz",
    "velocidad": "Velocidad",
    "temp_boquilla": "La temperatura de la boquilla",
    "temp_cama": "La temperatura de la cama",
    "ventilador_pieza": "El ventilador de la pieza",
    "ventilador_aux": "El ventilador auxiliar",
}


@router.post("/comandos", response_model=ComandoOut, status_code=status.HTTP_202_ACCEPTED)
async def ordenar(datos: ComandoIn, db: DB, usuario: Admin) -> ComandoOut:
    """Deja una orden para el servicio. Se valida contra el estado actual para no mandar, por
    ejemplo, «reanudar» a una impresora que no está en pausa."""
    if datos.comando == "luz" and datos.valor not in ("on", "off"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "La luz es «on» u «off».")
    if datos.comando == "velocidad" and datos.valor not in VELOCIDADES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "La velocidad va de 1 a 4.")
    if datos.comando in LIMITES:
        try:
            validar_numero(datos.comando, datos.valor)
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    elif datos.comando not in ("luz", "velocidad") and datos.valor is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Esa orden no lleva valor.")

    fila = await _estado(db)
    if not _vivo(fila) or not fila or not fila.conectada:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "La impresora no está conectada en este momento. Revisa que esté encendida.",
        )
    estado = (fila.datos or {}).get("estado")
    permitidos = _REQUIERE.get(datos.comando)
    if permitidos and estado not in permitidos:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{_NOMBRE[datos.comando]} no aplica ahora: la impresora está «{estado}».",
        )

    # Dos clics seguidos no mandan dos órdenes iguales.
    reciente = (
        await db.execute(
            select(ComandoImpresora)
            .where(
                ComandoImpresora.comando == datos.comando,
                ComandoImpresora.valor == datos.valor,
                ComandoImpresora.estado == "pendiente",
                ComandoImpresora.creado_en > ahora() - timedelta(seconds=10),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if reciente is not None:
        return ComandoOut.model_validate(reciente)

    orden = ComandoImpresora(comando=datos.comando, valor=datos.valor, usuario_id=usuario.id)
    db.add(orden)
    auditoria.registrar(
        db, "impresora_orden", usuario_id=usuario.id,
        detalle={"comando": datos.comando, "valor": datos.valor, "estado": estado},
    )  # fmt: skip
    await db.commit()
    await db.refresh(orden)
    return ComandoOut.model_validate(orden)


@router.get("/comandos/{orden_id}", response_model=ComandoOut)
async def ver_orden(orden_id: int, db: DB) -> ComandoOut:
    orden = await db.get(ComandoImpresora, orden_id)
    if orden is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa orden no existe.")
    return ComandoOut.model_validate(orden)


# -------------------------------------------------------------------------- trabajos
def _salida(t: TrabajoImpresora) -> TrabajoOut:
    zona = ZoneInfo(settings.app_timezone)
    # Tiempo MEDIDO: el que informa Bambu Cloud; si no, el visto en vivo (si se vio el inicio).
    medido = None if t.estado == "en_curso" else t.minutos_medidos
    if medido is None and t.inicio_observado and t.fin_en is not None:
        medido = max(1, round((t.fin_en - t.inicio_en).total_seconds() / 60))
    minutos = medido if medido is not None else t.minutos_estimados
    return TrabajoOut(
        id=t.id, nombre=t.nombre, estado=t.estado, gestion=t.gestion,
        inicio_en=t.inicio_en, fin_en=t.fin_en,
        fecha=(t.fin_en or t.inicio_en).astimezone(zona).date(),
        progreso=t.progreso, minutos=minutos,
        origen=t.origen,
        minutos_origen="medido" if medido is not None else ("estimado" if minutos else None),
        minutos_estimados=t.minutos_estimados, gramos_total=t.gramos_total,
        filamentos=[FilamentoTrabajoOut(**f) for f in (t.filamentos or [])],
        produccion_id=t.produccion_id,
    )  # fmt: skip


@router.get("/trabajos", response_model=list[TrabajoOut])
async def trabajos(
    db: DB,
    gestion: Literal["pendiente", "importado", "ignorado"] = "pendiente",
    limite: int = 50,
) -> list[TrabajoOut]:
    limite = max(1, min(limite, 200))
    filas = await db.execute(
        select(TrabajoImpresora)
        .where(TrabajoImpresora.gestion == gestion)
        .order_by(func.coalesce(TrabajoImpresora.fin_en, TrabajoImpresora.inicio_en).desc())
        .limit(limite)
    )
    return [_salida(t) for t in filas.scalars()]


async def _cambiar_gestion(
    db, trabajo_id: UUID, usuario, desde: str, hasta: str, accion: str
) -> TrabajoOut:
    t = (
        await db.execute(
            select(TrabajoImpresora).where(TrabajoImpresora.id == trabajo_id).with_for_update()
        )
    ).scalar_one_or_none()
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese trabajo no existe.")
    if t.gestion != desde:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ese trabajo ya se importó." if t.gestion == "importado" else "Ese trabajo ya cambió.",
        )
    if t.estado == "en_curso" and hasta == "ignorado":
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese trabajo sigue en curso.")
    t.gestion = hasta
    auditoria.registrar(db, accion, usuario_id=usuario.id, detalle={"trabajo": t.nombre})
    await db.commit()
    return _salida(t)


@router.post("/trabajos/{trabajo_id}/ignorar", response_model=TrabajoOut)
async def ignorar(trabajo_id: UUID, db: DB, usuario: Admin) -> TrabajoOut:
    """No es una producción (prueba, prototipo, fallo…): sale de la bandeja, sin borrarse."""
    return await _cambiar_gestion(
        db, trabajo_id, usuario, "pendiente", "ignorado", "trabajo_ignorado"
    )


@router.post("/trabajos/{trabajo_id}/restaurar", response_model=TrabajoOut)
async def restaurar(trabajo_id: UUID, db: DB, usuario: Admin) -> TrabajoOut:
    return await _cambiar_gestion(
        db, trabajo_id, usuario, "ignorado", "pendiente", "trabajo_restaurado"
    )
