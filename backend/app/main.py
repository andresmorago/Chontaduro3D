"""Aplicación FastAPI. Todo cuelga de /api: el frontend la expone en el mismo origen."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import (
    articulos,
    auth,
    inventario,
    media,
    panel,
    parametros,
    pedidos,
    produccion,
    publico,
    usuarios,
    ventas,
)
from app.config import settings
from app.core.limite_cuerpo import LimiteDeCuerpo
from app.db import engine

CABECERAS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


@asynccontextmanager
async def ciclo(_: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title="Mis impresiones",
    lifespan=ciclo,
    # La documentación interactiva solo en desarrollo.
    docs_url=None if settings.es_produccion else "/api/docs",
    redoc_url=None,
    openapi_url=None if settings.es_produccion else "/api/openapi.json",
)


app.add_middleware(LimiteDeCuerpo)


@app.middleware("http")
async def cabeceras_de_seguridad(request: Request, call_next):
    respuesta = await call_next(request)
    for k, v in CABECERAS.items():
        respuesta.headers.setdefault(k, v)
    # Nada de la API se guarda en caché salvo las imágenes (que fijan la suya).
    respuesta.headers.setdefault("Cache-Control", "no-store")
    return respuesta


for r in (
    auth,
    articulos,
    produccion,
    parametros,
    usuarios,
    ventas,
    inventario,
    pedidos,
    panel,
    publico,
    media,
):
    app.include_router(r.router, prefix="/api")


@app.get("/health", include_in_schema=False)
async def health() -> JSONResponse:
    async with engine.connect() as conexion:
        await conexion.execute(text("SELECT 1"))
    return JSONResponse({"ok": True})
