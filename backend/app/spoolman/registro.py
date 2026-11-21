"""Crear en Spoolman la bobina que está en una ranura del AMS, con lo que informa la impresora.

Lo usan el botón «Crear en Spoolman» del panel y el registro automático de bobinas Bambu con
chip: como el UID del chip es único, una misma bobina nunca se registra dos veces (Spoolman
rechaza un chip ya vinculado)."""

from typing import Any

from app.spoolman.cliente import Bobina, ClienteSpoolman, ErrorSpoolman, TagEnUso

PROVEEDOR_BAMBU = "Bambu Lab"
# Las ubicaciones «AMS · Ranura 2» las escribe y limpia el servicio; cualquier otra la puso una
# persona (p. ej. «Estante A») y no se toca.
PREFIJO_UBICACION = "AMS · "
PESO_NETO_G = 1000.0
# Densidad (g/cm³) de los materiales comunes: Spoolman la exige al crear un filamento.
DENSIDAD = {
    "PLA": 1.24, "PETG": 1.27, "ABS": 1.04, "ASA": 1.07, "TPU": 1.21, "PC": 1.20,
    "PA": 1.14, "PAHT": 1.2, "PVA": 1.23, "PLA-CF": 1.29, "PETG-CF": 1.3,
}  # fmt: skip


def candidatas_a_adoptar(
    bobinas: list[Bobina], bandeja: dict[str, Any], ubicacion: str | None = None
) -> list[Bobina]:
    """Bobinas ya registradas (sin chip) que probablemente SON la de esta bandeja: activas, de
    Bambu Lab, sin ningún chip vinculado y con el mismo material y color. Si coinciden varias, se
    queda con la que ya figura en esa ranura (`ubicacion`); si aun así hay duda devuelve varias y
    quien llama NO debe adivinar. Sirve para vincularle el chip en vez de crear un duplicado."""
    material = (bandeja.get("tipo") or "").strip().casefold()
    color = (bandeja.get("color") or "").strip().lower()
    if not material or not color:
        return []
    mias = [
        b for b in bobinas
        if not b.archivada and not b.tags
        and (b.proveedor or "").casefold() == PROVEEDOR_BAMBU.casefold()
        and (b.material or "").casefold() == material and (b.color or "").lower() == color
    ]  # fmt: skip
    if len(mias) > 1 and ubicacion:
        en_ranura = [b for b in mias if b.ubicacion == ubicacion]
        if len(en_ranura) == 1:
            return en_ranura
    return mias


def gramos_usados(bandeja: dict[str, Any], peso: float) -> float:
    """Con chip, la impresora informa el % que queda: se refleja al registrar una bobina ya usada.
    Solo entre 1 y 99 %: 100 es «llena» (o «no se sabe») y 0 no es creíble."""
    r = bandeja.get("restante")
    if bandeja.get("tag") and isinstance(r, int) and 0 < r < 100:
        return round(peso * (100 - r) / 100, 1)
    return 0.0


async def crear_desde_bandeja(
    cliente: ClienteSpoolman,
    bandeja: dict[str, Any],
    *,
    peso: float | None = None,
    precio: float | None = None,
    ubicacion: str | None = None,
    restante: float | None = None,
) -> Bobina:
    """Crea (o reutiliza) proveedor y filamento, crea la bobina y, si tiene chip, lo vincula.
    Lanza `TagEnUso` si el chip ya pertenece a otra bobina (y no deja una bobina huérfana)."""
    tag = bandeja.get("tag")
    material = (bandeja.get("tipo") or "").strip() or None
    nombre = (bandeja.get("marca") or "").strip() or material
    peso = float(peso or bandeja.get("peso") or PESO_NETO_G)
    # Una bobina Bambu con chip es de Bambu Lab; sin chip no se sabe la marca.
    proveedor_id = await cliente.proveedor(PROVEEDOR_BAMBU) if tag else None
    filamento_id = await cliente.filamento(
        proveedor_id=proveedor_id, nombre=nombre, material=material, color=bandeja.get("color"),
        densidad=DENSIDAD.get((material or "").upper(), 1.24), diametro=1.75,
        peso=peso, precio=precio,
    )  # fmt: skip
    nueva = await cliente.crear_bobina(
        filamento_id, peso=peso, precio=precio, ubicacion=ubicacion,
        usado=(
            round(max(peso - restante, 0.0), 1)
            if restante is not None
            else gramos_usados(bandeja, peso)
        ),
    )  # fmt: skip
    if tag:
        try:
            await cliente.vincular_tag(nueva.id, str(tag))
        except (TagEnUso, ErrorSpoolman):
            await cliente.borrar_bobina(nueva.id)  # que no quede una bobina huérfana
            raise
    return nueva
