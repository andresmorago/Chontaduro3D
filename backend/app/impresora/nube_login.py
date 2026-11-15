"""Inicio de sesión en Bambu Cloud desde el panel (reemplaza a `make bambu-login`).

API NO oficial. La contraseña solo pasa por aquí hacia Bambu: no se guarda ni se registra; lo único
que se conserva es el token. Flujo en dos pasos cuando Bambu pide verificación:
  1. `entrar(correo, clave)`  → listo | codigo (Bambu manda un código al correo) | tfa
  2. `verificar_codigo(...)` / `verificar_tfa(...)` → listo
Si Bambu bloquea el inicio de sesión (captcha, IP del servidor), queda `desde_token` (pegar el
token de la cookie de bambulab.com)."""

import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.impresora.nube import AGENTE, Sesion

TFA_URL = "https://bambulab.com/api/sign-in/tfa"


class ErrorLogin(Exception):
    """Mensaje para mostrar a la persona (sin datos sensibles)."""


@dataclass
class Resultado:
    paso: str  # listo | codigo | tfa
    sesion: Sesion | None = None
    tfa_key: str | None = None


def _sesion(d: dict[str, Any]) -> Sesion | None:
    if not d.get("accessToken"):
        return None
    exp = time.time() + float(d["expiresIn"]) if d.get("expiresIn") else 0.0
    return Sesion(str(d["accessToken"]), str(d.get("refreshToken") or ""), exp)


class LoginNube:
    def __init__(self, base_url: str, http: httpx.AsyncClient | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._http = http or httpx.AsyncClient(timeout=30, headers={"User-Agent": AGENTE})

    async def _post(self, url: str, cuerpo: dict) -> httpx.Response:
        try:
            return await self._http.post(url, json=cuerpo)
        except httpx.HTTPError as e:
            raise ErrorLogin(f"No hay conexión con Bambu Cloud ({type(e).__name__}).") from e

    @staticmethod
    def _json(r: httpx.Response) -> dict[str, Any]:
        try:
            d = r.json()
        except ValueError:
            return {}
        return d if isinstance(d, dict) else {}

    def _rechazo(self, r: httpx.Response, d: dict[str, Any], que: str) -> ErrorLogin:
        if r.status_code in (403, 429) or "captcha" in str(d).lower():
            return ErrorLogin(
                "Bambu bloqueó el inicio de sesión desde este servidor. Usa «Pegar token»."
            )
        motivo = str(d.get("message") or d.get("error") or "")[:120]
        return ErrorLogin(
            f"Bambu no aceptó {que} ({r.status_code}){': ' + motivo if motivo else ''}."
        )

    async def entrar(self, correo: str, clave: str) -> Resultado:
        r = await self._post(
            f"{self._base}/v1/user-service/user/login", {"account": correo, "password": clave}
        )
        d = self._json(r)
        if r.status_code != 200:
            raise self._rechazo(r, d, "el correo o la contraseña")
        if (s := _sesion(d)) is not None:
            return Resultado("listo", s)
        if d.get("loginType") == "verifyCode":
            await self._post(
                f"{self._base}/v1/user-service/user/sendemail/code",
                {"email": correo, "type": "codeLogin"},
            )
            return Resultado("codigo")
        if d.get("loginType") == "tfa" and d.get("tfaKey"):
            return Resultado("tfa", tfa_key=str(d["tfaKey"]))
        raise ErrorLogin("Bambu respondió algo inesperado. Usa «Pegar token».")

    async def verificar_codigo(self, correo: str, codigo: str) -> Resultado:
        r = await self._post(
            f"{self._base}/v1/user-service/user/login", {"account": correo, "code": codigo}
        )
        d = self._json(r)
        if r.status_code != 200 or (s := _sesion(d)) is None:
            raise self._rechazo(r, d, "el código")
        return Resultado("listo", s)

    async def verificar_tfa(self, tfa_key: str, codigo: str) -> Resultado:
        r = await self._post(TFA_URL, {"tfaKey": tfa_key, "tfaCode": codigo})
        d = self._json(r)
        token = r.cookies.get("token") if r.status_code == 200 else None
        if token:
            return Resultado("listo", Sesion(token))
        if r.status_code == 200 and (s := _sesion(d)) is not None:
            return Resultado("listo", s)
        raise self._rechazo(r, d, "el código de verificación")


def desde_token(token: str) -> Sesion:
    """El token copiado de la cookie «token» de bambulab.com (sin renovación automática)."""
    t = token.strip().removeprefix("token=").strip().strip('"')
    if len(t) < 20 or any(c.isspace() for c in t):
        raise ErrorLogin("Eso no parece un token de Bambu.")
    return Sesion(t)
