"""Descuento del filamento de cada trabajo de la impresora en Spoolman.

Lo ejecuta el servicio `impresora` (único que escribe en Spoolman, así un descuento no se manda dos
veces). Para cada trabajo que termina (o se corta) se crean sus líneas de consumo, se resuelve de
qué bobina salió cada filamento y se envía:

  sin_bobina ──(se elige/vincula una bobina)──▶ por_enviar ──▶ enviando ──▶ descontado
                                                                   └─(cortado a medias)─▶ revisar

Nunca se descuenta «a ciegas»: si no se sabe de qué bobina salió, queda `sin_bobina` y el panel pide
elegirla. Una línea `enviando` que no se confirmó pasa a `revisar` (no se sabe si Spoolman la
aplicó) en vez de reenviarse, para no descontar dos veces."""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ConsumoFilamento, EstadoSpoolman, RanuraBobina, TrabajoImpresora
from app.spoolman import asignacion
from app.spoolman.cliente import (
    Bobina,
    ClienteSpoolman,
    ErrorSpoolman,
    NoAlcanzable,
    NoExiste,
    Rechazo,
)

log = logging.getLogger("spoolman")

ENVIANDO_VENCE_S = 120  # una línea «enviando» más vieja que esto se dio por cortada
RANURA_EXTERNA = "254"
CENTAVO = Decimal("0.01")
INTENTOS_MAX = 5  # reintentos tras un error de servidor de Spoolman antes de pedir revisión


def titulo_ranura(ranura: str | None) -> str:
    """«2» → «Ranura 3»; «254» → «Externa»."""
    if ranura == RANURA_EXTERNA:
        return "Externa"
    return f"Ranura {int(ranura) + 1}" if ranura and ranura.isdigit() else "Ranura"


def nombre_ranura(ranura: str | None) -> str:
    """«2» → «ranura 3» (el AMS numera desde 0; las personas desde 1)."""
    if ranura == RANURA_EXTERNA:
        return "la bobina externa"
    return f"la ranura {int(ranura) + 1}" if ranura and ranura.isdigit() else "una ranura"


def _ahora() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- estado
async def guardar_estado(
    db: AsyncSession, *, conectado: bool, version: str | None, detalle: str | None
) -> EstadoSpoolman:
    """Actualiza la fila de estado. `desde` se fija la primera vez que se alcanza Spoolman."""
    fila = await db.get(EstadoSpoolman, 1)
    ahora = _ahora()
    if fila is None:
        fila = EstadoSpoolman(id=1)
        db.add(fila)
    fila.conectado, fila.detalle, fila.actualizado_en = conectado, detalle, ahora
    if conectado:
        fila.version, fila.ultimo_ok_en = version, ahora
        if fila.desde is None:
            fila.desde = ahora
    await db.flush()
    return fila


# ---------------------------------------------------------------- crear las líneas
def _gramos_a_descontar(t: TrabajoImpresora, plan: Decimal) -> tuple[Decimal, str | None]:
    """Un trabajo terminado gasta lo del archivo; uno cortado, la parte hecha (progreso)."""
    if t.estado == "terminado":
        return plan, None
    if t.progreso and t.progreso > 0:
        parte = (plan * Decimal(t.progreso) / 100).quantize(CENTAVO)
        return parte, f"Se cortó al {t.progreso} %: se descuenta esa parte."
    return Decimal(0), "Se cortó sin dato de avance: revisa en Spoolman si gastó filamento."


def _lineas_de(t: TrabajoImpresora) -> list[tuple[str | None, str | None, Decimal]]:
    """(tipo, color, gramos del archivo) por filamento. Si el trabajo solo trae el total, una
    línea sin tipo; si no trae nada, ninguna (no hay qué descontar)."""
    filas = []
    for f in t.filamentos or []:
        g = Decimal(str(f.get("gramos") or 0)).quantize(CENTAVO)
        if g > 0:
            filas.append(((f.get("tipo") or None), (f.get("color") or None), g))
    if not filas and t.gramos_total and t.gramos_total > 0:
        filas.append((None, None, Decimal(t.gramos_total).quantize(CENTAVO)))
    return filas


async def crear_lineas(db: AsyncSession, desde: datetime) -> int:
    """Crea las líneas de los trabajos cerrados después de `desde` que aún no las tienen."""
    tienen = select(ConsumoFilamento.trabajo_id).distinct()
    trabajos = (
        (
            await db.execute(
                select(TrabajoImpresora).where(
                    TrabajoImpresora.estado.in_(("terminado", "interrumpido")),
                    TrabajoImpresora.fin_en >= desde,
                    TrabajoImpresora.id.not_in(tienen),
                )
            )
        )
        .scalars()
        .all()
    )
    creadas = 0
    for t in trabajos:
        lineas = _lineas_de(t)
        pares = asignacion.emparejar(
            [{"tipo": tp, "color": c, "gramos": float(g)} for tp, c, g in lineas],
            t.bandejas or [],
        )
        for orden, ((tipo, color, plan), par) in enumerate(zip(lineas, pares, strict=True)):
            gramos, nota = _gramos_a_descontar(t, plan)
            db.add(
                ConsumoFilamento(
                    trabajo_id=t.id,
                    orden=orden,
                    tipo=tipo,
                    color=color,
                    gramos_plan=plan,
                    gramos=gramos,
                    ranura=(par.bandeja or {}).get("ranura"),
                    estado="omitido" if gramos == 0 else "sin_bobina",
                    detalle=nota,
                )  # fmt: skip
            )
            creadas += 1
        # Hay que ver las bandejas de cada línea otra vez al resolver: se hace en `resolver`.
    await db.flush()
    return creadas


