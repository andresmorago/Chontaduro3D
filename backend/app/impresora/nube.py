"""Historial de trabajos de Bambu Cloud (el mismo que ven Bambu Studio y Bambu Handy).

API NO oficial: puede cambiar sin aviso. Por eso el parseo es tolerante y cualquier fallo se
informa (estado de la sincronización) sin afectar al resto de la app. El token lo deja el comando
`make bambu-login` en un archivo (nunca la contraseña) y aquí se renueva solo."""

import contextlib
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

AGENTE = "misimpresiones/1.0 (uso personal)"


class ErrorNube(Exception):
    """La nube no respondió como se esperaba (red, cambio de API, bloqueo)."""


class RequiereLogin(ErrorNube):
    """No hay token, o ya no sirve y no se pudo renovar: hay que repetir `make bambu-login`."""


# ------------------------------------------------------------------------------- token
@dataclass
class Sesion:
    access_token: str
    refresh_token: str = ""
    expira_en: float = 0.0  # epoch; 0 = desconocido

    def vigente(self) -> bool:
        return bool(self.access_token) and (
            self.expira_en == 0 or time.time() < self.expira_en - 60
        )


class AlmacenToken:
    """El token en un archivo JSON con permisos 600; se escribe de forma atómica."""

    def __init__(self, ruta: str | Path) -> None:
        self.ruta = Path(ruta)

    def existe(self) -> bool:
        return self.ruta.is_file()

    def cargar(self) -> Sesion | None:
        try:
            d = json.loads(self.ruta.read_text())
            return Sesion(
                str(d["access_token"]),
                str(d.get("refresh_token") or ""),
                float(d.get("expira_en") or 0),
            )
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def guardar(self, s: Sesion) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.ruta.parent, prefix=".bambu-")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({"access_token": s.access_token, "refresh_token": s.refresh_token,
                           "expira_en": s.expira_en}, f)  # fmt: skip
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.ruta)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp)


# ------------------------------------------------------------------------------ tareas
@dataclass
class Tarea:
    """Un trabajo del historial de la nube, ya normalizado."""

    id: str
    titulo: str
    estado: str  # terminado | interrumpido
    inicio: datetime
    fin: datetime
    minutos: int | None
    gramos: float | None
    plate: int | None
    dispositivo: str | None
    filamentos: list[dict[str, Any]] = field(default_factory=list)


def _fecha(v: Any) -> datetime | None:
    """ISO-8601 («2026-11-10T15:30:12Z», con o sin fracción) o epoch en segundos/milisegundos."""
    if v in (None, "", 0):
        return None
    try:
        if isinstance(v, (int, float)):
            seg = v / 1000 if v > 1e11 else v
            return datetime.fromtimestamp(seg, UTC)
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except (ValueError, OverflowError, OSError):
        return None


def _numero(v: Any) -> float | None:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _color(v: Any) -> str | None:
    s = str(v or "").strip().lstrip("#")
    return (
        "#" + s[:6].lower()
        if len(s) >= 6 and all(c in "0123456789abcdefABCDEF" for c in s[:6])
        else None
    )


def tarea_de(t: dict[str, Any]) -> Tarea | None:
    """Normaliza una tarea de la nube. None si no es un trabajo ya cerrado (en curso o sin fechas).

    Estado: 2 = terminado; otro estado con hora de fin (fallido o cancelado) = interrumpido."""
    if not isinstance(t, dict) or t.get("id") in (None, ""):
        return None
    inicio, fin = _fecha(t.get("startTime")), _fecha(t.get("endTime"))
    if inicio is None or fin is None or fin < inicio:
        return None
    estado_raw = t.get("status")
    if estado_raw == 1:  # en curso en la nube
        return None
    filamentos = []
    for m in t.get("amsDetailMapping") or []:
        g = _numero(m.get("weight")) if isinstance(m, dict) else None
        if g is None:
            continue
        filamentos.append({
            "tipo": str(m.get("targetFilamentType") or m.get("filamentType") or "").strip(),
            "color": _color(m.get("targetColor") or m.get("sourceColor")),
            "gramos": round(g, 2),
        })  # fmt: skip
    gramos = _numero(t.get("weight")) or (
        round(sum(f["gramos"] for f in filamentos), 2) if filamentos else None
    )
    segundos = _numero(t.get("costTime"))
    plate = t.get("plateIndex")
    return Tarea(
        id=str(t["id"]),
        titulo=str(
            t.get("title") or t.get("designTitle") or t.get("plateName") or "Trabajo sin nombre"
        )[:200],
        estado="terminado" if estado_raw == 2 else "interrumpido",
        inicio=inicio, fin=fin,
        minutos=max(1, round(segundos / 60)) if segundos else None,
        gramos=gramos,
        plate=int(plate) if isinstance(plate, (int, float)) and plate > 0 else None,
        dispositivo=str(t.get("deviceId") or "") or None,
        filamentos=filamentos,
    )  # fmt: skip


