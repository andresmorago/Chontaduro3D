from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.comunes import Entrada, Numero, Salida

EstadoConsumo = Literal["sin_bobina", "por_enviar", "enviando", "descontado", "omitido", "revisar"]


class BobinaOut(Salida):
    id: int
    nombre: str
    material: str | None = None
    color: str | None = None
    restante_g: float | None = None
    inicial_g: float | None = None
    ubicacion: str | None = None
    # Precio del rollo (en la moneda de Spoolman); sin él no hay costo de filamento.
    precio: float | None = None
    # Queda menos del umbral (`BAJO_G`): hay que ir pensando en otro rollo.
    bajo: bool = False


class EditarBobinaIn(Entrada):
    # Cuánto filamento queda en el rollo, pesado o estimado (g).
    restante_g: Annotated[Decimal, Field(ge=0, le=Decimal("20000"), decimal_places=1)] | None = None
    precio: Annotated[Decimal, Field(ge=0, le=Decimal("99999999"), decimal_places=2)] | None = None
    # True = rollo terminado: sale de las listas (su chip se sigue reconociendo).
    archivar: bool | None = None


class RepuestosOut(Salida):
    umbral_g: int
    # Rollos activos que NO están puestos en el AMS, los más bajos primero.
    bobinas: list[BobinaOut]


EstadoAlcance = Literal["alcanza", "justo", "no_alcanza", "dudoso", "sin_bobina", "sin_peso"]


class AlcanceLineaOut(Salida):
    tipo: str | None = None
    color: str | None = None
    gramos: float
    # La ranura en la que, según el tipo y color, va este filamento (None si no es inequívoco).
    ranura: str | None = None
    ranura_nombre: str | None = None
    bobina: str | None = None
    restante_g: float | None = None
    estado: EstadoAlcance


class AlcanceOut(Salida):
    # Trabajo que se está imprimiendo ahora (None si la impresora está libre).
    trabajo: str | None = None
    # El archivo aún no se leyó (o no trae gramos): no hay nada que comparar todavía.
    leyendo: bool = False
    lineas: list[AlcanceLineaOut] = []
    # Alguna línea no alcanza: hay que cambiar de rollo antes de que se acabe.
    alerta: bool = False


class EstadoSpoolmanOut(Salida):
    # Hay SPOOLMAN_URL: la integración está encendida.
    configurado: bool
    conectado: bool = False
    version: str | None = None
    ultimo_ok_en: datetime | None = None
    detalle: str | None = None
    # Enlace para abrir Spoolman desde la red de casa (no se usa para conectar).
    url_web: str | None = None
    # Descuentos que esperan una decisión de la persona.
    por_resolver: int = 0
    # Las bobinas Bambu con chip se registran solas en Spoolman al verlas en el AMS.
    autoregistro: bool = False


class VinculoOut(Salida):
    # «rfid»: el chip de la bobina Bambu está vinculado en Spoolman; «manual»: se eligió a mano
    # para esa ranura (bobinas sin chip).
    tipo: Literal["rfid", "manual"]
    # «desactualizado»: la ranura cambió de tipo o color desde que se vinculó (¿misma bobina?).
    estado: Literal["ok", "desactualizado", "sin_vincular"]
    bobina: BobinaOut | None = None


class RanuraOut(Salida):
    ranura: str
    # Número que ve la persona: 1–4 en el AMS, «Externa» para la bobina externa.
    nombre: str
    tipo: str | None = None
    marca: str | None = None
    color: str | None = None
    en_uso: bool = False
    # UID del chip RFID que la impresora leyó en esta ranura (None = sin chip o aún no lo lee).
    tag: str | None = None
    vinculo: VinculoOut


class VincularIn(Entrada):
    # None = desvincular.
    spool_id: int | None = Field(default=None, ge=1)
    # Si el chip RFID ya está en otra bobina de Spoolman: moverlo a esta.
    mover: bool = False


class CrearBobinaIn(Entrada):
    # Peso del filamento nuevo (una bobina Bambu trae 1000 g).
    peso_g: Annotated[Decimal, Field(gt=0, le=Decimal("20000"), decimal_places=1)] = Decimal(1000)
    # Cuánto filamento queda en el rollo (g), si ya está gastado. Vacío = lo del chip, o lleno.
    restante_g: Annotated[Decimal, Field(ge=0, le=Decimal("20000"), decimal_places=1)] | None = None
    # En la moneda que tenga Spoolman configurada; sin precio no hay costo de filamento.
    precio: Annotated[Decimal, Field(ge=0, le=Decimal("99999999"), decimal_places=2)] | None = None


class ConsumoOut(Salida):
    id: UUID
    trabajo_id: UUID
    trabajo: str | None = None
    fecha: datetime | None = None
    orden: int
    tipo: str | None = None
    color: str | None = None
    gramos_plan: Numero
    gramos: Numero
    ranura: str | None = None
    spool_id: int | None = None
    estado: EstadoConsumo
    detalle: str | None = None
    descontado_en: datetime | None = None


class ConsumoAccionIn(Entrada):
    accion: Literal["asignar", "omitir", "reintentar", "confirmar"]
    spool_id: int | None = Field(default=None, ge=1)
    # Ajustar los gramos a descontar (p. ej. un trabajo cortado). Solo con «asignar».
    gramos: Annotated[Decimal, Field(ge=0, le=Decimal("10000"), decimal_places=2)] | None = None
