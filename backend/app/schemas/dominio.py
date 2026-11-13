from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.comunes import Dinero, DineroSalida, Entrada, Salida

MetodoPago = Literal["efectivo", "transferencia", "otro"]
EstadoPedido = Literal["nuevo", "contactado", "cerrado", "descartado"]
Cantidad = Field(ge=1, le=10_000)


# --- Artículos ---------------------------------------------------------------
class ArticuloIn(Entrada):
    nombre: str = Field(min_length=1, max_length=120)
    descripcion: str = Field(default="", max_length=2000)
    precio_venta: Dinero
    stock_minimo: int = Field(default=0, ge=0, le=10_000)
    publicado: bool = True


class ArticuloUpdate(Entrada):
    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    descripcion: str | None = Field(default=None, max_length=2000)
    precio_venta: Dinero | None = None
    stock_minimo: int | None = Field(default=None, ge=0, le=10_000)
    publicado: bool | None = None
    activo: bool | None = None


class ArticuloOut(Salida):
    id: UUID
    codigo: str
    nombre: str
    descripcion: str
    imagen_url: str | None
    precio_venta: DineroSalida
    stock_minimo: int
    stock: int
    publicado: bool
    activo: bool


class PrecioHistorialOut(Salida):
    precio: DineroSalida
    cambiado_en: datetime


# --- Producción --------------------------------------------------------------
class ItemCantidad(Entrada):
    articulo_id: UUID
    cantidad: int = Cantidad


class ProduccionIn(Entrada):
    fecha: date | None = None
    nota: str | None = Field(default=None, max_length=300)
    items: list[ItemCantidad] = Field(min_length=1, max_length=100)


class ProduccionItemOut(Salida):
    articulo_id: UUID
    codigo: str
    nombre: str
    cantidad: int


class ProduccionOut(Salida):
    id: UUID
    fecha: date
    nota: str | None
    creado_en: datetime
    items: list[ProduccionItemOut]


# --- Ventas ------------------------------------------------------------------
class VentaItemIn(Entrada):
    articulo_id: UUID
    cantidad: int = Cantidad
    # Opcional: vender con descuento. Si falta, se usa el precio maestro de ese momento.
    precio_unitario: Dinero | None = None


class VentaIn(Entrada):
    fecha: date | None = None
    cliente: str | None = Field(default=None, max_length=120)
    metodo_pago: MetodoPago = "efectivo"
    nota: str | None = Field(default=None, max_length=300)
    items: list[VentaItemIn] = Field(min_length=1, max_length=100)

    @field_validator("cliente", "nota")
    @classmethod
    def _vacio_a_none(cls, v: str | None) -> str | None:
        return v or None


class VentaItemOut(Salida):
    articulo_id: UUID
    codigo: str
    nombre: str
    cantidad: int
    precio_unitario: DineroSalida


class VentaOut(Salida):
    id: UUID
    fecha: date
    cliente: str | None
    metodo_pago: str
    nota: str | None
    total: DineroSalida
    anulada: bool
    creado_en: datetime
    items: list[VentaItemOut]


# --- Inventario --------------------------------------------------------------
class AjusteIn(Entrada):
    articulo_id: UUID
    cantidad: int = Field(ge=-10_000, le=10_000)
    nota: str = Field(min_length=3, max_length=300)

    @field_validator("cantidad")
    @classmethod
    def _no_cero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("La cantidad del ajuste no puede ser 0.")
        return v


class MovimientoOut(Salida):
    id: int
    articulo_id: UUID
    codigo: str
    nombre: str
    tipo: str
    cantidad: int
    nota: str | None
    creado_en: datetime


# --- Pedidos -----------------------------------------------------------------
class PedidoPublicoIn(Entrada):
    articulo_id: UUID
    nombre: str = Field(min_length=2, max_length=80)
    whatsapp: str = Field(min_length=7, max_length=20)
    cantidad: int = Field(ge=1, le=99)
    # Trampa para robots: un humano nunca ve este campo, así que debe llegar vacío.
    sitio_web: str = Field(default="", max_length=200)

    @field_validator("whatsapp")
    @classmethod
    def _telefono(cls, v: str) -> str:
        limpio = "".join(c for c in v if c.isdigit())
        if not 7 <= len(limpio) <= 15:
            raise ValueError("El WhatsApp debe tener entre 7 y 15 dígitos.")
        return ("+" if v.strip().startswith("+") else "") + limpio


class PedidoEstadoIn(Entrada):
    estado: EstadoPedido


class PedidoOut(Salida):
    id: UUID
    articulo_id: UUID
    codigo: str
    articulo: str
    nombre: str
    whatsapp: str
    cantidad: int
    estado: str
    creado_en: datetime


class PedidoCreado(Salida):
    ok: bool = True
    mensaje: str


# --- Público -----------------------------------------------------------------
class ArticuloPublico(Salida):
    id: UUID
    codigo: str
    nombre: str
    descripcion: str
    imagen_url: str | None
    precio: DineroSalida
    disponible: bool


class CatalogoPublico(Salida):
    articulos: list[ArticuloPublico]
    whatsapp_negocio: str


# --- Panel -------------------------------------------------------------------
class VentasDia(Salida):
    fecha: date
    total: DineroSalida
    cantidad: int


class StockBajo(Salida):
    articulo_id: UUID
    codigo: str
    nombre: str
    stock: int
    stock_minimo: int


class PanelOut(Salida):
    hoy: VentasDia
    ultimos_dias: list[VentasDia]
    stock_bajo: list[StockBajo]
    pedidos_nuevos: int
    articulos_activos: int
    unidades_en_stock: int
