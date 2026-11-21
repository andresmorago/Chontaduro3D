"""Cuándo empieza y cuándo termina un trabajo, a partir de la secuencia de estados de la A1.

Lógica pura (sin red ni base de datos): `decidir` recibe lo que informa la impresora y el trabajo
abierto que ya hay en la base, y dice qué hacer."""

from dataclasses import dataclass

from app.impresora.bambu import ACTIVOS
from app.impresora.topes import acotar_progreso


@dataclass(frozen=True)
class Instantanea:
    gcode_state: str | None
    nombre: str
    archivo: str
    tarea_id: str
    progreso: int


@dataclass(frozen=True)
class Abierto:
    """El trabajo que está `en_curso` en la base."""

    nombre: str
    archivo: str
    tarea_id: str


@dataclass(frozen=True)
class Accion:
    cerrar: str | None = None  # «terminado» | «interrumpido»
    abrir: bool = False
    actualizar_progreso: bool = False


NADA = Accion()


def instantanea_de(crudo: dict) -> Instantanea:
    return Instantanea(
        gcode_state=crudo.get("gcode_state"),
        nombre=str(crudo.get("subtask_name") or ""),
        archivo=str(crudo.get("gcode_file") or ""),
        tarea_id=str(crudo.get("task_id") or ""),
        progreso=acotar_progreso(crudo.get("mc_percent")),
    )


def _con_id(t: str) -> bool:
    return t not in ("", "0")


def _misma(s: Instantanea, a: Abierto) -> bool:
    """Mismo trabajo: por el identificador de la impresora si lo trae; si no, por el nombre (el
    nombre del archivo puede llegar un instante después, durante la preparación)."""
    if _con_id(s.tarea_id) and _con_id(a.tarea_id):
        return s.tarea_id == a.tarea_id
    return s.nombre == a.nombre


def decidir(s: Instantanea, abierto: Abierto | None) -> list[Accion]:
    """Acciones, en orden. Un trabajo se abre al ver la impresora preparando/imprimiendo; se cierra
    «terminado» con FINISH y «interrumpido» con FAILED/IDLE (cancelado o fallido) o si arranca otro
    trabajo sin que se haya visto el final del anterior."""
    estado = s.gcode_state
    if estado is None:
        return []
    activo = estado in ACTIVOS
    if abierto is None:
        return [Accion(abrir=True)] if activo and s.nombre else []
    if activo:
        if _misma(s, abierto):
            return [Accion(actualizar_progreso=True)]
        return (
            [Accion(cerrar="interrumpido"), Accion(abrir=True)]
            if s.nombre
            else [Accion(cerrar="interrumpido")]
        )
    if estado == "FINISH" and _misma(s, abierto):
        return [Accion(cerrar="terminado")]
    return [Accion(cerrar="interrumpido")]
