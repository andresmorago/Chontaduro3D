#!/usr/bin/env python3
"""Inicia sesión en Bambu Cloud y guarda SOLO el token (nunca la contraseña) en data/nube/bambu.json.

Uso:   make bambu-login                  (correo + contraseña + código que Bambu envía a tu correo)
       make bambu-login ARGS=--pegar     (si el inicio de sesión falla o se bloquea: pegar el token
                                          copiado del navegador)

Solo usa la biblioteca estándar. Escribe en la terminal, no en el chat: la contraseña no se guarda
ni se muestra. La API de Bambu no es oficial y puede cambiar."""

import argparse
import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("BAMBU_NUBE_URL", "https://api.bambulab.com").rstrip("/")
DESTINO = Path(os.environ.get("BAMBU_TOKEN_ARCHIVO", "data/nube/bambu.json"))
AGENTE = "misimpresiones/1.0 (uso personal)"


def post(url: str, cuerpo: dict) -> tuple[int, dict, str]:
    req = urllib.request.Request(
        url,
        data=json.dumps(cuerpo).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": AGENTE},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            crudo = r.read().decode() or "{}"
            return r.status, json.loads(crudo), r.headers.get("Set-Cookie", "")
    except urllib.error.HTTPError as e:
        crudo = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(crudo), ""
        except ValueError:
            return e.code, {"mensaje": crudo[:120]}, ""


def guardar(access: str, refresh: str = "", expira_en: float = 0.0) -> None:
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    tmp = DESTINO.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"access_token": access, "refresh_token": refresh, "expira_en": expira_en})
    )
    os.chmod(tmp, 0o600)
    os.replace(tmp, DESTINO)
    print(f"\nListo. Token guardado en {DESTINO} (permisos 600). La contraseña no se guardó.")
    print("El servicio de la impresora lo toma solo en unos minutos")
    print("(o reinícialo para que sea ya: make prod-restart s=impresora).")


def desde_respuesta(d: dict) -> bool:
    if not d.get("accessToken"):
        return False
    exp = time.time() + float(d["expiresIn"]) if d.get("expiresIn") else 0.0
    guardar(str(d["accessToken"]), str(d.get("refreshToken") or ""), exp)
    return True


def login() -> int:
    correo = input("Correo de tu cuenta Bambu: ").strip()
    clave = getpass.getpass("Contraseña (no se muestra): ")
    st, d, _ = post(f"{BASE}/v1/user-service/user/login", {"account": correo, "password": clave})
    clave = ""
    if st != 200:
        print(f"Bambu respondió {st}: {d.get('message') or d.get('mensaje') or d}", file=sys.stderr)
        print("Si es un bloqueo o un captcha, usa: make bambu-login ARGS=--pegar", file=sys.stderr)
        return 1
    if desde_respuesta(d):
        return 0
    tipo = d.get("loginType")
    if tipo == "verifyCode":
        post(f"{BASE}/v1/user-service/user/sendemail/code", {"email": correo, "type": "codeLogin"})
        print("Bambu te envió un código por correo.")
        codigo = input("Código de verificación: ").strip()
        st, d, _ = post(f"{BASE}/v1/user-service/user/login", {"account": correo, "code": codigo})
        if st == 200 and desde_respuesta(d):
            return 0
        print(f"No se pudo verificar el código ({st}).", file=sys.stderr)
        return 1
    if tipo == "tfa":
        codigo = input("Código de tu app de autenticación (2FA): ").strip()
        st, d, cookie = post(
            "https://bambulab.com/api/sign-in/tfa", {"tfaKey": d.get("tfaKey"), "tfaCode": codigo}
        )
        token = next(
            (p.split("=", 1)[1] for p in cookie.split(";") if p.strip().startswith("token=")), ""
        )
        if st == 200 and token:
            guardar(token)
            return 0
        if st == 200 and desde_respuesta(d):
            return 0
        print(f"No se pudo verificar el 2FA ({st}). Prueba: make bambu-login ARGS=--pegar", file=sys.stderr)
        return 1
    print("Respuesta inesperada de Bambu; no se guardó nada.", file=sys.stderr)
    print("Prueba: make bambu-login ARGS=--pegar", file=sys.stderr)
    return 1


def pegar() -> int:
    print("Inicia sesión en https://bambulab.com, abre las herramientas del navegador (F12) →")
    print("Aplicación/Almacenamiento → Cookies → bambulab.com y copia el valor de la cookie «token».")
    token = getpass.getpass("Pega el token (no se muestra): ").strip()
    if len(token) < 20:
        print("Eso no parece un token.", file=sys.stderr)
        return 1
    guardar(token)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pegar", action="store_true", help="pegar un token copiado del navegador")
    sys.exit(pegar() if ap.parse_args().pegar else login())
