"""Topes para datos que llegan de fuera (archivo .3mf, Bambu Cloud, la impresora).

Un valor absurdo (un archivo manipulado, un error de la nube) no debe terminar descontando miles de
kilos de una bobina ni desbordar una columna numérica: se descarta y se avisa en el log."""

import logging
import math
from decimal import Decimal

log = logging.getLogger("impresora")

MAX_GRAMOS_LINEA = 5000  # un filamento de un trabajo: una bobina pesa 1 kg (hasta 5 kg)
MAX_GRAMOS_TOTAL = 20000  # todos los filamentos de un trabajo


def _finito(v) -> float | None:
    try:
        n = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return n if math.isfinite(n) else None


def acotar_total(gramos, origen: str = "datos externos"):
    """El mismo valor si es razonable; None si pasa del tope o no es un número finito."""
    if gramos is None:
        return None
    n = _finito(gramos)
    if n is None or n > MAX_GRAMOS_TOTAL:
        log.warning("%s: peso total absurdo (%r g); se ignora.", origen, gramos)
        return None
    return gramos


def acotar_filamentos(filas: list[dict], origen: str = "datos externos") -> list[dict]:
    """Descarta los filamentos con gramos fuera de 0–5000 g por línea; si lo que queda suma más de
    20000 g, descarta todos (no hay forma segura de saber cuál está mal)."""
    buenas = []
    for f in filas or []:
        n = _finito(f.get("gramos")) if isinstance(f, dict) else None
        if n is None or n <= 0:
            continue
        if n > MAX_GRAMOS_LINEA:
            log.warning("%s: filamento de %r g (tope %s g); se descarta.", origen, n, MAX_GRAMOS_LINEA)
            continue
        buenas.append(f)
    total = sum((Decimal(str(f["gramos"])) for f in buenas), Decimal(0))
    if total > MAX_GRAMOS_TOTAL:
        log.warning("%s: suman %s g (tope %s g); se descartan.", origen, total, MAX_GRAMOS_TOTAL)
        return []
    return buenas


def acotar_progreso(p) -> int:
    """Progreso de impresión limitado a 0–100 (0 si no es un entero)."""
    return max(0, min(p, 100)) if isinstance(p, int) and not isinstance(p, bool) else 0
