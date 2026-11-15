"""Servicio de la impresora: `python -m app.impresora.servicio`.

La configuración (IP, serial, código de acceso, cuenta de Bambu Cloud) sale de la base, donde la
deja Administración → Conexión: el servicio reconecta solo cuando cambia. Cada pocos segundos:
(1) guarda el estado en `impresora_estado`, (2) detecta trabajos nuevos o
terminados y los guarda en `trabajos_impresora` (con gramos y tiempo del .3mf), (3) envía las
órdenes pendientes que dejó el backend. Nunca se cae por un error de la impresora o de la red:
registra y reintenta."""

import asyncio
import contextlib
import logging
import signal
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select, update

from app.config import settings
from app.core import secretos
from app.db import SessionLocal, engine
from app.impresora import ajustes, bambu, lector3mf, maquina, nube, sincronizacion
from app.models import ComandoImpresora, EstadoImpresora, TrabajoImpresora

log = logging.getLogger("impresora")

CICLO_S = 2
LATIDO_S = 10  # aunque nada cambie, se actualiza la fila para que se vea que el servicio vive
PEDIR_TODO_S = 60
ORDEN_VIGENTE_S = 30  # una orden más vieja que esto no se ejecuta (p. ej. tras una caída)
MENSAJE_RECIENTE_S = 90
REINTENTO_ARCHIVO_S = 60
INTENTOS_ARCHIVO = 6
NUBE_CADA_S = 600  # el historial de la nube cambia poco: cada 10 minutos basta
NUBE_REINTENTO_S = 120  # tras un fallo, se reintenta antes


def _progreso(snap: maquina.Instantanea) -> int:
    """Progreso real. Al preparar es 0: aún se informa el 100 % del trabajo anterior."""
    if snap.gcode_state == "PREPARE":
        return 0
    return max(0, min(snap.progreso, 100))


def _ahora() -> datetime:
    return datetime.now(UTC)


