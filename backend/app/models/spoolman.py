import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import uuid_pk

# Ciclo de un descuento: sin_bobina (falta elegir de cuál) → por_enviar → enviando → descontado.
# «revisar»: se cortó entre enviar y confirmar; no se sabe si Spoolman lo aplicó (lo decide la
# persona).
ESTADOS_CONSUMO = ("sin_bobina", "por_enviar", "enviando", "descontado", "omitido", "revisar")


class EstadoSpoolman(Base):
    """Cómo va la conexión con Spoolman (una fila). La escribe el servicio `impresora`."""

    __tablename__ = "spoolman_estado"
    __table_args__ = (CheckConstraint("id = 1", name="fila_unica"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1, server_default="1")
    # La primera vez que se alcanzó Spoolman: solo los trabajos que terminan DESPUÉS descuentan
    # filamento (lo impreso antes no se descuenta con retraso, ni dos veces).
    desde: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    conectado: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)
    version: Mapped[str | None] = mapped_column(String(20))
    ultimo_ok_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detalle: Mapped[str | None] = mapped_column(String(200))
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RanuraBobina(Base):
    """Bobina puesta en una ranura del AMS que NO tiene chip RFID (las Bambu con chip se
    reconocen solas: su UID queda vinculado dentro de Spoolman). Guarda el tipo y el color que
    mostraba la ranura al vincular: si cambian, la bobina ya no es la misma y se pide confirmar."""

    __tablename__ = "ranura_bobinas"

    ranura: Mapped[str] = mapped_column(String(4), primary_key=True)  # «0»–«3», «254» = externa
    spool_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[str | None] = mapped_column(String(20))
    color: Mapped[str | None] = mapped_column(String(7))
    vinculada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChipBobina(Base):
    """Chip RFID que el servicio ya leyó alguna vez en el AMS (o que ya estaba vinculado a una
    bobina de Spoolman). Es la memoria que evita registrar de nuevo un chip conocido aunque su
    bobina se haya borrado en Spoolman: quitar el rollo y volver a ponerlo no crea duplicados."""

    __tablename__ = "chips_bobina"

    uid: Mapped[str] = mapped_column(String(32), primary_key=True)  # mayúsculas, sin separadores
    spool_id: Mapped[int | None] = mapped_column(Integer)  # la bobina que tuvo (si se sabe)
    visto_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ConsumoFilamento(Base):
    """Filamento que gastó un trabajo de la impresora y su descuento en Spoolman. Es por TRABAJO,
    no por lote de producción: todo lo que se imprime descuenta, se importe o no como producción."""

    __tablename__ = "consumos_filamento"
    __table_args__ = (
        UniqueConstraint("trabajo_id", "orden", name="uq_consumos_filamento_trabajo_orden"),
        CheckConstraint(
            "estado IN (" + ", ".join(repr(e) for e in ESTADOS_CONSUMO) + ")",
            name="estado_valido",
        ),
        CheckConstraint("gramos >= 0", name="gramos_no_negativos"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    trabajo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trabajos_impresora.id", ondelete="CASCADE"), index=True
    )
    orden: Mapped[int] = mapped_column(SmallInteger, server_default="0", nullable=False)
    tipo: Mapped[str | None] = mapped_column(String(20))
    color: Mapped[str | None] = mapped_column(String(7))
    # Lo que dice el archivo del trabajo, y lo que de verdad se descuenta (un trabajo cortado
    # descuenta solo la parte hecha; la persona puede ajustarlo antes de enviar).
    gramos_plan: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    gramos: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    ranura: Mapped[str | None] = mapped_column(String(4))
    spool_id: Mapped[int | None] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(12), server_default="sin_bobina", nullable=False)
    detalle: Mapped[str | None] = mapped_column(String(200))
    intentos: Mapped[int] = mapped_column(SmallInteger, server_default="0", nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    descontado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
