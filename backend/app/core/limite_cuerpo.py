"""Tope al tamaño del cuerpo de las peticiones, ANTES de que el framework lo lea.

FastAPI lee y guarda en disco un cuerpo multipart antes de resolver la autenticación; sin un tope
en este nivel, cualquiera podría hacer que el servidor gaste disco/tiempo en una subida que acabará
en 401. Aquí se rechaza por Content-Length y, si no viene (chunked), cortando al pasar el tope.
"""

import re

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings

TOPE_GENERAL = 256 * 1024  # JSON de la API: de sobra para un pedido o una venta
# Foto principal del artículo y foto de uno de sus colores: las dos son subidas de imagen.
RUTA_IMAGEN = re.compile(r"^/api/articulos/[0-9a-fA-F-]{36}(/colores/[0-9a-fA-F-]{36})?/imagen$")


class CuerpoDemasiadoGrande(Exception):
    pass


def tope_para(ruta: str, metodo: str) -> int:
    if metodo == "PUT" and RUTA_IMAGEN.match(ruta):
        return (settings.max_upload_mb + 1) * 1024 * 1024  # +1 MB de margen para el multipart
    return TOPE_GENERAL


class LimiteDeCuerpo:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return
        tope = tope_para(scope["path"], scope["method"])
        declarado = dict(scope["headers"]).get(b"content-length", b"")
        if declarado.isdigit() and int(declarado) > tope:
            await self._rechazar(send)
            return

        recibidos = 0
        excedido = False
        respondido = False

        async def contar() -> Message:
            nonlocal recibidos, excedido
            mensaje = await receive()
            if mensaje["type"] == "http.request":
                recibidos += len(mensaje.get("body", b""))
                if recibidos > tope:
                    excedido = True
                    raise CuerpoDemasiadoGrande
            return mensaje

        async def enviar(mensaje: Message) -> None:
            # FastAPI convierte cualquier error al leer el cuerpo en un 400: si fue por el tope,
            # se sustituye por el 413 correcto (y se ignora lo que la app intente enviar después).
            nonlocal respondido
            if excedido:
                if not respondido:
                    respondido = True
                    await self._rechazar(send)
                return
            await send(mensaje)

        try:
            await self.app(scope, contar, enviar)
        except CuerpoDemasiadoGrande:
            if not respondido:
                await self._rechazar(send)

    @staticmethod
    async def _rechazar(send: Send) -> None:
        cuerpo = b'{"detail":"El cuerpo de la petici\xc3\xb3n es demasiado grande."}'
        await send({"type": "http.response.start", "status": 413, "headers": [
            (b"content-type", b"application/json"), (b"content-length", str(len(cuerpo)).encode()),
            (b"connection", b"close"),
        ]})  # fmt: skip
        await send({"type": "http.response.body", "body": cuerpo})
