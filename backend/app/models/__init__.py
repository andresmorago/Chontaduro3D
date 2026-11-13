"""Importar todos los modelos aquí es lo que llena Base.metadata para Alembic."""

from app.models.articulo import Articulo, PrecioHistorial
from app.models.auditoria import RegistroAuditoria
from app.models.inventario import MovimientoInventario
from app.models.parametros import Parametros
from app.models.pedido import Pedido
from app.models.produccion import Produccion, ProduccionFilamento, ProduccionItem
from app.models.usuario import SesionRefresh, Usuario
from app.models.venta import Venta, VentaItem

__all__ = [
    "Articulo",
    "MovimientoInventario",
    "Parametros",
    "Pedido",
    "PrecioHistorial",
    "Produccion",
    "ProduccionFilamento",
    "ProduccionItem",
    "RegistroAuditoria",
    "SesionRefresh",
    "Usuario",
    "Venta",
    "VentaItem",
]
