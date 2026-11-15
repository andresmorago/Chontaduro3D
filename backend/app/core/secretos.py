"""Cifrado de los secretos guardados en la base (código de acceso de la impresora, token de Bambu).

Los respaldos de `data/respaldos` son volcados de la base: sin esto, quien los lea vería los
secretos en claro. La clave se deriva de SECRET_KEY, así que el backend y el servicio `impresora`
deben compartirla. Si SECRET_KEY cambia, lo cifrado deja de poder leerse (`descifrar` devuelve
None) y hay que volver a escribirlo desde Administración → Conexión."""

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import settings


def _fernet() -> Fernet:
    clave = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=b"misimpresiones/secretos/v1"
    ).derive(settings.secret_key.encode())
    return Fernet(base64.urlsafe_b64encode(clave))


def cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode()).decode()


def descifrar(cifrado: str | None) -> str | None:
    """El texto original, o None si no hay nada o no se puede leer (otra SECRET_KEY, dañado)."""
    if not cifrado:
        return None
    try:
        return _fernet().decrypt(cifrado.encode()).decode()
    except (InvalidToken, ValueError):
        return None
