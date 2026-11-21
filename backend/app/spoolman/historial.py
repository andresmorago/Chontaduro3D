"""Consumo ESTIMADO de los trabajos ya impresos, repartido entre las bobinas de Spoolman.

Los trabajos anteriores a conectar Spoolman no descuentan solos (no se sabe de qué rollo salió cada
filamento). Aquí se suman por tipo y color, se sugiere la bobina de ese color y se puede aplicar.
Por defecto solo MUESTRA lo que haría: es una estimación (el color del .3mf es el del programa de
laminado, no necesariamente el del rollo) y un mismo color puede haber salido de varios rollos.

Aplicar crea una línea por trabajo en `consumos_filamento` (estado por_enviar) y el servicio
`impresora` las envía con el mismo camino seguro de siempre; un trabajo que ya tiene líneas no se
vuelve a contar, así que repetir el comando no duplica nada.

    python -m app.spoolman.historial                       # vista previa
    python -m app.spoolman.historial --aplicar             # aplica lo sugerido (sin consumo previo)
    python -m app.spoolman.historial --aplicar --mapa "PLA#c31679=2,PLA#ffffff=3"
"""

import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ConsumoFilamento, TrabajoImpresora
from app.spoolman import asignacion
from app.spoolman.cliente import Bobina, ClienteSpoolman
from app.spoolman.consumo import _gramos_a_descontar, _lineas_de

COLOR_SUGERIDO = 60.0  # el color del programa de laminado rara vez es idéntico al del rollo
VENTAJA = 20.0


@dataclass
class Grupo:
    tipo: str
    color: str | None
    gramos: Decimal = Decimal(0)
    trabajos: int = 0
    desde: date | None = None
    hasta: date | None = None
    lineas: list[tuple[TrabajoImpresora, int, Decimal]] = field(default_factory=list)
    sugerida: Bobina | None = None
    distancia: float | None = None

    @property
    def clave(self) -> str:
        return f"{self.tipo}#{(self.color or '').lstrip('#')}"


def gastado(b: Bobina) -> float:
    return max((b.inicial_g or 0) - (b.restante_g or 0), 0.0)


def _compatible(material: str | None, tipo: str) -> bool:
    m, t = asignacion.norm_tipo(material), asignacion.norm_tipo(tipo)
    return bool(m and t) and (m == t or m.startswith(t) or t.startswith(m))


def sugerir(g: Grupo, bobinas: list[Bobina]) -> None:
    cand = sorted(
        (d, b.id, b)
        for b in bobinas
        if _compatible(b.material, g.tipo)
        and (d := asignacion.distancia(g.color, b.color)) is not None
    )
    if (
        cand
        and cand[0][0] <= COLOR_SUGERIDO
        and (len(cand) == 1 or cand[1][0] - cand[0][0] >= VENTAJA)
    ):
        g.distancia, g.sugerida = cand[0][0], cand[0][2]


async def calcular(db: AsyncSession, bobinas: list[Bobina]) -> list[Grupo]:
    tienen = select(ConsumoFilamento.trabajo_id).distinct()
    trabajos = (
        (
            await db.execute(
                select(TrabajoImpresora)
                .where(
                    TrabajoImpresora.estado.in_(("terminado", "interrumpido")),
                    TrabajoImpresora.fin_en.is_not(None),
                    TrabajoImpresora.id.not_in(tienen),
                )
                .order_by(TrabajoImpresora.fin_en)
            )
        )
        .scalars()
        .all()
    )
    grupos: dict[str, Grupo] = {}
    for t in trabajos:
        for orden, (tipo, color, plan) in enumerate(_lineas_de(t)):
            gramos, _ = _gramos_a_descontar(t, plan)
            if gramos <= 0 or tipo is None:
                continue
            g = grupos.setdefault(
                f"{tipo}#{(color or '').lstrip('#')}", Grupo(tipo=tipo, color=color)
            )
            dia = t.fin_en.date()
            g.gramos += gramos
            g.trabajos += 1
            g.desde, g.hasta = min(g.desde or dia, dia), max(g.hasta or dia, dia)
            g.lineas.append((t, orden, gramos))
    resultado = sorted(grupos.values(), key=lambda g: -g.gramos)
    for g in resultado:
        sugerir(g, bobinas)
    return resultado


