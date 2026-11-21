"""Hash de contraseñas (argon2id)."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
LONGITUD_MINIMA = 10

# Contraseñas muy comunes (en minúsculas; se compara sin distinguir mayúsculas). Las de menos de
# LONGITUD_MINIMA ya caen por largo, pero se dejan por si la longitud mínima baja algún día.
COMUNES = frozenset(
    """
    password password1 password12 password123 password1234 password12345 passw0rd p@ssw0rd p@ssword
    contrasena contrasena1 contrasena12 contrasena123 contrasena1234 clave123456 micontrasena
    1234567890 12345678910 123456789a 1q2w3e4r5t 1qaz2wsx3edc 123qweasdzxc
    qwertyuiop qwertyuiop1 qwerty123 qwerty1234 qwerty12345 qwertyui123 qwerty123456 qazwsxedc
    asdfghjkl asdfghjkl1 asdfghjkl123 zxcvbnm123 zxcvbnmasdf iloveyou1 iloveyou12 iloveyou123
    tequiero123 teamo12345 teamo123456 abcdefghij abcd123456 abc1234567 abcdefg123 a1b2c3d4e5
    letmein123 welcome123 welcome1234 admin12345 admin123456 administrador administrator1
    administrator123 changeme123 changeme1234 superman123 batman12345 football123 baseball123
    princess123 sunshine123 dragon12345 monkey12345 master12345 shadow12345 trustno123
    colombia123 colombia1234 colombia2024 colombia2025 bogota12345 medellin123 cali1234567
    misimpresiones impresiones123 impresion3d 3dprinter123 bambulab123
    1111111111 0000000000 1234512345 0123456789 9876543210 1234567891 1122334455 1212121212
    123456789012 12345678901 111111111111 123123123123 654321654321 11223344556 1234554321
    """.split()
)

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


def validar_fortaleza(password: str, email: str | None = None) -> str | None:
    """Motivo del rechazo, o None si la contraseña sirve."""
    if len(password) < LONGITUD_MINIMA:
        return f"La contraseña tiene menos de {LONGITUD_MINIMA} caracteres. Agrégale unos cuantos."
    if password.isdigit():
        return "La contraseña es solo números. Mezcla letras."
    if password.lower() in COMUNES:
        return "Esa contraseña es de las más usadas y se adivina enseguida. Elige otra."
    if email:
        correo = email.strip().lower()
        if password.strip().lower() in (correo, correo.split("@")[0]):
            return "La contraseña no puede ser igual al correo. Elige otra."
    return None