class Servicio:
    def __init__(self, cliente=None, nube_cliente=None) -> None:
        # `cliente` se inyecta en las pruebas y entonces no se reconecta con la configuración;
        # en producción es la conexión MQTT real, creada con lo guardado en la base.
        self.cliente = cliente
        self._cliente_fijo = cliente is not None
        self._conexion: ajustes.Conexion | None = None
        self._heredado_revisado = False
        self._solicitada_vista: datetime | None = None
        self._solicitud_nueva = False
        self._ultimo_estado: dict | None = None
        self._ultima_escritura = datetime.min.replace(tzinfo=UTC)
        self._ultimo_pushall = datetime.min.replace(tzinfo=UTC)
        # ¿Se vio el inicio de verdad, o el servicio arrancó con el trabajo ya andando?
        self._vio_inactiva = False
        self._intentos: dict[str, tuple[int, datetime]] = {}
        self._parar = asyncio.Event()
        # Historial de Bambu Cloud (opcional: solo si se vinculó la cuenta en el panel). El token
        # vive cifrado en la base; aquí se presta a `ClienteNube` y se devuelve si se renovó.
        self._memoria = nube.AlmacenMemoria()
        self._nube = nube_cliente or nube.ClienteNube(settings.bambu_nube_url, self._memoria)
        self._nube_proxima = datetime.min.replace(tzinfo=UTC)

    # ------------------------------------------------------------- configuración
    async def _importar_heredado(self, db, fila):
        """Una sola vez al arrancar: si la base aún no tiene configuración, la toma de lo que se
        usaba antes (BAMBU_* del .env y el token de data/nube/bambu.json) y lo deja guardado
        (cifrado) en la base. Desde entonces el .env y el archivo ya no hacen falta.

        NO borra ni modifica nada fuera de la base: el archivo puede ser compartido con otro
        servicio (p. ej. el de producción con código anterior). Para que no reaparezca tras
        desvincular, el token solo se importa si la cuenta nunca se vinculó ni desvinculó
        (`nube_solicitada_en` vacío)."""
        env_completo = settings.bambu_ip and settings.bambu_serial and settings.bambu_access_code
        if env_completo and (fila is None or not (fila.ip and fila.serial and fila.codigo_acceso)):
            try:
                ip = ajustes.validar_ip(settings.bambu_ip)
                serie = ajustes.validar_serial(settings.bambu_serial)
                codigo = ajustes.validar_codigo(settings.bambu_access_code)
            except ValueError as e:
                log.warning("BAMBU_* del .env no sirven (%s); se ignoran.", e)
            else:
                fila = fila or await ajustes.obtener_o_crear(db)
                fila.ip, fila.serial = ip, serie
                fila.codigo_acceso = secretos.cifrar(codigo)
                fila.version += 1
                log.info("Configuración de la impresora importada del .env a la base.")
        archivo = Path(settings.bambu_nube_archivo)
        nunca_vinculada = fila is None or (not fila.nube_sesion and fila.nube_solicitada_en is None)
        if nunca_vinculada and archivo.is_file():
            sesion = nube.AlmacenToken(archivo).cargar()
            if sesion is not None:
                fila = fila or await ajustes.obtener_o_crear(db)
                ajustes.poner_sesion(fila, sesion)
                fila.nube_solicitada_en = _ahora()
                log.info("Token de Bambu Cloud importado de %s a la base.", archivo)
        return fila

    async def _cargar_config(self) -> None:
        """Lee la configuración de la base y reconecta si cambió."""
        async with SessionLocal() as db:
            fila = await ajustes.obtener(db)
            if not self._heredado_revisado:
                fila = await self._importar_heredado(db, fila)
                await db.commit()
                self._heredado_revisado = True
            conexion = ajustes.conexion_de(fila)
            solicitada = fila.nube_solicitada_en if fila else None
        self._solicitud_nueva = solicitada is not None and solicitada != self._solicitada_vista
        self._solicitada_vista = solicitada
        if self._cliente_fijo or conexion == self._conexion:
            return
        if self.cliente is not None:
            await asyncio.to_thread(self.cliente.detener)
        self._conexion, self.cliente = conexion, None
        self._ultimo_estado, self._vio_inactiva = None, False
        self._ultimo_pushall = datetime.min.replace(tzinfo=UTC)
        self._intentos.clear()
        if conexion is None:
            log.info(
                "Sin configuración de la impresora: queda en espera (Administración → Conexión)."
            )
            return
        self.cliente = bambu.ClienteBambu(conexion.ip, conexion.serial, conexion.codigo)
        self.cliente.iniciar()
        log.info("Conectando con la impresora en %s.", conexion.ip)

    # ------------------------------------------------------------------ estado
    async def _escribir_estado(self) -> None:
        crudo = self.cliente.crudo() if self.cliente else None
        datos = bambu.normalizar(crudo) if crudo else None
        ultimo = self.cliente.ultimo_mensaje if self.cliente else None
        reciente = ultimo is not None and (_ahora() - ultimo).total_seconds() < MENSAJE_RECIENTE_S
        conectada = bool(self.cliente and self.cliente.conectada and reciente)
        version = self._conexion.version if self._conexion else None
        error = None if conectada else getattr(self.cliente, "error_conexion", None)
        foto = {"datos": datos, "conectada": conectada, "version": version, "error": error}
        ahora = _ahora()
        if (
            foto == self._ultimo_estado
            and (ahora - self._ultima_escritura).total_seconds() < LATIDO_S
        ):
            return
        async with SessionLocal() as db:
            fila = await db.get(EstadoImpresora, 1)
            if fila is None:
                fila = EstadoImpresora(id=1)
                db.add(fila)
            fila.conectada, fila.datos = conectada, datos
            fila.config_version, fila.conexion_error = version, error
            fila.ultimo_mensaje_en, fila.actualizado_en = ultimo, ahora
            await db.commit()
        self._ultimo_estado, self._ultima_escritura = foto, ahora

    # ---------------------------------------------------------------- trabajos
    async def _leer_archivo(
        self, trabajo: TrabajoImpresora, crudo: dict, forzar: bool = False
    ) -> None:
        """Intenta completar gramos y tiempo desde el .3mf (con reintentos espaciados; `forzar`
        salta la espera, para la última oportunidad al terminar el trabajo)."""
        clave = str(trabajo.id)
        n, ultimo = self._intentos.get(clave, (0, datetime.min.replace(tzinfo=UTC)))
        ahora = _ahora()
        if not forzar and (
            n >= INTENTOS_ARCHIVO or (ahora - ultimo).total_seconds() < REINTENTO_ARCHIVO_S
        ):
            return
        self._intentos[clave] = (n + 1, ahora)
        try:
            info = await asyncio.to_thread(
                lector3mf.leer_de_la_impresora,
                self._conexion.ip if self._conexion else "",
                self._conexion.codigo if self._conexion else "",
                trabajo.archivo or crudo.get("gcode_file"), trabajo.nombre, trabajo.plate,
            )  # fmt: skip
        except Exception as e:  # noqa: BLE001 — la red o la impresora pueden fallar: se reintenta
            log.warning("No se pudo leer el .3mf de «%s»: %s", trabajo.nombre, type(e).__name__)
            return
        if info is None:
            log.info("Sin .3mf para «%s» (intento %d)", trabajo.nombre, n + 1)
            return
        trabajo.plate = info.plate
        trabajo.minutos_estimados = info.minutos
        trabajo.gramos_total = info.gramos
        trabajo.filamentos = info.filamentos or None
        log.info("«%s»: %s g, %s min (del .3mf)", trabajo.nombre, info.gramos, info.minutos)

    async def _seguir_trabajos(self) -> None:
        if self.cliente is None:
            return
        crudo = self.cliente.crudo()
        if not crudo or "gcode_state" not in crudo:
            return
        snap = maquina.instantanea_de(crudo)
        if snap.gcode_state not in bambu.ACTIVOS:
            self._vio_inactiva = True
        async with SessionLocal() as db:
            fila = (
                await db.execute(
                    select(TrabajoImpresora)
                    .where(TrabajoImpresora.estado == "en_curso")
                    .order_by(TrabajoImpresora.inicio_en.desc())
                    .with_for_update()
                )
            ).scalars().all()  # fmt: skip
            # Si una caída dejó varios abiertos, solo el más nuevo sigue; los demás se cierran.
            abierto = fila[0] if fila else None
            for viejo in fila[1:]:
                viejo.estado, viejo.fin_en = "interrumpido", _ahora()
            ref = (
                maquina.Abierto(abierto.nombre, abierto.archivo or "", abierto.tarea_id)
                if abierto
                else None
            )
            for accion in maquina.decidir(snap, ref):
                ahora = _ahora()
                if accion.cerrar and abierto is not None:
                    if abierto.gramos_total is None:
                        # Última oportunidad de datos (también para un trabajo interrumpido).
                        await self._leer_archivo(abierto, crudo, forzar=True)
                    abierto.estado = accion.cerrar
                    abierto.fin_en = ahora
                    abierto.progreso = 100 if accion.cerrar == "terminado" else abierto.progreso
                    self._intentos.pop(str(abierto.id), None)
                    log.info("Trabajo «%s»: %s", abierto.nombre, accion.cerrar)
                    abierto = None
                if accion.abrir:
                    abierto = TrabajoImpresora(
                        nombre=snap.nombre[:200], archivo=snap.archivo[:300] or None,
                        tarea_id=snap.tarea_id[:40], inicio_en=ahora,
                        inicio_observado=self._vio_inactiva, progreso=_progreso(snap),
                        plate=lector3mf.plate_de(snap.archivo, snap.nombre),
                    )  # fmt: skip
                    db.add(abierto)
                    await db.flush()
                    log.info("Trabajo nuevo: «%s»", abierto.nombre)
                if accion.actualizar_progreso and abierto is not None:
                    abierto.progreso = _progreso(snap)
            if (
                abierto is not None
                and abierto.gramos_total is None
                and abierto.estado == "en_curso"
            ):
                await self._leer_archivo(abierto, crudo)
            await db.commit()

    # ------------------------------------------------------------- historial (nube)
    async def _guardar_nube(self, estado: str, detalle: str | None, ok: bool = False) -> None:
        async with SessionLocal() as db:
            fila = await db.get(EstadoImpresora, 1)
            if fila is None:
                fila = EstadoImpresora(id=1)
                db.add(fila)
            fila.nube_estado, fila.nube_detalle = estado, detalle
            fila.nube_atendida_en = _ahora()
            if ok:
                fila.nube_sincronizada_en = _ahora()
            await db.commit()

    async def _devolver_token_renovado(self, antes: str | None) -> None:
        """Si la consulta renovó el token, se guarda la versión nueva (salvo que mientras tanto
        se haya vinculado otra cuenta o desvinculado: entonces manda lo del panel)."""
        sesion = self._memoria.cargar()
        if not self._memoria.cambio or sesion is None:
            return
        async with SessionLocal() as db:
            fila = await ajustes.obtener(db)
            if fila is not None and fila.nube_sesion == antes:
                ajustes.poner_sesion(fila, sesion)
                await db.commit()

    async def _sincronizar_nube(self) -> None:
        """Trae los trabajos de los últimos días del historial de Bambu Cloud."""
        if self._solicitud_nueva:  # el panel pidió «sincronizar ahora» (o vinculó/desvinculó)
            self._nube_proxima = datetime.min.replace(tzinfo=UTC)
        if _ahora() < self._nube_proxima:
            return
        async with SessionLocal() as db:
            fila = await ajustes.obtener(db)
            cifrado = fila.nube_sesion if fila else None
            sesion = ajustes.sesion_de(fila)
        if sesion is None:
            self._nube_proxima = _ahora() + timedelta(seconds=NUBE_CADA_S)
            await self._guardar_nube("sin_configurar", None)
            return
        self._memoria.poner(sesion)
        desde = _ahora() - timedelta(days=settings.bambu_nube_dias)
        serie = self._conexion.serial if self._conexion else None
        try:
            tareas = await asyncio.to_thread(self._nube.tareas, desde, serie)
            async with SessionLocal() as db:
                r = await sincronizacion.aplicar(db, tareas)
                await db.commit()
            log.info("Historial de la nube: %d tareas, %s", len(tareas), r)
            await self._devolver_token_renovado(cifrado)
            await self._guardar_nube("ok", None, ok=True)
            self._nube_proxima = _ahora() + timedelta(seconds=NUBE_CADA_S)
        except nube.RequiereLogin as e:
            await self._guardar_nube("requiere_login", str(e)[:200])
            self._nube_proxima = _ahora() + timedelta(seconds=NUBE_CADA_S)
        except nube.ErrorNube as e:
            log.warning("Historial de la nube: %s", e)
            await self._devolver_token_renovado(cifrado)
            await self._guardar_nube("error", str(e)[:200])
            self._nube_proxima = _ahora() + timedelta(seconds=NUBE_REINTENTO_S)

    # ----------------------------------------------------------------- órdenes
    async def _atender_ordenes(self) -> None:
        async with SessionLocal() as db:
            limite = _ahora() - timedelta(seconds=ORDEN_VIGENTE_S)
            await db.execute(
                update(ComandoImpresora)
                .where(ComandoImpresora.estado == "pendiente", ComandoImpresora.creado_en < limite)
                .values(estado="vencido", atendido_en=_ahora(), detalle="Pasó demasiado tiempo.")
            )
            pendientes = (
                await db.execute(
                    select(ComandoImpresora)
                    .where(ComandoImpresora.estado == "pendiente")
                    .order_by(ComandoImpresora.id)
                    .with_for_update(skip_locked=True)
                )
            ).scalars().all()  # fmt: skip
            for orden in pendientes:
                orden.atendido_en = _ahora()
                if self.cliente is None or not self.cliente.conectada:
                    orden.estado, orden.detalle = "fallido", "La impresora no está conectada."
                    continue
                try:
                    ok = await asyncio.to_thread(self.cliente.enviar, orden.comando, orden.valor)
                    orden.estado = "enviado" if ok else "fallido"
                    orden.detalle = None if ok else "La impresora no recibió la orden."
                    log.info("Orden %s %s: %s", orden.comando, orden.valor or "", orden.estado)
                except Exception as e:  # noqa: BLE001
                    orden.estado, orden.detalle = "fallido", f"Error: {type(e).__name__}"
            await db.commit()

    # ------------------------------------------------------------------- bucle
    async def correr(self) -> None:
        if self.cliente is not None:  # inyectado (pruebas)
            self.cliente.iniciar()
        log.info("Servicio de impresora iniciado.")
        while not self._parar.is_set():
            for paso in (
                self._cargar_config,
                self._escribir_estado,
                self._seguir_trabajos,
                self._sincronizar_nube,
                self._atender_ordenes,
            ):
                try:
                    await paso()
                except Exception:  # noqa: BLE001
                    log.exception("Fallo en %s; se reintenta.", paso.__name__)
            if (
                self.cliente is not None
                and (_ahora() - self._ultimo_pushall).total_seconds() > PEDIR_TODO_S
                and self.cliente.conectada
            ):
                self.cliente.pedir_todo()
                self._ultimo_pushall = _ahora()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._parar.wait(), CICLO_S)
        if self.cliente is not None:
            await asyncio.to_thread(self.cliente.detener)
        await engine.dispose()

    def parar(self) -> None:
        self._parar.set()


async def principal() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    servicio = Servicio()
    bucle = asyncio.get_running_loop()
    for senal in (signal.SIGINT, signal.SIGTERM):
        bucle.add_signal_handler(senal, servicio.parar)
    await servicio.correr()


if __name__ == "__main__":
    asyncio.run(principal())
