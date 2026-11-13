from fastapi import APIRouter

from app.core import auditoria, energia
from app.core.deps import DB, PROTEGIDO, Admin
from app.models import Parametros
from app.schemas.dominio import ParametrosIn, ParametrosOut

router = APIRouter(prefix="/parametros", tags=["parametros"], dependencies=PROTEGIDO)


def _salida(p: Parametros) -> ParametrosOut:
    return ParametrosOut(precio_kwh=p.precio_kwh, potencia_impresora_w=p.potencia_impresora_w)


@router.get("", response_model=ParametrosOut)
async def ver(db: DB) -> ParametrosOut:
    p = await energia.parametros(db)
    await db.commit()
    return _salida(p)


@router.put("", response_model=ParametrosOut)
async def guardar(datos: ParametrosIn, db: DB, usuario: Admin) -> ParametrosOut:
    """Cambia los parámetros universales. Solo afecta a los lotes que se registren DESPUÉS:
    cada lote guarda la potencia y el precio del kWh con que se calculó."""
    p = await energia.parametros(db)
    antes = {"precio_kwh": p.precio_kwh, "potencia_w": p.potencia_impresora_w}
    p.precio_kwh = datos.precio_kwh
    p.potencia_impresora_w = datos.potencia_impresora_w
    auditoria.registrar(
        db, "parametros_cambiados", usuario_id=usuario.id,
        detalle={
            "antes": {k: float(v) if v is not None else None for k, v in antes.items()},
            "despues": {
                "precio_kwh": float(datos.precio_kwh) if datos.precio_kwh is not None else None,
                "potencia_w": float(datos.potencia_impresora_w)
                if datos.potencia_impresora_w is not None
                else None,
            },
        },
    )  # fmt: skip
    await db.commit()
    return _salida(p)
