from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.comunes import Entrada, Numero, Salida

EstadoTrabajo = Literal["en_curso", "terminado", "interrumpido"]
GestionTrabajo = Literal["pendiente", "importado", "ignorado"]


class BandejaOut(Salida):
    id: str
    vacia: bool
    tipo: str | None = None
    color: str | None = None
    restante: int | None = None
    en_uso: bool = False


class DatosImpresoraOut(Salida):
    estado: str
    trabajo: str | None = None
    progreso: int | None = None
    capa: int | None = None
    capas: int | None = None
    restante_min: int | None = None
    boquilla: float | None = None
    boquilla_objetivo: float | None = None
    cama: float | None = None
    cama_objetivo: float | None = None
    boquilla_mm: str | None = None
    velocidad: int | None = None
    luz: Literal["on", "off"] | None = None
    wifi: str | None = None
    error: int = 0
    alertas: int = 0
    ams: list[BandejaOut] = []
    externa: BandejaOut | None = None


class NubeOut(Salida):
    """Sincronización con el historial de Bambu Cloud."""

    estado: Literal["sin_configurar", "ok", "requiere_login", "error"] | None = None
    sincronizada_en: datetime | None = None
    detalle: str | None = None


class ImpresoraOut(Salida):
    # El servicio escribe un latido cada pocos segundos: si falta, el servicio no está corriendo.
    servicio_activo: bool
    # Hay conexión con la impresora y está llegando información reciente.
    conectada: bool
    actualizado_en: datetime | None = None
    datos: DatosImpresoraOut | None = None
    trabajos_pendientes: int = 0
    nube: NubeOut = NubeOut()


class ComandoIn(Entrada):
    comando: Literal["pausar", "reanudar", "cancelar", "luz", "velocidad"]
    valor: str | None = Field(default=None, max_length=3)


class ComandoOut(Salida):
    id: int
    comando: str
    valor: str | None
    estado: str
    detalle: str | None


class FilamentoTrabajoOut(Salida):
    tipo: str
    color: str | None = None
    gramos: Numero


class TrabajoOut(Salida):
    id: UUID
    nombre: str
    estado: EstadoTrabajo
    gestion: GestionTrabajo
    inicio_en: datetime
    fin_en: datetime | None
    # Fecha local (zona del negocio) en que terminó (o empezó, si sigue en curso).
    fecha: date
    progreso: int
    # Tiempo para el lote: el MEDIDO (la impresora ocupada) si se vio el inicio; si no, el estimado
    # del archivo.
    minutos: int | None
    minutos_origen: Literal["medido", "estimado"] | None
    minutos_estimados: int | None
    # «impresora» = detectado en vivo; «nube» = del historial de Bambu Cloud.
    origen: Literal["impresora", "nube"] = "impresora"
    gramos_total: Numero | None
    filamentos: list[FilamentoTrabajoOut]
    produccion_id: UUID | None
