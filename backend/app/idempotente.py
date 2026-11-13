"""Ayudantes para escribir migraciones que se pueden repetir.

Una migración idempotente deja la base igual si se corre de nuevo, o sobre un
esquema que ya tiene parte de lo que crea (p. ej. tras un fallo a medias o un
retoque manual). Cada ayudante mira primero el estado real de la base.
"""

import sqlalchemy as sa

from alembic import op


def _inspector() -> sa.Inspector:
    # Inspector nuevo cada vez: el de antes guarda en caché lo que ya cambió.
    return sa.inspect(op.get_bind())


def tabla_existe(nombre: str) -> bool:
    return _inspector().has_table(nombre)


def columna_existe(tabla: str, columna: str) -> bool:
    if not tabla_existe(tabla):
        return False
    return any(c["name"] == columna for c in _inspector().get_columns(tabla))


def indice_existe(tabla: str, nombre: str) -> bool:
    if not tabla_existe(tabla):
        return False
    return any(i["name"] == nombre for i in _inspector().get_indexes(tabla))


def crear_tabla_si_no_existe(nombre: str, *elementos, **kw) -> bool:
    """Crea la tabla si falta. Devuelve True si la creó."""
    if tabla_existe(nombre):
        return False
    op.create_table(nombre, *elementos, **kw)
    return True


def borrar_tabla_si_existe(nombre: str) -> None:
    if tabla_existe(nombre):
        op.drop_table(nombre)


def agregar_columna_si_no_existe(tabla: str, columna: sa.Column) -> bool:
    if columna_existe(tabla, columna.name):
        return False
    op.add_column(tabla, columna)
    return True


def borrar_columna_si_existe(tabla: str, columna: str) -> None:
    if columna_existe(tabla, columna):
        op.drop_column(tabla, columna)


def crear_indice_si_no_existe(nombre: str, tabla: str, columnas: list[str], **kw) -> bool:
    if indice_existe(tabla, nombre):
        return False
    op.create_index(nombre, tabla, columnas, **kw)
    return True


def borrar_indice_si_existe(nombre: str, tabla: str) -> None:
    if indice_existe(tabla, nombre):
        op.drop_index(nombre, table_name=tabla)