# ------------------------------------------------------------------------------ cliente
class ClienteNube:
    def __init__(self, base_url: str, almacen: AlmacenToken, http: httpx.Client | None = None):
        self._base = base_url.rstrip("/")
        self._almacen = almacen
        self._http = http or httpx.Client(timeout=20, headers={"User-Agent": AGENTE})

    def _sesion(self) -> Sesion:
        s = self._almacen.cargar()
        if s is None:
            raise RequiereLogin("Falta iniciar sesión en Bambu Cloud (make bambu-login).")
        return s

    def _renovar(self, s: Sesion) -> Sesion:
        if not s.refresh_token:
            raise RequiereLogin("El acceso a Bambu Cloud venció: repite make bambu-login.")
        try:
            r = self._http.post(
                f"{self._base}/v1/user-service/user/refreshtoken",
                json={"refreshToken": s.refresh_token},
            )
        except httpx.HTTPError as e:
            raise ErrorNube(f"Sin conexión con Bambu Cloud ({type(e).__name__}).") from e
        if r.status_code in (400, 401, 403):
            raise RequiereLogin("El acceso a Bambu Cloud venció: repite make bambu-login.")
        if r.status_code != 200:
            raise ErrorNube(f"Bambu Cloud respondió {r.status_code} al renovar el acceso.")
        d = r.json()
        nuevo = Sesion(
            str(d.get("accessToken") or ""),
            str(d.get("refreshToken") or s.refresh_token),
            time.time() + float(d.get("expiresIn") or 0) if d.get("expiresIn") else 0.0,
        )
        if not nuevo.access_token:
            raise ErrorNube("Bambu Cloud no devolvió un acceso nuevo.")
        self._almacen.guardar(nuevo)
        return nuevo

    def _get(self, ruta: str, params: dict) -> Any:
        s = self._sesion()
        if not s.vigente() and s.refresh_token:
            s = self._renovar(s)
        for intento in (1, 2):
            try:
                r = self._http.get(
                    f"{self._base}{ruta}", params=params,
                    headers={"Authorization": f"Bearer {s.access_token}"},
                )  # fmt: skip
            except httpx.HTTPError as e:
                raise ErrorNube(f"Sin conexión con Bambu Cloud ({type(e).__name__}).") from e
            if r.status_code == 401 and intento == 1:
                s = self._renovar(s)  # puede lanzar RequiereLogin
                continue
            if r.status_code == 401:
                raise RequiereLogin("Bambu Cloud rechazó el acceso: repite make bambu-login.")
            if r.status_code == 403:
                raise ErrorNube("Bambu Cloud bloqueó la petición (403).")
            if r.status_code != 200:
                raise ErrorNube(f"Bambu Cloud respondió {r.status_code}.")
            try:
                return r.json()
            except ValueError as e:
                raise ErrorNube("Bambu Cloud devolvió algo que no es JSON.") from e
        raise ErrorNube("No se pudo consultar Bambu Cloud.")  # pragma: no cover

    def tareas(
        self, desde: datetime, dispositivo: str | None = None, max_paginas: int = 6
    ) -> list[Tarea]:
        """Trabajos cerrados desde `desde` (más reciente primero). Pagina por el id del último."""
        vistos: set[str] = set()
        resultado: list[Tarea] = []
        despues: str | None = None
        for _ in range(max_paginas):
            params: dict[str, Any] = {"limit": 50}
            if despues:
                params["after"] = despues
            d = self._get("/v1/user-service/my/tasks", params)
            filas = d.get("hits") if isinstance(d, dict) else None
            if filas is None and isinstance(d, dict):
                filas = d.get("tasks") or d.get("list")
            if not isinstance(filas, list) or not filas:
                break
            nuevas = [f for f in filas if isinstance(f, dict) and str(f.get("id")) not in vistos]
            if not nuevas:  # la API ignoró el cursor: no seguir dando vueltas
                break
            vistos.update(str(f.get("id")) for f in nuevas)
            for f in nuevas:
                t = tarea_de(f)
                if t is None:
                    continue
                if dispositivo and t.dispositivo and t.dispositivo != dispositivo:
                    continue  # trabajo de otra impresora de la misma cuenta
                if t.fin >= desde:
                    resultado.append(t)
            ultimo = _fecha(nuevas[-1].get("startTime"))
            if len(filas) < 50 or (ultimo is not None and ultimo < desde):
                break
            despues = str(nuevas[-1].get("id"))
        return resultado
