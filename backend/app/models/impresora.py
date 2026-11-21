import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import MarcaDeTiempo, uuid_pk

ESTADOS_TRABAJO = ("en_curso", "terminado", "interrumpido")
GESTION_TRABAJO = ("pendiente", "importado", "ignorado")
COMANDOS = (
    "pausar", "reanudar", "cancelar", "luz", "velocidad",
    "temp_boquilla", "temp_cama", "ventilador_pieza", "ventilador_aux",
)  # fmt: skip
ESTADOS_COMANDO = ("pendiente", "enviado", "fallido", "vencido")


def _en(columna: str, valores: tuple[str, ...]) -> str:
    return f"{columna} IN ({', '.join(repr(v) for v in valores)})"


class TrabajoImpresora(MarcaDeTiempo, Base):
    """Un trabajo de la impresora 3D, detectado por el servicio `impresora`.

    Los gramos y el tiempo estimado salen del archivo .3mf (lo que calculó el slicer); el tiempo
    medido es lo que la impresora estuvo ocupada, si se vio el inicio. No todo trabajo es una
    producción: la persona elige cuáles importar (`gestion`)."""

    __tablename__ = "trabajos_impresora"
    __table_args__ = (
        CheckConstraint(_en("estado", ESTADOS_TRABAJO), name="estado_valido"),
        CheckConstraint(_en("gestion", GESTION_TRABAJO), name="gestion_valida"),
        Index("ix_trabajos_impresora_gestion_fin", "gestion", "fin_en"),
        Index(
            "uq_trabajos_impresora_nube_id", "nube_id", unique=True,
            postgresql_where=text("nube_id IS NOT NULL"),
        ),
    )  # fmt: skip

    id: Mapped[uuid.UUID] = uuid_pk()
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    archivo: Mapped[str | None] = mapped_column(String(300))
    # Identificador que la impresora da al trabajo (task_id); "" / "0" si no lo trae.
    tarea_id: Mapped[str] = mapped_column(String(40), server_default="", nullable=False)
    estado: Mapped[str] = mapped_column(String(12), server_default="en_curso", nullable=False)
    gestion: Mapped[str] = mapped_column(String(10), server_default="pendiente", nullable=False)
    inicio_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # False = el servicio arrancó con el trabajo a medias: «inicio_en» es cuando se vio, no el real.
    inicio_observado: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), nullable=False
    )
    fin_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    progreso: Mapped[int] = mapped_column(SmallInteger, server_default="0", nullable=False)
    plate: Mapped[int | None] = mapped_column(SmallInteger)
    minutos_estimados: Mapped[int | None] = mapped_column(Integer)
    gramos_total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    # [{"tipo": "PLA", "color": "#ffb673", "gramos": 0.88}, …]
    filamentos: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    # Bandejas del AMS en las que estuvo la impresora durante el trabajo, en orden:
    # [{"ranura": "2", "tipo": "PLA", "color": "#f7e6de", "tag": "0E45…" | null}, …]. Con esto (y
    # los filamentos del .3mf) se sabe de qué bobina descontar; el .3mf no dice en qué bandeja iba.
    bandejas: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    produccion_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("producciones.id", ondelete="SET NULL"), unique=True
    )
    # De dónde salió: «impresora» (detectado en vivo) o «nube» (historial de Bambu Cloud).
    origen: Mapped[str] = mapped_column(String(10), server_default="impresora", nullable=False)
    # Identificador del trabajo en Bambu Cloud (une el historial con lo detectado en vivo).
    nube_id: Mapped[str | None] = mapped_column(String(40))
    # Tiempo de impresión que informa Bambu Cloud (segundos → minutos): es el MEDIDO por la
    # impresora, mejor que la estimación del archivo.
    minutos_medidos: Mapped[int | None] = mapped_column(Integer)


class EstadoImpresora(Base):
    """Última foto del estado de la impresora (una fila). La escribe el servicio `impresora`."""

    __tablename__ = "impresora_estado"
    __table_args__ = (CheckConstraint("id = 1", name="fila_unica"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1, server_default="1")
    conectada: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)
    ultimo_mensaje_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Latido del servicio: si se queda viejo, el servicio no está corriendo.
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    datos: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Sincronización con el historial de Bambu Cloud: sin_configurar | ok | requiere_login | error.
    nube_estado: Mapped[str | None] = mapped_column(String(20))
    nube_sincronizada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    nube_detalle: Mapped[str | None] = mapped_column(String(200))
    # Última vez que el servicio terminó un intento con la nube (bien o mal): sirve para saber si
    # una sincronización pedida desde el panel ya fue atendida.
    nube_atendida_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Versión de `ConfigImpresora` que el servicio ya aplicó (conectó con esos datos).
    config_version: Mapped[int | None] = mapped_column(Integer)
    # Por qué no conecta: «credenciales» (código de acceso rechazado) o «red» (no se alcanza).
    conexion_error: Mapped[str | None] = mapped_column(String(20))


class ComandoImpresora(Base):
    """Orden para la impresora. El backend la deja aquí y el servicio la envía (así el backend
    no necesita las credenciales de la impresora). Una orden vieja no se ejecuta."""

    __tablename__ = "impresora_comandos"
    __table_args__ = (
        CheckConstraint(_en("comando", COMANDOS), name="comando_valido"),
        CheckConstraint(_en("estado", ESTADOS_COMANDO), name="estado_valido"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    comando: Mapped[str] = mapped_column(String(20), nullable=False)
    valor: Mapped[str | None] = mapped_column(String(12))
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    estado: Mapped[str] = mapped_column(String(10), server_default="pendiente", nullable=False)
    detalle: Mapped[str | None] = mapped_column(String(200))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    atendido_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConfigImpresora(Base):
    """Cómo conectar con la impresora y con la cuenta de Bambu Cloud (una fila). La escribe el
    panel (Administración → Conexión) y la lee el servicio `impresora`, que reconecta solo cuando
    cambia. Los secretos van cifrados (app/core/secretos.py); nunca se devuelven por la API."""

    __tablename__ = "impresora_config"
    __table_args__ = (CheckConstraint("id = 1", name="fila_unica"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1, server_default="1")
    ip: Mapped[str | None] = mapped_column(String(45))
    serial: Mapped[str | None] = mapped_column(String(32))
    codigo_acceso: Mapped[str | None] = mapped_column(Text)  # cifrado
    # Sube con cada cambio de ip/serial/código: el servicio reconecta y avisa que ya lo aplicó.
    version: Mapped[int] = mapped_column(Integer, server_default="1", nullable=False)
    # Bambu Cloud: JSON {access_token, refresh_token, expira_en}, cifrado.
    # La contraseña NO se guarda.
    nube_sesion: Mapped[str | None] = mapped_column(Text)
    nube_correo: Mapped[str | None] = mapped_column(String(254))
    # El panel la actualiza para pedir «sincronizar ya»; el servicio la compara con
    # `nube_atendida_en`.
    nube_solicitada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