# ------------------------------------------------------------------- resolver bobina
async def _bobina_de_bandeja(
    cliente: ClienteSpoolman,
    ranuras: dict[str, RanuraBobina],
    bobinas_por_tag: dict[str, Bobina],
    bandeja: dict,
) -> int | None:
    """Bobina de Spoolman para una bandeja vista: por chip RFID (vinculado en Spoolman) o por el
    vínculo manual de la ranura, si la bandeja sigue con lo mismo que al vincular."""
    tag = bandeja.get("tag")
    if tag:
        b = bobinas_por_tag.get(str(tag).upper())
        if b is not None:
            return b.id
        return None
    v = ranuras.get(str(bandeja.get("ranura")))
    if v is not None and asignacion.misma_bobina(
        v.tipo, v.color, bandeja.get("tipo"), bandeja.get("color")
    ):
        return v.spool_id
    return None


async def resolver(db: AsyncSession, cliente: ClienteSpoolman) -> int:
    """Busca bobina para las líneas `sin_bobina` que aún no la tienen. Devuelve cuántas resolvió."""
    pendientes = (
        (
            await db.execute(
                select(ConsumoFilamento).where(
                    ConsumoFilamento.estado == "sin_bobina", ConsumoFilamento.spool_id.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    if not pendientes:
        return 0
    ranuras = {r.ranura: r for r in (await db.execute(select(RanuraBobina))).scalars()}
    por_tag = {t: b for b in await cliente.bobinas() for t in b.tags}
    resueltas = 0
    for c in pendientes:
        t = await db.get(TrabajoImpresora, c.trabajo_id)
        bandeja = next((b for b in (t.bandejas or []) if b.get("ranura") == c.ranura), None)
        if c.ranura is None or bandeja is None:
            c.detalle = "No se pudo saber de qué ranura salió: elige la bobina."
            continue
        spool_id = await _bobina_de_bandeja(cliente, ranuras, por_tag, bandeja)
        if spool_id is not None:
            c.spool_id, c.estado, c.detalle = spool_id, "por_enviar", None
            resueltas += 1
        elif bandeja.get("tag"):
            c.detalle = (
                f"La bobina Bambu de {nombre_ranura(c.ranura)} aún no está vinculada "
                "a una bobina de Spoolman."
            )
        else:
            c.detalle = f"Elige la bobina que estaba en {nombre_ranura(c.ranura)}."
    await db.flush()
    return resueltas


# --------------------------------------------------------------------------- enviar
async def enviar(db: AsyncSession, cliente: ClienteSpoolman) -> dict[str, int]:
    """Manda a Spoolman las líneas `por_enviar`. Cada una se marca `enviando` y se confirma ANTES
    de llamar, y se pasa a `descontado` justo después: si el proceso muere entre medias, la línea
    queda `enviando` y luego `revisar` (no se reenvía sola)."""
    cuenta = {"descontadas": 0, "falladas": 0}

    # Una línea «enviando» vieja: el proceso murió a medias. No se sabe si se aplicó.
    vencidas = (
        (
            await db.execute(
                select(ConsumoFilamento).where(
                    ConsumoFilamento.estado == "enviando",
                    ConsumoFilamento.actualizado_en
                    < _ahora() - timedelta(seconds=ENVIANDO_VENCE_S),
                )
            )
        )
        .scalars()
        .all()
    )
    for c in vencidas:
        c.estado = "revisar"
        c.detalle = "Se cortó al enviar: confirma en Spoolman si se descontó."
    if vencidas:
        await db.commit()

    pendientes = (
        (
            await db.execute(
                select(ConsumoFilamento)
                .where(ConsumoFilamento.estado == "por_enviar")
                .order_by(ConsumoFilamento.actualizado_en)
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    for c in pendientes:
        if c.spool_id is None or c.gramos <= 0:
            c.estado = "sin_bobina" if c.spool_id is None else "omitido"
            await db.commit()
            continue
        c.estado, c.intentos = "enviando", c.intentos + 1
        await db.commit()
        try:
            await cliente.usar(c.spool_id, float(c.gramos))
        except NoExiste:
            c.estado, c.spool_id = "sin_bobina", None
            c.detalle = "Esa bobina ya no existe en Spoolman: elige otra."
            cuenta["falladas"] += 1
        except NoAlcanzable as e:
            # La petición ni salió: es seguro reintentar y no cuenta como intento.
            c.estado, c.intentos, c.detalle = (
                "por_enviar",
                c.intentos - 1,
                "Spoolman no responde; se reintenta.",
            )
            log.warning("Spoolman no alcanzable: %s", e)
            await db.commit()
            break  # sin Spoolman no tiene sentido seguir con las demás
        except Rechazo as e:
            # Spoolman contestó con error: NO aplicó el descuento.
            if e.reintentable and c.intentos < INTENTOS_MAX:
                c.estado, c.detalle = "por_enviar", f"{e} Se reintenta."
            else:
                c.estado, c.detalle = "revisar", f"{e} No se descontó: revisa Spoolman."
            cuenta["falladas"] += 1
            log.warning("Descuento de %s g en la bobina %s: %s", c.gramos, c.spool_id, e)
        except ErrorSpoolman as e:
            # No se vio la respuesta: pudo haberse aplicado igual, así que NO se reenvía sola.
            c.estado = "revisar"
            c.detalle = f"{e} Confirma en Spoolman si se descontó."[:200]
            cuenta["falladas"] += 1
            log.warning("Descuento de %s g en la bobina %s: %s", c.gramos, c.spool_id, e)
        else:
            c.estado, c.detalle, c.descontado_en = "descontado", None, _ahora()
            cuenta["descontadas"] += 1
            log.info("Spoolman: -%s g de la bobina %s", c.gramos, c.spool_id)
        await db.commit()
    return cuenta
