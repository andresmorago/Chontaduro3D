from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

# En JSON el dinero viaja como número (COP no usa decimales en la práctica).
Dinero = Annotated[
    Decimal,
    Field(ge=0, le=Decimal("99999999"), max_digits=12, decimal_places=2),
    PlainSerializer(lambda v: float(v), return_type=float, when_used="json"),
]
DineroSalida = Annotated[
    Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")
]


class Salida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Entrada(BaseModel):
    # Campos desconocidos = error: no se cuelan datos que el backend no espera.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
