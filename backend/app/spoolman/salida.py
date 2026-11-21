"""Conversión de un descuento de filamento a su forma de API (la usan dos routers)."""

from app.models import ConsumoFilamento, TrabajoImpresora
from app.schemas.spoolman import ConsumoOut


def consumo_out(c: ConsumoFilamento, t: TrabajoImpresora | None = None) -> ConsumoOut:
    return ConsumoOut(
        id=c.id, trabajo_id=c.trabajo_id,
        trabajo=t.nombre if t else None, fecha=(t.fin_en or t.inicio_en) if t else None,
        orden=c.orden, tipo=c.tipo, color=c.color, gramos_plan=c.gramos_plan, gramos=c.gramos,
        ranura=c.ranura, spool_id=c.spool_id, estado=c.estado, detalle=c.detalle,
        descontado_en=c.descontado_en,
    )  # fmt: skip
