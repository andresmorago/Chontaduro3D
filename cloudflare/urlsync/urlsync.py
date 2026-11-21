#!/usr/bin/env python3
"""Mantiene el Worker de workers.dev apuntando al quick tunnel vigente.

cloudflared (quick tunnel) expone su hostname en http://cloudflared:2000/quicktunnel.
Cada vez que cambia, este proceso sube de nuevo el Worker con ORIGIN = esa URL.

Solo biblioteca estándar. Credenciales por entorno (nunca por argumento ni en logs):
  CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, WORKER_NOMBRE, PROXY_SHARED_SECRET

Uso:  urlsync.py            (bucle, para el contenedor)
      urlsync.py --una-vez  (sube una vez y sale)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

API = "https://api.cloudflare.com/client/v4"
METRICAS = os.environ.get("METRICAS_URL", "http://cloudflared:2000/quicktunnel")
HOST_VALIDO = re.compile(r"^[a-z0-9-]+\.trycloudflare\.com$")
INTERVALO = int(os.environ.get("URLSYNC_INTERVALO", "15"))
CODIGO = Path(os.environ.get("WORKER_CODIGO", Path(__file__).resolve().parent.parent / "worker" / "index.js"))


def log(msg: str) -> None:
    print(f"[urlsync] {msg}", flush=True)


def entorno(nombre: str) -> str:
    valor = os.environ.get(nombre, "").strip()
    if not valor:
        sys.exit(f"[urlsync] Falta {nombre} en el entorno.")
    return valor


def hostname_actual() -> str | None:
    if not METRICAS.startswith(("http://", "https://")):  # urlopen aceptaría también file://
        return None
    try:
        with urllib.request.urlopen(METRICAS, timeout=5) as r:
            host = json.load(r).get("hostname", "")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return host if HOST_VALIDO.fullmatch(host) else None


def llamar(metodo: str, ruta: str, token: str, cuerpo: bytes | None = None, tipo: str = "application/json"):
    req = urllib.request.Request(f"{API}{ruta}", data=cuerpo, method=metodo)
    req.add_header("Authorization", f"Bearer {token}")
    if cuerpo is not None:
        req.add_header("Content-Type", tipo)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            detalle = json.load(e).get("errors")
        except ValueError:
            detalle = None
        # Solo el código y los errores de la API: nunca cabeceras ni el token.
        sys.exit(f"[urlsync] Cloudflare respondió {e.code} en {metodo} {ruta}: {detalle}")


def subir_worker(origen: str, cuenta: str, nombre: str, token: str, secreto: str) -> None:
    metadata = {
        "main_module": "index.js",
        "compatibility_date": "2025-01-01",
        "bindings": [{"type": "plain_text", "name": "ORIGIN", "text": origen}]
        + ([{"type": "secret_text", "name": "PROXY_SECRET", "text": secreto}] if secreto else []),
    }
    frontera = uuid.uuid4().hex
    partes = [
        (
            'Content-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n'
            + json.dumps(metadata)
        ).encode(),
        (
            'Content-Disposition: form-data; name="index.js"; filename="index.js"\r\n'
            "Content-Type: application/javascript+module\r\n\r\n"
        ).encode()
        + CODIGO.read_bytes(),
    ]
    cuerpo = b"".join(b"--" + frontera.encode() + b"\r\n" + p + b"\r\n" for p in partes) + b"--" + frontera.encode() + b"--\r\n"
    llamar("PUT", f"/accounts/{cuenta}/workers/scripts/{nombre}", token, cuerpo, f"multipart/form-data; boundary={frontera}")
    # Publica el Worker en <nombre>.<subdominio-de-la-cuenta>.workers.dev.
    llamar("POST", f"/accounts/{cuenta}/workers/scripts/{nombre}/subdomain", token, json.dumps({"enabled": True}).encode())


def url_publica(cuenta: str, nombre: str, token: str) -> str | None:
    sub = llamar("GET", f"/accounts/{cuenta}/workers/subdomain", token).get("result", {}).get("subdomain")
    return f"https://{nombre}.{sub}.workers.dev" if sub else None


def main() -> int:
    token = entorno("CLOUDFLARE_API_TOKEN")
    cuenta = entorno("CLOUDFLARE_ACCOUNT_ID")
    nombre = os.environ.get("WORKER_NOMBRE", "misimpresiones").strip()
    secreto = os.environ.get("PROXY_SHARED_SECRET", "").strip()
    una_vez = "--una-vez" in sys.argv

    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", nombre):
        sys.exit("[urlsync] WORKER_NOMBRE debe ser minúsculas, dígitos y guiones.")
    if not secreto:
        # Sin secreto, el Worker no lo adjunta y el frontend no lo exige: la URL directa del túnel serviría la app.
        sys.exit("[urlsync] PROXY_SHARED_SECRET vacío: no se publica el Worker sin la puerta de origen.")

    ultimo = None
    while True:
        host = hostname_actual()
        if host and host != ultimo:
            log(f"túnel detectado: {host}; actualizando el Worker «{nombre}»…")
            subir_worker(f"https://{host}", cuenta, nombre, token, secreto)
            ultimo = host
            log(f"listo: {url_publica(cuenta, nombre, token) or '(subdominio workers.dev sin configurar)'}")
        if una_vez and ultimo:
            return 0
        if una_vez and not host:
            log("el túnel todavía no tiene URL; reintentando…")
        time.sleep(INTERVALO if not una_vez else 3)


if __name__ == "__main__":
    sys.exit(main())
