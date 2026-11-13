"""Hash de contraseñas (argon2id)."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
LONGITUD_MINIMA = 10

# Hash de relleno: verificar contra él cuando el correo no existe iguala el
# tiempo de respuesta y no delata qué correos tienen cuenta.
HASH_DE_RELLENO = _hasher.hash("relleno-para-igualar-tiempos")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def validar_fortaleza(password: str) -> str | None:
    """Motivo del rechazo, o None si la contraseña sirve."""
    if len(password) < LONGITUD_MINIMA:
        return f"La contraseña tiene menos de {LONGITUD_MINIMA} caracteres. Agrégale unos cuantos."
    if password.isdigit():
        return "La contraseña es solo números. Mezcla letras."
    return None
