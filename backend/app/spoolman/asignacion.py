"""Qué bandeja del AMS (y de ahí qué bobina) usó cada filamento de un trabajo.

Lógica pura. La A1 no informa el mapeo del trabajo, solo en qué bandeja estaba la impresora
(`tray_now`) mientras imprimía; el servicio guarda esas bandejas vistas (`bandejas`) y aquí se
emparejan con los filamentos del .3mf. Es conservador a propósito: si hay duda devuelve None y la
persona elige la bobina; descontar de la bobina equivocada es peor que pedir una confirmación."""

from dataclasses import dataclass
from typing import Any

# Distancia máxima (RGB, 0–441) para dar por «el mismo color» y ventaja mínima sobre el segundo.
COLOR_IGUAL = 48.0
COLOR_VENTAJA = 24.0
# Para saber si la bandeja sigue con la misma bobina que cuando se vinculó.
COLOR_MISMO = 24.0


def norm_tipo(t: str | None) -> str:
    return "".join(c for c in (t or "").lower() if c.isalnum())


def _rgb(c: str | None) -> tuple[int, int, int] | None:
    s = (c or "").strip().lstrip("#")
    if len(s) < 6:
        return None
    try:
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except ValueError:
        return None


def distancia(a: str | None, b: str | None) -> float | None:
    x, y = _rgb(a), _rgb(b)
    if x is None or y is None:
        return None
    return sum((p - q) ** 2 for p, q in zip(x, y, strict=True)) ** 0.5


def misma_bobina(tipo_a, color_a, tipo_b, color_b) -> bool:
    """¿La bandeja `b` sigue teniendo lo mismo que cuando se vinculó (`a`)? Sin datos de color de
    alguno de los dos, solo cuenta el tipo."""
    if norm_tipo(tipo_a) != norm_tipo(tipo_b):
        return False
    d = distancia(color_a, color_b)
    return d is None or d <= COLOR_MISMO


@dataclass(frozen=True)
class Emparejado:
    filamento: int  # posición en la lista de filamentos
    bandeja: dict[str, Any] | None


def emparejar(filamentos: list[dict[str, Any]], bandejas: list[dict[str, Any]]) -> list[Emparejado]:
    """`filamentos`: {tipo, color, gramos} del .3mf. `bandejas`: {ranura, tipo, color, tag} vistas
    durante el trabajo. Devuelve, por filamento, la bandeja o None si no es inequívoco."""
    if not bandejas:
        return [Emparejado(i, None) for i in range(len(filamentos))]

    # Un solo filamento y una sola bandeja vista: es esa, aunque el tipo del archivo no coincida
    # (lo que importa es qué había físicamente puesto).
    if len(filamentos) == 1:
        if len(bandejas) == 1:
            return [Emparejado(0, bandejas[0])]
        return [Emparejado(0, _elegir(filamentos[0], bandejas))]

    libres = list(bandejas)
    resultado: list[Emparejado] = []
    for i, f in enumerate(filamentos):
        elegida = _elegir(f, libres)
        if elegida is not None:
            libres = [b for b in libres if b is not elegida]
        resultado.append(Emparejado(i, elegida))
    return resultado


def _elegir(filamento: dict[str, Any], candidatas: list[dict[str, Any]]) -> dict[str, Any] | None:
    del_tipo = [
        b for b in candidatas if norm_tipo(b.get("tipo")) == norm_tipo(filamento.get("tipo"))
    ]
    if not del_tipo:
        return None
    if len(del_tipo) == 1:
        return del_tipo[0]
    puntuadas = sorted(
        (
            (d, i)
            for i, b in enumerate(del_tipo)
            if (d := distancia(filamento.get("color"), b.get("color"))) is not None
        ),
    )
    if not puntuadas or puntuadas[0][0] > COLOR_IGUAL:
        return None
    if len(puntuadas) > 1 and puntuadas[1][0] - puntuadas[0][0] < COLOR_VENTAJA:
        return None  # dos bandejas igual de parecidas: que elija la persona
    return del_tipo[puntuadas[0][1]]
