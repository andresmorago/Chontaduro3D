"""Administración → Conexión: configurar la impresora (IP, serial, código de acceso) y vincular la
cuenta de Bambu Cloud desde el panel, sin `.env` ni scripts.

El backend solo guarda los datos (cifrados) y el servicio `impresora` los toma de la base y
reconecta. La API nunca devuelve el código de acceso ni el token."""

from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.core import auditoria, secretos
from app.core.deps import DB, PROTEGIDO, Admin
from app.core.tokens import ahora
from app.impresora import ajustes, nube_login
from app.models import ConfigImpresora, EstadoImpresora
from app.schemas.impresora import (
    ConexionIn,
    ConexionOut,
    NubeConexionOut,
    NubeEntrarIn,
    NubePasoOut,
    NubeTokenIn,
    NubeVerificarIn,
)

router = APIRouter(prefix="/impresora/conexion", tags=["impresora"], dependencies=PROTEGIDO)

LATIDO_MAX_S = 40  # igual que en api/impresora.py: el servicio escribe cada ~10 s


def login_nube() -> nube_login.LoginNube:
    """Punto único de salida hacia Bambu Cloud (las pruebas lo sustituyen)."""
    return nube_login.LoginNube(settings.bambu_nube_url)


def _vivo(estado: EstadoImpresora | None) -> bool:
    return estado is not None and (ahora() - estado.actualizado_en).total_seconds() < LATIDO_MAX_S


def _salida(cfg: ConfigImpresora | None, estado: EstadoImpresora | None) -> ConexionOut:
    vivo = _vivo(estado)
    completa = ajustes.conexion_de(cfg) is not None
    sesion = ajustes.sesion_de(cfg)
    solicitada = cfg.nube_solicitada_en if cfg else None
    atendida = estado.nube_atendida_en if estado else None
    conectada = bool(vivo and estado and estado.conectada)
    return ConexionOut(
        ip=cfg.ip if cfg else None,
        serial=cfg.serial if cfg else None,
        codigo_guardado=bool(cfg and cfg.codigo_acceso),
        ilegible=bool(cfg and cfg.codigo_acceso and not completa and cfg.ip and cfg.serial),
        servicio_activo=vivo,
        conectada=conectada,
        pendiente=bool(
            completa and (estado is None or estado.config_version != (cfg.version if cfg else None))
        ),
        error=estado.conexion_error if estado and not conectada else None,
        nube=NubeConexionOut(
            vinculada=sesion is not None,
            correo=cfg.nube_correo if cfg and sesion else None,
            estado=estado.nube_estado if estado else None,
            sincronizada_en=estado.nube_sincronizada_en if estado else None,
            detalle=estado.nube_detalle if estado else None,
            pendiente=bool(sesion and solicitada and (atendida is None or atendida < solicitada)),
        ),
    )


async def _vista(db: DB) -> ConexionOut:
    cfg = await ajustes.obtener(db)
    estado = await db.get(EstadoImpresora, 1)
    return _salida(cfg, estado)


@router.get("", response_model=ConexionOut)
async def ver(db: DB) -> ConexionOut:
    return await _vista(db)


# ------------------------------------------------------------------------ impresora
@router.put("", response_model=ConexionOut)
async def guardar(datos: ConexionIn, db: DB, usuario: Admin) -> ConexionOut:
    """Guarda IP, serial y código de acceso. El servicio reconecta solo con lo nuevo."""
    cfg = await ajustes.obtener_o_crear(db)
    if datos.codigo_acceso:
        cfg.codigo_acceso = secretos.cifrar(datos.codigo_acceso)
    elif not cfg.codigo_acceso or ajustes.conexion_de(cfg) is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Escribe el código de acceso de la impresora."
        )
    cfg.ip, cfg.serial = datos.ip, datos.serial
    cfg.version += 1
    cfg.actualizado_en = ahora()
    auditoria.registrar(
        db, "impresora_conexion", usuario_id=usuario.id,
        detalle={"ip": datos.ip, "serial": datos.serial},
    )  # fmt: skip
    await db.commit()
    return await _vista(db)


