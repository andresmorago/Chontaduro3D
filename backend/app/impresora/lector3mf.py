"""Gramos, tiempo y colores de un trabajo, leídos del archivo .3mf que guarda la impresora.

El .3mf trae `Metadata/slice_info.config` con, por plate: el tiempo estimado (segundos), el peso
total (g) y los gramos por filamento. Son los ESTIMADOS del slicer, no una medición."""

import contextlib
import io
import re
import socket
import ssl
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from ftplib import FTP, FTP_TLS

from app.impresora.topes import acotar_filamentos, acotar_total

LIMITE_BYTES = 80 * 1024 * 1024  # un .3mf de impresora doméstica pesa unos pocos MB
LIMITE_XML = 5 * 1024 * 1024
CARPETAS = ("/", "/cache")


@dataclass
class InfoArchivo:
    plate: int | None = None
    minutos: int | None = None
    gramos: Decimal | None = None
    filamentos: list[dict] = field(default_factory=list)  # {"tipo", "color", "gramos"}


def _decimal(v: str | None) -> Decimal | None:
    try:
        d = Decimal(str(v))
    except (InvalidOperation, TypeError):
        return None
    return d if d.is_finite() and d > 0 else None


def plate_de(*textos: str | None) -> int | None:
    """«plate_2» en el nombre del archivo o del trabajo."""
    for t in textos:
        m = re.search(r"plate[_ -]?(\d+)", t or "", re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def analizar_3mf(contenido: bytes, plate: int | None = None) -> InfoArchivo | None:
    """Lee `slice_info.config`. Si el archivo trae varias plates y no se sabe cuál es, devuelve
    None (mejor sin dato que con el dato de otra plate)."""
    try:
        z = zipfile.ZipFile(io.BytesIO(contenido))
        # El XML de metadatos pesa unos KB: uno enorme (descomprimido) no es un .3mf normal.
        if z.getinfo("Metadata/slice_info.config").file_size > LIMITE_XML:
            return None
        raiz = ET.fromstring(z.read("Metadata/slice_info.config"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        return None

    plates = []
    for pl in raiz.iter("plate"):
        meta = {m.get("key"): m.get("value") for m in pl.findall("metadata")}
        plates.append((_entero(meta.get("index")), meta, pl))
    if not plates:
        return None
    if plate is not None:
        elegidas = [p for p in plates if p[0] == plate]
    else:
        elegidas = plates if len(plates) == 1 else []
    if len(elegidas) != 1:
        return None
    indice, meta, nodo = elegidas[0]

    filamentos = []
    for f in nodo.findall("filament"):
        g = _decimal(f.get("used_g"))
        if g is not None:
            color = (f.get("color") or "").strip().lower()
            filamentos.append(
                {"tipo": (f.get("type") or "").strip(), "color": color or None, "gramos": float(g)}
            )
    filamentos = acotar_filamentos(filamentos, "Archivo .3mf")
    segundos = _entero(meta.get("prediction"))
    gramos = acotar_total(_decimal(meta.get("weight")), "Archivo .3mf")
    if gramos is None and filamentos:
        gramos = sum((Decimal(str(f["gramos"])) for f in filamentos), Decimal(0))
    return InfoArchivo(
        plate=indice,
        minutos=max(1, round(segundos / 60)) if segundos else None,
        gramos=gramos.quantize(Decimal("0.01")) if gramos else None,
        filamentos=filamentos,
    )


def _entero(v: str | None) -> int | None:
    try:
        return int(float(v))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _norm(nombre: str) -> str:
    base = re.sub(r"\.(gcode\.)?3mf$", "", nombre.rsplit("/", 1)[-1], flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]+", "_", base.lower()).strip("_")


def elegir_archivo(
    nombres: list[str], archivo: str | None, nombre: str | None, solo_exacto: bool = False
) -> str | None:
    """El .3mf que corresponde al trabajo, entre los que hay en la impresora. Primero el nombre
    exacto que informa la impresora; después coincidencias por nombre normalizado (salvo que
    `solo_exacto`)."""
    tres_mf = [n for n in nombres if n.lower().endswith(".3mf")]
    exactos = []
    if archivo:
        exactos.append(archivo.rsplit("/", 1)[-1])
    if nombre:
        exactos += [f"{nombre}.gcode.3mf", f"{nombre}.3mf"]
    for e in exactos:
        for n in tres_mf:
            if n == e:
                return n
    if solo_exacto:
        return None
    objetivos = [t for t in (_norm(archivo or ""), _norm(nombre or "")) if t]
    for t in objetivos:
        for n in tres_mf:
            if _norm(n) == t:
                return n
    return None


def elegir_en_carpetas(
    listados: dict[str, dict[str, int]], archivo: str | None, nombre: str | None
) -> tuple[str, str] | None:
    """(carpeta, archivo) del trabajo. Un nombre EXACTO en cualquier carpeta gana a uno solo
    «parecido» de otra: la impresora guarda copias del mismo trabajo en `/` y en `/cache`, y un
    `X_plate_2.gcode.3mf` más nuevo en `/` no es el `X_plate_2.3mf` que de verdad se imprimió."""
    # 1) el archivo que informa la impresora, en cualquier carpeta; 2) los derivados del nombre del
    # trabajo; 3) coincidencias parecidas. Cada nivel mira TODAS las carpetas antes del siguiente.
    niveles = (
        {"archivo": archivo, "nombre": None, "solo_exacto": True},
        {"archivo": None, "nombre": nombre, "solo_exacto": True},
        {"archivo": archivo, "nombre": nombre, "solo_exacto": False},
    )
    for nivel in niveles:
        for carpeta, tamanos in listados.items():
            elegido = elegir_archivo(list(tamanos), **nivel)
            if elegido is not None:
                return carpeta, elegido
    return None


class _FTPSImplicito(FTP_TLS):
    """FTPS «implícito» (TLS desde el primer byte, puerto 990), como lo usa Bambu."""

    def connect(self, host="", port=0, timeout=-999, source_address=None):
        if host:
            self.host = host
        if port > 0:
            self.port = port
        if timeout != -999:
            self.timeout = timeout
        sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock = self.context.wrap_socket(sock, server_hostname=self.host)
        self.af = self.sock.family
        self.file = self.sock.makefile("r", encoding=self.encoding)
        self.welcome = self.getresp()
        return self.welcome

    def ntransfercmd(self, cmd, rest=None):
        conn, size = FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(
                conn, server_hostname=self.host, session=self.sock.session
            )
        return conn, size


def leer_de_la_impresora(
    ip: str, codigo: str, archivo: str | None, nombre: str | None, plate: int | None = None
) -> InfoArchivo | None:
    """Busca el .3mf del trabajo en la impresora (solo lectura) y lo analiza. None si no está o
    no se pudo leer. Bloqueante: llamar desde un hilo."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ftp = _FTPSImplicito(context=ctx)
    try:
        ftp.connect(ip, 990, timeout=20)
        ftp.login("bblp", codigo)
        ftp.prot_p()
        listados: dict[str, dict[str, int]] = {}
        for carpeta in CARPETAS:
            try:
                filas: list[str] = []
                ftp.retrlines(f"LIST {carpeta}", filas.append)
            except Exception:  # noqa: BLE001 — una carpeta que falta no impide mirar la otra
                continue
            tamanos = {}
            for fila in filas:
                partes = fila.split(None, 8)
                if len(partes) == 9 and partes[4].isdigit():
                    tamanos[partes[8]] = int(partes[4])
            listados[carpeta] = tamanos
        hallado = elegir_en_carpetas(listados, archivo, nombre)
        if hallado is not None:
            carpeta, elegido = hallado
            if listados[carpeta].get(elegido, 0) > LIMITE_BYTES:
                return None
            buffer = io.BytesIO()
            ftp.retrbinary(f"RETR {carpeta.rstrip('/')}/{elegido}", buffer.write)
            return analizar_3mf(buffer.getvalue(), plate or plate_de(archivo, nombre, elegido))
        return None
    finally:
        with contextlib.suppress(Exception):
            ftp.close()
