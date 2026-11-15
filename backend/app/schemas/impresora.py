from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator

from app.impresora.ajustes import validar_codigo, validar_ip, validar_serial
from app.schemas.comunes import Entrada, Numero, Salida

EstadoTrabajo = Literal["en_curso", "terminado", "interrumpido"]
GestionTrabajo = Literal["pendiente", "importado", "ignorado"]


class BandejaOut(Salida):
    id: str
    vacia: bool
    tipo: str | None = None
    marca: str | None = None
    color: str | None = None
    # True = bobina con chip RFID: el «restante» es una medición real; si no, no se sabe.
    medido: bool = False
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
    ventilador_pieza: int | None = None
    ventilador_aux: int | None = None
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
    comando: Literal[
        "pausar", "reanudar", "cancelar", "luz", "velocidad",
        "temp_boquilla", "temp_cama", "ventilador_pieza", "ventilador_aux",
    ]  # fmt: skip
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


# ------------------------------------------------------------ conexión (Administración → Conexión)
class NubeConexionOut(Salida):
    vinculada: bool
    correo: str | None = None
    estado: Literal["sin_configurar", "ok", "requiere_login", "error"] | None = None
    sincronizada_en: datetime | None = None
    detalle: str | None = None
    # Se pidió sincronizar y el servicio aún no lo atendió.
    pendiente: bool = False


class ConexionOut(Salida):
    """Lo guardado y cómo va. El código de acceso y el token NUNCA salen por aquí."""

    ip: str | None = None
    serial: str | None = None
    codigo_guardado: bool = False
    # Hay datos guardados pero no se pueden leer (cambió SECRET_KEY): hay que escribirlos de nuevo.
    ilegible: bool = False
    servicio_activo: bool = False
    conectada: bool = False
    # Se guardó un cambio y el servicio aún no reconectó con él.
    pendiente: bool = False
    # Si no conecta: «credenciales» (código de acceso rechazado) o «red» (no se alcanza la IP).
    error: Literal["credenciales", "red"] | None = None
    nube: NubeConexionOut = NubeConexionOut(vinculada=False)


class ConexionIn(Entrada):
    ip: str = Field(min_length=7, max_length=45)
    serial: str = Field(min_length=8, max_length=20)
    # Vacío = conservar el que ya está guardado.
    codigo_acceso: str | None = Field(default=None, max_length=32)

    @field_validator("ip")
    @classmethod
    def _ip(cls, v: str) -> str:
        return validar_ip(v)

    @field_validator("serial")
    @classmethod
    def _serial(cls, v: str) -> str:
        return validar_serial(v)

    @field_validator("codigo_acceso")
    @classmethod
    def _codigo(cls, v: str | None) -> str | None:
        return validar_codigo(v) if v else None


class NubeEntrarIn(Entrada):
    # Bambu acepta correo o teléfono como cuenta.
    correo: str = Field(min_length=3, max_length=254)
    clave: str = Field(min_length=1, max_length=200)
    # La contraseña no se repite en los mensajes de validación.
    model_config = ConfigDict(hide_input_in_errors=True)


class NubeVerificarIn(Entrada):
    codigo: str = Field(min_length=4, max_length=12)
    # Verificación por correo: el correo. Por app de autenticación (2FA): la llave que dio Bambu.
    correo: str | None = Field(default=None, min_length=3, max_length=254)
    tfa_key: str | None = Field(default=None, min_length=4, max_length=200)


class NubeTokenIn(Entrada):
    token: str = Field(min_length=20, max_length=4096)
    model_config = ConfigDict(hide_input_in_errors=True)


class NubePasoOut(Salida):
    paso: Literal["listo", "codigo", "tfa"]
    tfa_key: str | None = None
