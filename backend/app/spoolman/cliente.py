"""Cliente de la API REST de Spoolman (v1).

Spoolman no tiene autenticación: solo se le habla por la red interna de Docker (SPOOLMAN_URL).
Todo fallo de red o de servidor sale como `ErrorSpoolman` (el servicio lo reintenta); los casos con
significado propio tienen su excepción (`NoExiste`, `TagEnUso`)."""

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

TIEMPO_S = 6.0
FORMATO_TAG_BAMBU = "bambu"


class ErrorSpoolman(Exception):
    """Spoolman no contesta o contestó con un error de servidor."""


class NoAlcanzable(ErrorSpoolman):
    """No se pudo ni abrir la conexión: la petición NO salió, es seguro reintentar."""


class Rechazo(ErrorSpoolman):
    """Spoolman contestó con un error: no aplicó la petición (se reintenta si `reintentable`)."""

    def __init__(self, mensaje: str, *, reintentable: bool):
        super().__init__(mensaje)
        self.reintentable = reintentable


class NoExiste(ErrorSpoolman):
    """La bobina (o lo pedido) ya no está en Spoolman."""


class TagEnUso(ErrorSpoolman):
    """El chip RFID ya está vinculado a otra bobina."""

    def __init__(self, spool_id: int | None):
        super().__init__("Ese chip RFID ya está vinculado a otra bobina.")
        self.spool_id = spool_id


@dataclass(frozen=True)
class Bobina:
    """Lo que la app necesita de una bobina de Spoolman."""

    id: int
    nombre: str  # «Bambu Lab · PLA Basic · Blanco»
    material: str | None
    color: str | None  # «#rrggbb»
    restante_g: float | None
    inicial_g: float | None
    precio: float | None
    ubicacion: str | None
    archivada: bool
    tags: tuple[str, ...]  # UID de los chips RFID vinculados (mayúsculas, sin separadores)
    proveedor: str | None = None  # «Bambu Lab», «Sunlu»…


def validar_url(url: str) -> str:
    """http(s) con anfitrión; sin credenciales ni ruta rara. Vacío = integración apagada."""
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    partes = urlsplit(url)
    if partes.scheme not in ("http", "https") or not partes.hostname or partes.username:
        raise ValueError("SPOOLMAN_URL debe ser http(s)://anfitrión[:puerto] sin usuario.")
    return url


def _color(v: Any) -> str | None:
    s = str(v or "").strip().lstrip("#")
    ok = len(s) >= 6 and all(c in "0123456789abcdefABCDEF" for c in s[:6])
    return "#" + s[:6].lower() if ok else None


def _numero(v: Any) -> float | None:
    try:
        return round(float(v), 1) if v is not None else None
    except (TypeError, ValueError):
        return None


def bobina_de(d: dict[str, Any]) -> Bobina:
    fil = d.get("filament") or {}
    marca = (fil.get("vendor") or {}).get("name")
    partes = [p for p in (marca, fil.get("name") or fil.get("material")) if p]
    return Bobina(
        id=int(d["id"]),
        nombre=" · ".join(partes) or f"Bobina {d['id']}",
        material=fil.get("material"),
        color=_color(fil.get("color_hex")),
        restante_g=_numero(d.get("remaining_weight")),
        inicial_g=_numero(d.get("initial_weight") or fil.get("weight")),
        precio=_numero(d.get("price") if d.get("price") is not None else fil.get("price")),
        ubicacion=d.get("location") or None,
        archivada=bool(d.get("archived")),
        tags=tuple(str(t.get("uid", "")).upper() for t in d.get("tags") or [] if t.get("uid")),
        proveedor=marca,
    )


