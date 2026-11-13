from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, select, update

from app.config import settings
from app.core import auditoria
from app.core.cliente import origen_hash
from app.core.deps import COOKIE_ACCESO, COOKIE_REFRESCO, DB, Admin, exigir_cabecera_csrf
from app.core.security import HASH_DE_RELLENO, verify_password
from app.core.tokens import (
    ahora,
    crear_access_token,
    generar_token_opaco,
    hash_token,
    vencimiento_refresco,
)
from app.models import RegistroAuditoria, SesionRefresh, Usuario
from app.schemas.auth import LoginIn, UsuarioOut

router = APIRouter(prefix="/auth", tags=["auth"])

VENTANA = timedelta(minutes=15)
MAX_FALLOS_POR_ORIGEN = 10
MAX_FALLOS_POR_CORREO = 5


def _seguras(request: Request) -> bool:
    if settings.cookie_secure is not None:
        return settings.cookie_secure
    return (
        request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
        == "https"
    )


def _poner_cookies(response: Response, request: Request, access: str, refresh: str) -> None:
    comunes = {"httponly": True, "secure": _seguras(request), "samesite": "lax", "path": "/"}
    response.set_cookie(
        COOKIE_ACCESO, access, max_age=settings.access_token_minutes * 60, **comunes
    )
    response.set_cookie(
        COOKIE_REFRESCO, refresh, max_age=settings.refresh_token_days * 86400, **comunes
    )


def _borrar_cookies(response: Response) -> None:
    response.delete_cookie(COOKIE_ACCESO, path="/")
    response.delete_cookie(COOKIE_REFRESCO, path="/")


async def _abrir_sesion(db, response: Response, request: Request, usuario: Usuario) -> None:
    crudo, hasheado = generar_token_opaco()
    db.add(
        SesionRefresh(
            usuario_id=usuario.id,
            token_hash=hasheado,
            expira_en=vencimiento_refresco(),
            user_agent=(request.headers.get("user-agent") or "")[:255],
        )
    )
    _poner_cookies(response, request, crear_access_token(str(usuario.id)), crudo)


async def _fallos_recientes(db, **filtro) -> int:
    desde = ahora() - VENTANA
    consulta = (
        select(func.count())
        .select_from(RegistroAuditoria)
        .where(RegistroAuditoria.accion == "login_fallido", RegistroAuditoria.creado_en >= desde)
    )
    if "origen" in filtro:
        consulta = consulta.where(RegistroAuditoria.origen_hash == filtro["origen"])
    if "email" in filtro:
        consulta = consulta.where(RegistroAuditoria.detalle["email"].astext == filtro["email"])
    return (await db.execute(consulta)).scalar_one()


@router.post("/login", response_model=UsuarioOut, dependencies=[])
async def login(datos: LoginIn, request: Request, response: Response, db: DB) -> Usuario:
    exigir_cabecera_csrf(request)
    origen = origen_hash(request)
    email = datos.email.lower()

    if (
        await _fallos_recientes(db, origen=origen) >= MAX_FALLOS_POR_ORIGEN
        or await _fallos_recientes(db, email=email) >= MAX_FALLOS_POR_CORREO
    ):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Demasiados intentos. Espera unos minutos e inténtalo de nuevo.",
        )

    usuario = (await db.execute(select(Usuario).where(Usuario.email == email))).scalar_one_or_none()
    valido = verify_password(datos.password, usuario.password_hash if usuario else HASH_DE_RELLENO)
    if usuario is None or not usuario.activo or not valido:
        auditoria.registrar(db, "login_fallido", detalle={"email": email}, origen_hash=origen)
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Correo o contraseña incorrectos.")

    await _abrir_sesion(db, response, request, usuario)
    auditoria.registrar(db, "login", usuario_id=usuario.id, origen_hash=origen)
    await db.commit()
    return usuario


@router.post("/refresh", status_code=status.HTTP_204_NO_CONTENT, dependencies=[])
async def refrescar(request: Request, response: Response, db: DB) -> None:
    exigir_cabecera_csrf(request)
    crudo = request.cookies.get(COOKIE_REFRESCO)
    if not crudo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tu sesión venció. Entra de nuevo.")

    sesion = (
        await db.execute(
            select(SesionRefresh)
            .where(SesionRefresh.token_hash == hash_token(crudo))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if sesion is None:
        _borrar_cookies(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tu sesión venció. Entra de nuevo.")

    if sesion.revocada:
        # Un token ya usado reapareció: alguien lo copió. Se cierran todas las sesiones.
        await db.execute(
            update(SesionRefresh)
            .where(SesionRefresh.usuario_id == sesion.usuario_id)
            .values(revocada=True)
        )
        auditoria.registrar(db, "refresh_reutilizado", usuario_id=sesion.usuario_id)
        await db.commit()
        _borrar_cookies(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tu sesión venció. Entra de nuevo.")

    usuario = await db.get(Usuario, sesion.usuario_id)
    if sesion.expira_en <= ahora() or usuario is None or not usuario.activo:
        _borrar_cookies(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tu sesión venció. Entra de nuevo.")

    sesion.revocada = True
    await _abrir_sesion(db, response, request, usuario)
    await db.commit()


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[])
async def salir(request: Request, response: Response, db: DB) -> None:
    exigir_cabecera_csrf(request)
    crudo = request.cookies.get(COOKIE_REFRESCO)
    if crudo:
        await db.execute(
            update(SesionRefresh)
            .where(SesionRefresh.token_hash == hash_token(crudo))
            .values(revocada=True)
        )
        await db.commit()
    _borrar_cookies(response)


@router.get("/yo", response_model=UsuarioOut)
async def yo(usuario: Admin) -> Usuario:
    return usuario
