"""Valores permitidos. Se guardan como texto con CHECK (sin tipos ENUM de Postgres:
agregar un valor es una migración trivial e idempotente)."""

TIPOS_MOVIMIENTO = ("produccion", "venta", "ajuste", "anulacion")
METODOS_PAGO = ("efectivo", "transferencia", "otro")
ESTADOS_PEDIDO = ("nuevo", "contactado", "cerrado", "descartado")


def en_lista(columna: str, valores: tuple[str, ...]) -> str:
    return f"{columna} IN ({', '.join(repr(v) for v in valores)})"
