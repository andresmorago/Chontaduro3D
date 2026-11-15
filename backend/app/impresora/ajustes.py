"""Configuración de la impresora y de la cuenta de Bambu Cloud: validación y lectura/escritura en
la base (tabla `impresora_config`). La comparten el backend (panel) y el servicio `impresora`."""

import ipaddress
import json
import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import secretos
from app.impresora.nube import Sesion
from app.models import ConfigImpresora

# El número de serie va dentro del tema MQTT (`device/<serie>/report`): solo alfanuméricos, así
# no puede colar comodines (# +) ni barras.
_SERIE = re.compile(r"[A-Za-z0-9]{8,20}")
_CODIGO = re.compile(r"[\x21-\x7e]{4,32}")  # ASCII visible, sin espacios


def validar_ip(valor: str) -> str:
    """IP de la impresora. Debe ser de la red local o de una VPN (privada o compartida): el
    servicio abre conexiones hacia ella, y esto impide apuntarlo a internet o a sí mismo."""
    try:
        ip = ipaddress.ip_address(valor.strip())
    except ValueError:
        raise ValueError("Escribe la IP con números, p. ej. 192.168.1.50.") from None
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_global:
        raise ValueError("La IP debe ser de tu red local o VPN (p. ej. 192.168.x.x o 10.x.x.x).")
    return str(ip)


def validar_serial(valor: str) -> str:
    v = valor.strip().upper()
    if not _SERIE.fullmatch(v):
        raise ValueError("El número de serie lleva solo letras y números (8 a 20).")
    return v


def validar_codigo(valor: str) -> str:
    v = valor.strip()
    if not _CODIGO.fullmatch(v):
        raise ValueError("El código de acceso lleva de 4 a 32 caracteres, sin espacios.")
    return v


@dataclass(frozen=True)
class Conexion:
    """Lo que el servicio necesita para hablar con la impresora."""

    ip: str
    serial: str
    codigo: str
    version: int


async def obtener(db: AsyncSession) -> ConfigImpresora | None:
    return await db.get(ConfigImpresora, 1)


async def obtener_o_crear(db: AsyncSession) -> ConfigImpresora:
    fila = await db.get(ConfigImpresora, 1)
    if fila is None:
        fila = ConfigImpresora(id=1, version=1)
        db.add(fila)
        await db.flush()
    return fila


def conexion_de(fila: ConfigImpresora | None) -> Conexion | None:
    """None si falta algún dato o el código no se puede descifrar (SECRET_KEY distinta)."""
    if fila is None or not (fila.ip and fila.serial):
        return None
    codigo = secretos.descifrar(fila.codigo_acceso)
    if not codigo:
        return None
    return Conexion(fila.ip, fila.serial, codigo, fila.version)


def sesion_de(fila: ConfigImpresora | None) -> Sesion | None:
    crudo = secretos.descifrar(fila.nube_sesion) if fila else None
    if not crudo:
        return None
    try:
        d = json.loads(crudo)
        return Sesion(
            str(d["access_token"]),
            str(d.get("refresh_token") or ""),
            float(d.get("expira_en") or 0),
        )
    except (ValueError, KeyError, TypeError):
        return None


def poner_sesion(fila: ConfigImpresora, s: Sesion) -> None:
    fila.nube_sesion = secretos.cifrar(
        json.dumps(
            {
                "access_token": s.access_token,
                "refresh_token": s.refresh_token,
                "expira_en": s.expira_en,
            }  # fmt: skip
        )
    )
