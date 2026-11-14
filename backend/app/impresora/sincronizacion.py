"""Une el historial de Bambu Cloud con los trabajos de la base, sin duplicar ni pisar decisiones.

- Si el trabajo ya se detectó en vivo (mismo identificador, o mismo nombre y hora), se le
  completan los datos que falten (tiempo medido, gramos, filamentos).
- Si no, se crea como trabajo «por revisar» con origen «nube».
- Lo que la persona ya importó o ignoró NUNCA se revierte."""

from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.impresora.nube import Tarea
from app.models import TrabajoImpresora

VENTANA_MATCH = timedelta(minutes=45)


def _normal(t: str) -> str:
    return "".join(c for c in t.lower() if c.isalnum())


async def _buscar(db: AsyncSession, t: Tarea) -> TrabajoImpresora | None:
    por_id = (
        await db.execute(
            select(TrabajoImpresora)
            .where(or_(TrabajoImpresora.nube_id == t.id, TrabajoImpresora.tarea_id == t.id))
            .limit(1)
        )
    ).scalar_one_or_none()
    if por_id is not None:
        return por_id
    # Sin identificador común: mismo nombre y empezó casi a la misma hora.
    cercanos = (
        (
            await db.execute(
                select(TrabajoImpresora).where(
                    TrabajoImpresora.nube_id.is_(None),
                    TrabajoImpresora.inicio_en >= t.inicio - VENTANA_MATCH,
                    TrabajoImpresora.inicio_en <= t.inicio + VENTANA_MATCH,
                )
            )
        )
        .scalars()
        .all()
    )
    objetivo = _normal(t.titulo)
    for c in cercanos:
        if _normal(c.nombre) == objetivo:
            return c
    return None


async def aplicar(db: AsyncSession, tareas: list[Tarea]) -> dict[str, int]:
    """Guarda las tareas. Devuelve cuántas se crearon / completaron."""
    creadas = completadas = 0
    for t in sorted(tareas, key=lambda x: x.inicio):
        existente = await _buscar(db, t)
        if existente is None:
            db.add(
                TrabajoImpresora(
                    nombre=t.titulo,
                    tarea_id=t.id,
                    nube_id=t.id,
                    origen="nube",
                    estado=t.estado,
                    inicio_en=t.inicio,
                    inicio_observado=True,
                    fin_en=t.fin,
                    progreso=100 if t.estado == "terminado" else 0,
                    plate=t.plate,
                    minutos_medidos=t.minutos,
                    minutos_estimados=None,
                    gramos_total=t.gramos,
                    filamentos=t.filamentos or None,
                )  # fmt: skip
            )
            creadas += 1
            continue
        cambio = False
        if existente.nube_id is None:
            existente.nube_id, cambio = t.id, True
        if existente.gestion != "importado":
            # Lo que da la nube completa lo que falta; no pisa lo ya leído del .3mf.
            if t.minutos and existente.minutos_medidos != t.minutos:
                existente.minutos_medidos, cambio = t.minutos, True
            if existente.gramos_total is None and t.gramos:
                existente.gramos_total, cambio = t.gramos, True
            if not existente.filamentos and t.filamentos:
                existente.filamentos, cambio = t.filamentos, True
        completadas += int(cambio)
    await db.flush()
    return {"creadas": creadas, "completadas": completadas}