async def aplicar(
    db: AsyncSession, grupos: list[Grupo], mapa: dict[str, int]
) -> tuple[int, Decimal]:
    """Crea las líneas (por_enviar) de los grupos con bobina elegida. Devuelve (líneas, gramos)."""
    n, total = 0, Decimal(0)
    for g in grupos:
        spool_id = mapa.get(g.clave)
        if spool_id is None:
            continue
        for t, orden, gramos in g.lineas:
            db.add(
                ConsumoFilamento(
                    trabajo_id=t.id,
                    orden=orden,
                    tipo=g.tipo,
                    color=g.color,
                    gramos_plan=gramos,
                    gramos=gramos,
                    spool_id=spool_id,
                    estado="por_enviar",
                    detalle="Estimado del historial (no se sabía de qué rollo salió).",
                )  # fmt: skip
            )
            n, total = n + 1, total + gramos
    await db.flush()
    return n, total


def _tabla(grupos: list[Grupo], bobinas: dict[int, Bobina]) -> str:
    filas = [
        f"{'filamento':<16}{'trabajos':>8}{'gramos':>9}  {'fechas':<23}"
        f"{'bobina sugerida':<44}{'ya gastado':>10}"
    ]
    for g in grupos:
        b = g.sugerida
        sug = (
            f"n.º {b.id} {b.nombre} (Δcolor {g.distancia:.0f})" if b else "— (sin bobina parecida)"
        )
        uso = f"{gastado(b):.0f} g" if b else ""
        fechas = f"{g.desde:%d/%m} → {g.hasta:%d/%m}"
        filas.append(
            f"{g.clave:<16}{g.trabajos:>8}{float(g.gramos):>9.1f}  {fechas:<23}"
            f"{sug[:43]:<44}{uso:>10}"
        )
    return "\n".join(filas)


def _leer_mapa(texto: str) -> dict[str, int]:
    pares = [p.split("=") for p in texto.split(",") if p.strip()]
    return {k.strip().lower().replace("##", "#"): int(v) for k, v in pares}


async def principal() -> None:
    from app.db import SessionLocal, engine

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument(
        "--aplicar", action="store_true", help="crea los descuentos (si no, solo muestra)"
    )
    ap.add_argument("--mapa", default="", help="«TIPO#color=n.º bobina,…» (si no, lo sugerido)")
    ap.add_argument(
        "--incluir-gastadas", action="store_true",
        help="también aplica a bobinas que YA tienen consumo registrado (por defecto se saltan)",
    )  # fmt: skip
    a = ap.parse_args()
    cliente = ClienteSpoolman(settings.spoolman_url)
    try:
        bobinas = await cliente.bobinas()
        por_id = {b.id: b for b in bobinas}
        async with SessionLocal() as db:
            grupos = await calcular(db, bobinas)
            print(_tabla(grupos, por_id))
            print(
                f"\nTotal estimado: {float(sum(g.gramos for g in grupos)):.1f} g "
                f"en {len(grupos)} colores."
            )
            if not a.aplicar:
                print(
                    "\nVista previa: no se cambió nada. "
                    "Usa --aplicar (y --mapa si quieres elegir bobinas)."
                )
                return
            mapa = _leer_mapa(a.mapa) if a.mapa else {
                g.clave: g.sugerida.id for g in grupos if g.sugerida
            }  # fmt: skip
            if not a.mapa and not a.incluir_gastadas:
                saltadas = {k for k, i in mapa.items() if gastado(por_id[i]) > 0}
                for k in saltadas:
                    print(
                        f"  se salta {k}: la bobina n.º {mapa[k]} ya tiene consumo "
                        "(usa --mapa o --incluir-gastadas)"
                    )
                mapa = {k: i for k, i in mapa.items() if k not in saltadas}
            faltan = [i for i in mapa.values() if i not in por_id]
            if faltan:
                raise SystemExit(f"Bobinas que no existen en Spoolman: {faltan}")
            n, total = await aplicar(db, grupos, mapa)
            await db.commit()
            print(
                f"\nCreados {n} descuentos ({float(total):.1f} g); "
                "el servicio los envía en unos segundos."
            )
    finally:
        await cliente.cerrar()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(principal())