# ---------------------------------------------------------------------- Bambu Cloud
async def _vincular(db: DB, usuario: Admin, sesion, correo: str | None, como: str) -> NubePasoOut:
    cfg = await ajustes.obtener_o_crear(db)
    ajustes.poner_sesion(cfg, sesion)
    cfg.nube_correo = correo
    cfg.nube_solicitada_en = ahora()  # el servicio sincroniza de inmediato
    cfg.actualizado_en = ahora()
    auditoria.registrar(db, "nube_vinculada", usuario_id=usuario.id, detalle={"como": como})
    await db.commit()
    return NubePasoOut(paso="listo")


@router.post("/nube/entrar", response_model=NubePasoOut)
async def nube_entrar(datos: NubeEntrarIn, db: DB, usuario: Admin) -> NubePasoOut:
    """Primer paso: correo y contraseña. Bambu puede pedir un código (por correo o por 2FA)."""
    try:
        r = await login_nube().entrar(datos.correo, datos.clave)
    except nube_login.ErrorLogin as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None
    if r.paso == "listo" and r.sesion is not None:
        return await _vincular(db, usuario, r.sesion, datos.correo, "clave")
    return NubePasoOut(paso=r.paso, tfa_key=r.tfa_key)  # type: ignore[arg-type]


@router.post("/nube/verificar", response_model=NubePasoOut)
async def nube_verificar(datos: NubeVerificarIn, db: DB, usuario: Admin) -> NubePasoOut:
    """Segundo paso: el código que Bambu mandó al correo, o el de la app de autenticación."""
    if bool(datos.tfa_key) == bool(datos.correo):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Falta el correo o la llave de verificación."
        )
    try:
        nube = login_nube()
        r = (
            await nube.verificar_tfa(datos.tfa_key, datos.codigo)
            if datos.tfa_key
            else await nube.verificar_codigo(datos.correo or "", datos.codigo)
        )
    except nube_login.ErrorLogin as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None
    assert r.sesion is not None
    return await _vincular(db, usuario, r.sesion, datos.correo, "codigo")


@router.post("/nube/token", response_model=NubePasoOut)
async def nube_token(datos: NubeTokenIn, db: DB, usuario: Admin) -> NubePasoOut:
    """Si Bambu bloquea el inicio de sesión: pegar el token de la cookie de bambulab.com."""
    try:
        sesion = nube_login.desde_token(datos.token)
    except nube_login.ErrorLogin as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    return await _vincular(db, usuario, sesion, None, "token")


@router.post("/nube/sincronizar", response_model=ConexionOut, status_code=status.HTTP_202_ACCEPTED)
async def nube_sincronizar(db: DB, usuario: Admin) -> ConexionOut:
    """Pide al servicio que traiga ya el historial (si no, lo hace cada 10 minutos)."""
    cfg = await ajustes.obtener(db)
    if ajustes.sesion_de(cfg) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Primero vincula tu cuenta de Bambu Lab.")
    assert cfg is not None
    cfg.nube_solicitada_en = ahora()
    auditoria.registrar(db, "nube_sincronizar", usuario_id=usuario.id)
    await db.commit()
    return await _vista(db)


@router.delete("/nube", response_model=ConexionOut)
async def nube_desvincular(db: DB, usuario: Admin) -> ConexionOut:
    """Olvida el token de la cuenta. Los trabajos ya traídos se conservan."""
    cfg = await ajustes.obtener(db)
    if cfg is not None and cfg.nube_sesion:
        cfg.nube_sesion = None
        cfg.nube_correo = None
        cfg.nube_solicitada_en = ahora()  # para que el servicio ponga «sin vincular» al instante
        auditoria.registrar(db, "nube_desvinculada", usuario_id=usuario.id)
        await db.commit()
    return await _vista(db)
