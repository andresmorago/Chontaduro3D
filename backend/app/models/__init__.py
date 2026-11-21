"""Importar todos los modelos aquí es lo que llena Base.metadata para Alembic."""

from app.models.articulo import Articulo, ArticuloColor, PrecioHistorial
from app.models.auditoria import RegistroAuditoria
from app.models.impresora import (
    ComandoImpresora,
    ConfigImpresora,
    EstadoImpresora,
    TrabajoImpresora,
)
from app.models.inventario import MovimientoInventario
from app.models.parametros import Parametros
from app.models.pedido import Pedido, PedidoItem
from app.models.produccion import Produccion, ProduccionFilamento, ProduccionItem
from app.models.spoolman import ChipBobina, ConsumoFilamento, EstadoSpoolman, RanuraBobina
from app.models.usuario import SesionRefresh, Usuario
from app.models.venta import Venta, VentaItem

__all__ = [
    "Articulo",
    "ArticuloColor",
    "ComandoImpresora",
    "ConsumoFilamento",
    "ConfigImpresora",
    "EstadoImpresora",
    "EstadoSpoolman",
    "MovimientoInventario",
    "Parametros",
    "Pedido",
    "PedidoItem",
    "PrecioHistorial",
    "Produccion",
    "ProduccionFilamento",
    "ProduccionItem",
    "ChipBobina",
    "RanuraBobina",
    "RegistroAuditoria",
    "SesionRefresh",
    "TrabajoImpresora",
    "Usuario",
    "Venta",
    "VentaItem",
]