class ClienteSpoolman:
    def __init__(self, url: str, *, transporte: httpx.AsyncBaseTransport | None = None) -> None:
        self._http = httpx.AsyncClient(
            base_url=f"{validar_url(url)}/api/v1", timeout=TIEMPO_S, transport=transporte
        )

    async def cerrar(self) -> None:
        await self._http.aclose()

    async def _pedir(self, metodo: str, ruta: str, **kw: Any) -> Any:
        try:
            r = await self._http.request(metodo, ruta, **kw)
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            raise NoAlcanzable(f"No se alcanza Spoolman ({type(e).__name__}).") from None
        except httpx.HTTPError as e:
            # Puede haber llegado y aplicarse sin que veamos la respuesta (p. ej. tiempo agotado).
            raise ErrorSpoolman(f"Spoolman no respondió a tiempo ({type(e).__name__}).") from None
        if r.status_code == 404:
            raise NoExiste("Esa bobina ya no existe en Spoolman.")
        if r.status_code == 409:
            try:
                spool_id = r.json().get("spool_id")
            except ValueError:
                spool_id = None
            raise TagEnUso(spool_id if isinstance(spool_id, int) else None)
        if r.status_code >= 400:
            raise Rechazo(f"Spoolman respondió {r.status_code}.", reintentable=r.status_code >= 500)
        if r.status_code == 204 or not r.content:
            return None  # p. ej. quitar un chip: Spoolman contesta sin cuerpo
        try:
            return r.json()
        except ValueError:
            raise ErrorSpoolman("Spoolman respondió algo ilegible.") from None

    async def info(self) -> dict[str, Any]:
        return await self._pedir("GET", "/info")

    async def bobinas(self, *, archivadas: bool = False) -> list[Bobina]:
        filas = await self._pedir("GET", "/spool", params={"allow_archived": archivadas})
        return [bobina_de(f) for f in filas]

    async def bobina_por_tag(self, uid: str) -> Bobina | None:
        """La bobina (aunque esté archivada) que tiene ese chip vinculado, o None."""
        filas = await self._pedir("GET", "/spool", params={"tag": uid, "allow_archived": True})
        return bobina_de(filas[0]) if filas else None

    async def bobina(self, spool_id: int) -> Bobina:
        return bobina_de(await self._pedir("GET", f"/spool/{spool_id}"))

    async def usar(self, spool_id: int, gramos: float) -> Bobina:
        """Resta `gramos` de la bobina (suma a su peso usado). NO es idempotente."""
        return bobina_de(
            await self._pedir("PUT", f"/spool/{spool_id}/use", json={"use_weight": gramos})
        )

    async def proveedor(self, nombre: str) -> int:
        """Id del proveedor con ese nombre (sin distinguir mayúsculas); lo crea si no existe."""
        for v in await self._pedir("GET", "/vendor", params={"name": nombre}):
            if str(v.get("name", "")).casefold() == nombre.casefold():
                return int(v["id"])
        return int((await self._pedir("POST", "/vendor", json={"name": nombre}))["id"])

    async def filamento(
        self,
        *,
        proveedor_id: int | None,
        nombre: str | None,
        material: str | None,
        color: str | None,
        densidad: float,
        diametro: float,
        peso: float,
        precio: float | None,
    ) -> int:
        """Id del filamento (mismo proveedor, nombre, material y color); lo crea si no existe, para
        que varias bobinas iguales compartan el filamento en vez de duplicarlo."""
        params: dict[str, Any] = {}
        if proveedor_id is not None:
            params["vendor_id"] = proveedor_id
        if material:
            params["material"] = material
        hexa = (color or "").lstrip("#").upper() or None
        # La «línea» del chip («PLA Basic» → «basic»): el catálogo nombra «Basic Red», «Pure White»…
        linea = (nombre or "").casefold().removeprefix((material or "").casefold()).strip()
        parecidos = []
        for f in await self._pedir("GET", "/filament", params=params):
            mismo_proveedor = (f.get("vendor") or {}).get("id") == proveedor_id
            mismo_material = str(f.get("material") or "").casefold() == (material or "").casefold()
            mismo_color = str(f.get("color_hex") or "").upper() == (hexa or "")
            if not (mismo_proveedor and mismo_material and mismo_color):
                continue
            if str(f.get("name") or "").casefold() == (nombre or "").casefold():
                return int(f["id"])
            if linea and linea in str(f.get("name") or "").casefold().split():
                parecidos.append(int(f["id"]))
        if len(parecidos) == 1:  # «Basic Red» ya es el «PLA Basic» rojo: no se crea otro filamento
            return parecidos[0]
        cuerpo = {
            "name": nombre, "vendor_id": proveedor_id, "material": material, "color_hex": hexa,
            "density": densidad, "diameter": diametro, "weight": peso, "price": precio,
        }  # fmt: skip
        return int((await self._pedir("POST", "/filament", json=cuerpo))["id"])

    async def crear_bobina(
        self,
        filamento_id: int,
        *,
        peso: float,
        precio: float | None,
        ubicacion: str | None,
        usado: float = 0.0,
    ) -> Bobina:
        cuerpo = {
            "filament_id": filamento_id, "initial_weight": peso, "price": precio,
            "location": ubicacion, "used_weight": usado,
        }  # fmt: skip
        return bobina_de(await self._pedir("POST", "/spool", json=cuerpo))

    async def ubicar(self, spool_id: int, ubicacion: str | None) -> None:
        """Cambia (o quita, con None) la ubicación de una bobina."""
        await self._pedir("PATCH", f"/spool/{spool_id}", json={"location": ubicacion or ""})

    async def borrar_bobina(self, spool_id: int) -> None:
        try:
            await self._pedir("DELETE", f"/spool/{spool_id}")
        except NoExiste:
            return

    async def vincular_tag(self, spool_id: int, uid: str, formato: str = FORMATO_TAG_BAMBU) -> None:
        await self._pedir("POST", f"/spool/{spool_id}/tag", json={"uid": uid, "format": formato})

    async def desvincular_tag(self, spool_id: int, uid: str) -> None:
        try:
            await self._pedir("DELETE", f"/spool/{spool_id}/tag/{uid}")
        except NoExiste:
            return  # ya no estaba: es lo que se quería
