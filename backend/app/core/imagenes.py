"""Imágenes de artículos: validadas por contenido, re-codificadas, con nombre aleatorio."""

import io
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from app.config import settings

# HEIF = HEIC del iPhone: se lee aquí y se guarda como WebP (el navegador de escritorio no sabe
# mostrarlo). 2000 px de lado dejan hacer zoom en la interfaz sin que se vea borroso.
FORMATOS = {"JPEG", "PNG", "WEBP", "HEIF"}
LADO_MAXIMO = 2000
PIXELES_MAXIMOS = 40_000_000
NOMBRE_VALIDO = re.compile(r"^[0-9a-f]{32}\.webp$")

Image.MAX_IMAGE_PIXELS = PIXELES_MAXIMOS
register_heif_opener()


def carpeta() -> Path:
    ruta = Path(settings.media_dir)
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def ruta_de(nombre: str) -> Path | None:
    """Ruta de una imagen guardada, o None si el nombre no es uno nuestro."""
    if not NOMBRE_VALIDO.fullmatch(nombre):
        return None
    return carpeta() / nombre


def _invalida(detalle: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detalle)


async def guardar(archivo: UploadFile) -> str:
    limite = settings.max_upload_mb * 1024 * 1024
    datos = await archivo.read(limite + 1)
    if len(datos) > limite:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"La imagen pesa más de {settings.max_upload_mb} MB. Achícala e inténtalo de nuevo.",
        )
    return await run_in_threadpool(_procesar, datos)


def _procesar(datos: bytes) -> str:
    """Decodifica, normaliza y guarda. Corre en un hilo: Pillow es CPU pura."""
    try:
        with Image.open(io.BytesIO(datos)) as img:
            if img.format not in FORMATOS:
                raise _invalida("Solo se aceptan imágenes JPG, PNG, WEBP o HEIC.")
            ancho, alto = img.size
            # Pillow solo avisa (no falla) entre 1× y 2× el tope: se corta ANTES de decodificar.
            if ancho * alto > PIXELES_MAXIMOS:
                raise _invalida(
                    "La imagen tiene demasiados píxeles. Reduce su tamaño e inténtalo de nuevo."
                )
            img.load()
            img = ImageOps.exif_transpose(img)  # respeta la orientación y descarta EXIF
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            img.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
            nombre = f"{uuid.uuid4().hex}.webp"
            img.save(carpeta() / nombre, "WEBP", quality=82, method=4)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        raise _invalida(
            "No pude leer ese archivo como imagen. Prueba con otro JPG, PNG, WEBP o HEIC."
        ) from None
    return nombre


def borrar(nombre: str | None) -> None:
    if not nombre:
        return
    ruta = ruta_de(nombre)
    if ruta is not None:
        ruta.unlink(missing_ok=True)
