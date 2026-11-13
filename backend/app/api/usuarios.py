"""Administración de usuarios: alta, edición, activar/desactivar y contraseñas.

Sin roles por ahora: toda persona con sesión puede administrar a las demás (el negocio es chico).
Cada cambio que debe cortar el acceso (cambio de contraseña, desactivación) sube `version_sesion`
—los JWT de acceso ya emitidos dejan de valer— y revoca los tokens de refresco.
"""

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select, update

from app.api.auth import _abrir_sesion
from app.core import auditoria
from app.core.deps import DB, PROTEGIDO, Admin
from app.core.security import hash_password, validar_fortaleza, verify_password
from app.core.tokens import ahora
from app.models import RegistroAuditoria, SesionRefresh, Usuario
from app.schemas.usuarios import (
    CambiarContrasena,
    RestablecerContrasena,
    UsuarioAdminOut,
    UsuarioCambios,
    UsuarioNuevo,
)

router = APIRouter(prefix="/usuarios", tags=["usuarios"], dependencies=PROTEGIDO)

MAX_FALLOS_CLAVE = 5
VENTANA = timedelta(minutes=15)


def _salida(u: Usuario, yo: Usuario) -> UsuarioAdminOut:
    return UsuarioAdminOut(
        id=u.id, email=u.email, nombre=u.nombre, activo=u.activo, creado_en=u.creado_en,
        es_yo=u.id == yo.id,
    )  # fmt: skip


def _exigir_fortaleza(clave: str, email: str) -> None:
    motivo = validar_fortaleza(clave)
    if motivo is None and clave.strip().lower() in (email.lower(), email.split("@")[0].lower()):
        motivo = "La contraseña no puede ser igual al correo. Elige otra."
    if motivo:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, motivo)


async def _cortar_sesiones(db, usuario: Usuario) -> None:
    """Invalida los JWT de acceso (versión) y los refrescos (revocados) de un usuario."""
    usuario.version_sesion += 1
    await db.execute(
        update(SesionRefresh).where(SesionRefresh.usuario_id == usuario.id).values(revocada=True)
    )


async def _obtener(db, usuario_id: UUID) -> Usuario:
    u = await db.get(Usuario, usuario_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese usuario no existe.")
    return u


@router.get("", response_model=list[UsuarioAdminOut])
async def listar(db: DB, yo: Admin) -> list[UsuarioAdminOut]:
    filas = (await db.execute(select(Usuario).order_by(Usuario.creado_en))).scalars().all()
    return [_salida(u, yo) for u in filas]


@router.post("", response_model=UsuarioAdminOut, status_code=status.HTTP_201_CREATED)
async def crear(datos: UsuarioNuevo, db: DB, yo: Admin) -> UsuarioAdminOut:
    email = datos.email.lower()
    _exigir_fortaleza(datos.password, email)
    existe = (await db.execute(select(Usuario.id).where(Usuario.email == email))).first()
    if existe:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya hay un usuario con ese correo.")
    nuevo = Usuario(
        email=email,
        nombre=datos.nombre.strip(),
        password_hash=await run_in_threadpool(hash_password, datos.password),
    )
    db.add(nuevo)
    auditoria.registrar(db, "usuario_creado", usuario_id=yo.id, detalle={"email": email})
    await db.commit()
    await db.refresh(nuevo)
    return _salida(nuevo, yo)


@router.post("/yo/contrasena", status_code=status.HTTP_204_NO_CONTENT)
async def cambiar_la_mia(
    datos: CambiarContrasena, request: Request, response: Response, db: DB, yo: Admin
) -> None:
    """Cambia TU contraseña: pide la actual, cierra tus otras sesiones y conserva esta."""
    fallos = (
        await db.execute(
            select(func.count()).select_from(RegistroAuditoria).where(
                RegistroAuditoria.accion == "cambio_clave_fallido",
                RegistroAuditoria.usuario_id == yo.id,
                RegistroAuditoria.creado_en >= ahora() - VENTANA,
            )
        )
    ).scalar_one()  # fmt: skip
    if fallos >= MAX_FALLOS_CLAVE:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Demasiados intentos. Espera unos minutos."
        )
    if not await run_in_threadpool(verify_password, datos.actual, yo.password_hash):
        auditoria.registrar(db, "cambio_clave_fallido", usuario_id=yo.id)
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La contraseña actual no es correcta.")
    if datos.nueva == datos.actual:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "La contraseña nueva debe ser distinta de la actual.",
        )
    _exigir_fortaleza(datos.nueva, yo.email)
    yo.password_hash = await run_in_threadpool(hash_password, datos.nueva)
    await _cortar_sesiones(db, yo)
    auditoria.registrar(db, "contrasena_cambiada", usuario_id=yo.id)
    # Se sigue dentro en ESTE equipo: sesión nueva con la versión nueva; el resto queda cerrado.
    await _abrir_sesion(db, response, request, yo)
    await db.commit()


@router.patch("/{usuario_id}", response_model=UsuarioAdminOut)
async def actualizar(usuario_id: UUID, datos: UsuarioCambios, db: DB, yo: Admin) -> UsuarioAdminOut:
    u = await _obtener(db, usuario_id)
    if datos.nombre is not None:
        u.nombre = datos.nombre.strip()
    if datos.activo is not None and datos.activo != u.activo:
        if not datos.activo:
            if u.id == yo.id:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "No puedes desactivar tu propio usuario."
                )
            activos = (
                await db.execute(select(func.count()).select_from(Usuario).where(Usuario.activo))
            ).scalar_one()
            if activos <= 1:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "Debe quedar al menos un usuario activo."
                )
            await _cortar_sesiones(db, u)  # se queda fuera ya, no a los 15 minutos
        u.activo = datos.activo
        auditoria.registrar(
            db, "usuario_activado" if datos.activo else "usuario_desactivado",
            usuario_id=yo.id, detalle={"email": u.email},
        )  # fmt: skip
    await db.commit()
    return _salida(u, yo)


@router.post("/{usuario_id}/contrasena", status_code=status.HTTP_204_NO_CONTENT)
async def restablecer(usuario_id: UUID, datos: RestablecerContrasena, db: DB, yo: Admin) -> None:
    """Pone una contraseña nueva a OTRA persona y cierra todas sus sesiones."""
    u = await _obtener(db, usuario_id)
    if u.id == yo.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Para tu propia contraseña usa «Cambiar mi contraseña»."
        )
    _exigir_fortaleza(datos.nueva, u.email)
    u.password_hash = await run_in_threadpool(hash_password, datos.nueva)
    await _cortar_sesiones(db, u)
    auditoria.registrar(db, "contrasena_restablecida", usuario_id=yo.id, detalle={"email": u.email})
    await db.commit()
