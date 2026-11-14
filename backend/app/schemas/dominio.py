from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.schemas.comunes import Dinero, DineroSalida, Entrada, Numero, Salida

MetodoPago = Literal["efectivo", "transferencia", "otro"]
EstadoPedido = Literal["nuevo", "contactado", "cerrado", "descartado"]
Cantidad = Field(ge=1, le=10_000)


# --- Artículos ---------------------------------------------------------------
# Encuadre de una foto (no destructivo): centro horizontal y vertical en % de la foto y zoom.
FotoX = Field(default=50, ge=0, le=100)
FotoZoom = Field(default=1, ge=1, le=4)


class ColorIn(Entrada):
    # Con id = un color que ya existe (conserva su foto); sin id = uno nuevo.
    id: UUID | None = None
    nombre: str = Field(min_length=1, max_length=30)
    hex: str = Field(default="#9ca3af", pattern=r"^#[0-9a-fA-F]{6}$")
    foto_x: float = FotoX
    foto_y: float = FotoX
    foto_zoom: float = FotoZoom

    @field_validator("nombre")
    @classmethod
    def _limpio(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("El color necesita un nombre.")
        return v

    @field_validator("hex")
    @classmethod
    def _minuscula(cls, v: str) -> str:
        return v.lower()


class ColorOut(Salida):
    id: UUID
    nombre: str
    hex: str
    imagen_url: str | None = None
    foto_x: float = 50
    foto_y: float = 50
    foto_zoom: float = 1


def _sin_repetidos(colores: list[ColorIn] | None) -> list[ColorIn] | None:
    if colores is None:
        return None
    vistos: set[str] = set()
    for c in colores:
        clave = c.nombre.casefold()
        if clave in vistos:
            raise ValueError(f"El color «{c.nombre}» está repetido.")
        vistos.add(clave)
    return colores


class ArticuloIn(Entrada):
    nombre: str = Field(min_length=1, max_length=120)
    descripcion: str = Field(default="", max_length=2000)
    precio_venta: Dinero
    stock_minimo: int = Field(default=0, ge=0, le=10_000)
    publicado: bool = True
    foto_x: float = FotoX
    foto_y: float = FotoX
    foto_zoom: float = FotoZoom
    colores: list[ColorIn] = Field(default_factory=list, max_length=20)

    @field_validator("colores")
    @classmethod
    def _colores_unicos(cls, v: list[ColorIn]) -> list[ColorIn]:
        return _sin_repetidos(v) or []


class ArticuloUpdate(Entrada):
    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    descripcion: str | None = Field(default=None, max_length=2000)
    precio_venta: Dinero | None = None
    stock_minimo: int | None = Field(default=None, ge=0, le=10_000)
    publicado: bool | None = None
    activo: bool | None = None
    foto_x: float | None = Field(default=None, ge=0, le=100)
    foto_y: float | None = Field(default=None, ge=0, le=100)
    foto_zoom: float | None = Field(default=None, ge=1, le=4)
    # None = no tocar los colores; una lista (aunque sea vacía) reemplaza la anterior.
    colores: list[ColorIn] | None = Field(default=None, max_length=20)

    @field_validator("colores")
    @classmethod
    def _colores_unicos(cls, v: list[ColorIn] | None) -> list[ColorIn] | None:
        return _sin_repetidos(v)


class StockColor(Salida):
    """Stock de un color de un artículo (`color_id` None = stock «sin color asignado»)."""

    color_id: UUID | None
    nombre: str | None
    hex: str | None
    stock: int


class ArticuloOut(Salida):
    id: UUID
    codigo: str
    nombre: str
    descripcion: str
    imagen_url: str | None
    foto_x: float = 50
    foto_y: float = 50
    foto_zoom: float = 1
    precio_venta: DineroSalida
    stock_minimo: int
    stock: int
    publicado: bool
    activo: bool
    colores: list[ColorOut] = []
    # Stock por color (solo en artículos con colores; el «sin color asignado» solo si hay stock).
    stock_colores: list[StockColor] = []


class PrecioHistorialOut(Salida):
    precio: DineroSalida
    cambiado_en: datetime


# --- Producción --------------------------------------------------------------
class ItemCantidad(Entrada):
    articulo_id: UUID
    # Obligatorio si el artículo se ofrece en colores; debe omitirse si no los tiene.
    color_id: UUID | None = None
    cantidad: int = Cantidad


class FilamentoIn(Entrada):
    descripcion: str = Field(default="", max_length=60)  # «PLA negro», «PETG transparente»…
    gramos: Decimal = Field(gt=0, le=Decimal("100000"), max_digits=10, decimal_places=2)


class ProduccionIn(Entrada):
    fecha: date | None = None
    nota: str | None = Field(default=None, max_length=300)
    items: list[ItemCantidad] = Field(min_length=1, max_length=100)
    # Filamento: o el TOTAL directo, o gramos POR filamento (el total es la suma). Ambos opcionales.
    gramos_total: Decimal | None = Field(
        default=None, gt=0, le=Decimal("100000"), max_digits=10, decimal_places=2
    )
    filamentos: list[FilamentoIn] = Field(default_factory=list, max_length=20)
    # Tiempo de impresión del lote, en minutos (máximo 30 días).
    minutos_impresion: int | None = Field(default=None, ge=1, le=60 * 24 * 30)
    # Carga histórica: False = queda en el historial y las métricas, pero NO suma al stock de hoy.
    afecta_inventario: bool = True
    # Opcionales: valores de energía propios de ESTE lote (si no, se usan los parámetros de hoy).
    # Útil al cargar lotes viejos, cuando el kWh o la impresora eran otros.
    precio_kwh: Decimal | None = Field(
        default=None, ge=0, le=Decimal("100000"), max_digits=12, decimal_places=2
    )
    potencia_w: Decimal | None = Field(
        default=None, gt=0, le=Decimal("20000"), max_digits=8, decimal_places=1
    )
    # Importar un trabajo de la impresora como este lote (solo al crear; al editar se ignora).
    trabajo_id: UUID | None = None


class ProduccionItemOut(Salida):
    articulo_id: UUID
    color_id: UUID | None = None
    color: str | None = None
    color_hex: str | None = None
    codigo: str
    nombre: str
    cantidad: int


class FilamentoOut(Salida):
    descripcion: str
    gramos: Numero


class ProduccionOut(Salida):
    id: UUID
    fecha: date
    nota: str | None
    creado_en: datetime
    items: list[ProduccionItemOut]
    afecta_inventario: bool = True
    gramos_total: Numero | None = None
    filamentos: list[FilamentoOut] = []
    minutos_impresion: int | None = None
    # Energía de ESTE lote, con la potencia y el precio del kWh vigentes cuando se registró.
    potencia_w: Numero | None = None
    precio_kwh: Numero | None = None
    kwh: Numero | None = None
    costo_energia: Numero | None = None
    # Nombre del trabajo de la impresora de donde salió este lote (si se importó).
    desde_impresora: str | None = None


class ParametrosIn(Entrada):
    precio_kwh: Decimal | None = Field(
        default=None, ge=0, le=Decimal("100000"), max_digits=12, decimal_places=2
    )
    potencia_impresora_w: Decimal | None = Field(
        default=None, gt=0, le=Decimal("20000"), max_digits=8, decimal_places=1
    )


class ParametrosOut(Salida):
    precio_kwh: Numero | None
    potencia_impresora_w: Numero | None


# --- Ventas ------------------------------------------------------------------
class VentaItemIn(Entrada):
    articulo_id: UUID
    color_id: UUID | None = None
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
    color_id: UUID | None = None
    color: str | None = None
    color_hex: str | None = None
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
    # Obligatorio en un artículo con colores (salvo para REDUCIR el stock «sin color asignado»).
    color_id: UUID | None = None
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
    color: str | None = None
    nota: str | None
    creado_en: datetime


# --- Pedidos -----------------------------------------------------------------
class PedidoItemIn(Entrada):
    articulo_id: UUID
    cantidad: int = Field(ge=1, le=99)
    # Obligatorio si el artículo tiene colores; debe ser uno de ellos.
    color: str = Field(default="", max_length=30)


class PedidoPublicoIn(Entrada):
    nombre: str = Field(min_length=2, max_length=80)
    whatsapp: str = Field(min_length=7, max_length=20)
    # El pedido: uno o varios renglones (mini carrito), hasta 20.
    items: list[PedidoItemIn] = Field(default_factory=list, max_length=20)
    # Formato anterior (un solo artículo): se convierte en un renglón.
    articulo_id: UUID | None = None
    cantidad: int | None = Field(default=None, ge=1, le=99)
    color: str = Field(default="", max_length=30)
    # Trampa para robots: un humano nunca ve este campo, así que debe llegar vacío.
    sitio_web: str = Field(default="", max_length=200)
    turnstile: str = Field(default="", max_length=2048)

    @model_validator(mode="after")
    def _a_renglones(self) -> "PedidoPublicoIn":
        if not self.items:
            if self.articulo_id is None or self.cantidad is None:
                raise ValueError("El pedido necesita al menos un artículo.")
            self.items = [
                PedidoItemIn(articulo_id=self.articulo_id, cantidad=self.cantidad, color=self.color)
            ]
        elif self.articulo_id is not None or self.cantidad is not None:
            raise ValueError("Usa «items» o el formato de un solo artículo, no los dos.")
        return self

    @field_validator("whatsapp")
    @classmethod
    def _telefono(cls, v: str) -> str:
        limpio = "".join(c for c in v if c.isdigit())
        if not 7 <= len(limpio) <= 15:
            raise ValueError("El WhatsApp debe tener entre 7 y 15 dígitos.")
        return ("+" if v.strip().startswith("+") else "") + limpio


class PedidoEstadoIn(Entrada):
    estado: EstadoPedido


class PedidoItemOut(Salida):
    articulo_id: UUID
    codigo: str
    articulo: str
    color: str | None = None
    cantidad: int
    # Precio de hoy del artículo (el precio final se acuerda al vender; esto es una referencia).
    precio: DineroSalida
    subtotal: DineroSalida


class PedidoOut(Salida):
    id: UUID
    nombre: str
    whatsapp: str
    items: list[PedidoItemOut]
    piezas: int
    total_estimado: DineroSalida
    estado: str
    creado_en: datetime


class PedidoCreado(Salida):
    ok: bool = True
    mensaje: str


# --- Público -----------------------------------------------------------------
class ColorPublicoOut(Salida):
    id: UUID
    nombre: str
    hex: str
    imagen_url: str | None = None
    foto_x: float = 50
    foto_y: float = 50
    foto_zoom: float = 1
    # Solo «hay / no hay»: el catálogo nunca expone el stock exacto.
    disponible: bool = False


class ArticuloPublico(Salida):
    id: UUID
    codigo: str
    nombre: str
    descripcion: str
    imagen_url: str | None
    foto_x: float = 50
    foto_y: float = 50
    foto_zoom: float = 1
    precio: DineroSalida
    disponible: bool
    colores: list[ColorPublicoOut] = []


class CatalogoPublico(Salida):
    articulos: list[ArticuloPublico]
    whatsapp_negocio: str
    turnstile_sitekey: str = ""


class ConfigPublica(Salida):
    turnstile_sitekey: str = ""


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
