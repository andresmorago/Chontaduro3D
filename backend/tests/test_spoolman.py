"""Integración con Spoolman: emparejamiento, cliente HTTP, descuento de filamento y API."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select, text

from app.api import spoolman as api_spoolman
from app.config import settings
from app.db import SessionLocal, engine
from app.impresora.servicio import Servicio
from app.main import app
from app.models import (
    ConsumoFilamento,
    EstadoSpoolman,
    RanuraBobina,
    TrabajoImpresora,
)
from app.spoolman import asignacion
from app.spoolman import consumo as consumo_mod
from app.spoolman.cliente import (
    Bobina,
    ClienteSpoolman,
    ErrorSpoolman,
    NoAlcanzable,
    NoExiste,
    Rechazo,
    TagEnUso,
    bobina_de,
    validar_url,
)
from app.spoolman.dependencia import cliente_spoolman

TAG = "0E45AABBCCDD1122"
ROJO, AZUL, BLANCO = "#ff0000", "#0000ff", "#ffffff"


# ------------------------------------------------------------------ Spoolman de mentira
class FalsoSpoolman:
    """Lo mínimo de Spoolman que usa la app, en memoria."""

    def __init__(self):
        self.bobinas_: dict[int, Bobina] = {}
        self.usos: list[tuple[int, float]] = []
        self.caido = False  # no se alcanza (la petición no sale)
        self.ambiguo = False  # el envío sale pero no se ve la respuesta
        self.version = "0.27.1"
        self.proveedores: dict[str, int] = {}
        self.filamentos_: list[dict] = []
        self.creadas: list[dict] = []
        self.archivadas: dict[str, int] = {}  # chip → id de una bobina archivada que lo tiene
        self._siguiente = 100

    def agregar(self, id_, nombre="Bambu Lab · PLA Basic", color=ROJO, restante=800.0, tags=(),
                proveedor="Bambu Lab", ubicacion=None, precio=60000.0):  # fmt: skip
        self.bobinas_[id_] = Bobina(
            id=id_, nombre=nombre, material="PLA", color=color, restante_g=restante,
            inicial_g=1000.0, precio=precio, ubicacion=ubicacion, archivada=False,
            tags=tuple(t.upper() for t in tags), proveedor=proveedor,
        )  # fmt: skip
        return self

    def _vivo(self):
        if self.caido:
            raise NoAlcanzable("No se alcanza Spoolman (ConnectError).")

    async def info(self):
        self._vivo()
        return {"version": self.version}

    async def bobinas(self, *, archivadas=False):
        self._vivo()
        extra = []
        if archivadas:
            extra = [Bobina(id=i, nombre="archivada", material=None, color=None, restante_g=0,
                            inicial_g=1000, precio=None, ubicacion=None, archivada=True,
                            tags=(t,)) for t, i in self.archivadas.items()]  # fmt: skip
        return [*self.bobinas_.values(), *extra]

    async def bobina(self, spool_id):
        self._vivo()
        if spool_id not in self.bobinas_:
            raise NoExiste("Esa bobina ya no existe en Spoolman.")
        return self.bobinas_[spool_id]

    async def usar(self, spool_id, gramos):
        self._vivo()
        if self.ambiguo:
            raise ErrorSpoolman("Spoolman no respondió a tiempo (ReadTimeout).")
        b = await self.bobina(spool_id)
        self.usos.append((spool_id, gramos))
        nuevo = Bobina(**{**b.__dict__, "restante_g": (b.restante_g or 0) - gramos})
        self.bobinas_[spool_id] = nuevo
        return nuevo

    async def vincular_tag(self, spool_id, uid, formato="bambu"):
        self._vivo()
        uid = uid.upper()
        if uid in self.archivadas:
            raise TagEnUso(self.archivadas[uid])
        for b in self.bobinas_.values():
            if uid in b.tags and b.id != spool_id:
                raise TagEnUso(b.id)
        b = self.bobinas_[spool_id]
        if uid not in b.tags:
            self.bobinas_[spool_id] = Bobina(**{**b.__dict__, "tags": (*b.tags, uid)})

    async def desvincular_tag(self, spool_id, uid):
        self._vivo()
        b = self.bobinas_.get(spool_id)
        if b is not None:
            quedan = tuple(t for t in b.tags if t != uid.upper())
            self.bobinas_[spool_id] = Bobina(**{**b.__dict__, "tags": quedan})

    async def proveedor(self, nombre):
        self._vivo()
        return self.proveedores.setdefault(nombre, len(self.proveedores) + 1)

    async def filamento(self, **kw):
        self._vivo()
        for i, f in enumerate(self.filamentos_):
            if all(f[k] == kw[k] for k in ("proveedor_id", "nombre", "material", "color")):
                return i + 1
        self.filamentos_.append(kw)
        return len(self.filamentos_)

    async def crear_bobina(self, filamento_id, *, peso, precio, ubicacion, usado=0.0):
        self._vivo()
        self._siguiente += 1
        f = self.filamentos_[filamento_id - 1]
        self.creadas.append({"id": self._siguiente, "filamento": f, "peso": peso, "precio": precio,
                             "ubicacion": ubicacion, "usado": usado})  # fmt: skip
        self.agregar(self._siguiente, nombre=f["nombre"] or "?", color=f["color"],
                     restante=peso - usado)  # fmt: skip
        return self.bobinas_[self._siguiente]

    async def borrar_bobina(self, spool_id):
        self.bobinas_.pop(spool_id, None)

    async def editar(self, spool_id, *, restante=None, precio=None, archivada=None):
        self._vivo()
        b = await self.bobina(spool_id)
        cambios = {}
        if restante is not None:
            cambios["restante_g"] = restante
        if precio is not None:
            cambios["precio"] = precio
        nueva = Bobina(**{**b.__dict__, **cambios, "archivada": bool(archivada)})
        if archivada:
            self.bobinas_.pop(spool_id)  # una archivada deja de salir en la lista normal
        else:
            self.bobinas_[spool_id] = nueva
        return nueva

    async def ubicar(self, spool_id, ubicacion):
        self._vivo()
        b = self.bobinas_[spool_id]
        self.bobinas_[spool_id] = Bobina(**{**b.__dict__, "ubicacion": ubicacion or None})

    async def bobina_por_tag(self, uid):
        for b in self.bobinas_.values():
            if uid.upper() in b.tags:
                return b
        return None

    async def cerrar(self):
        pass


@pytest.fixture
def spool():
    return FalsoSpoolman()


@pytest.fixture
def con_spoolman(spool, monkeypatch):
    """El backend web ve el Spoolman de mentira."""
    monkeypatch.setattr(settings, "spoolman_url", "http://spoolman:8000")
    monkeypatch.setattr(settings, "spoolman_web", "http://10.6.0.6:7912")

    async def falso():
        yield spool

    app.dependency_overrides[cliente_spoolman] = falso
    yield spool
    app.dependency_overrides.pop(cliente_spoolman, None)


@pytest.fixture(autouse=True)
async def limpiar_spoolman():
    async with engine.begin() as c:
        await c.execute(
            text(
                "TRUNCATE trabajos_impresora, ranura_bobinas, spoolman_estado, chips_bobina CASCADE"
            )
        )
    yield


def bandeja(ranura, tipo="PLA", color=ROJO, tag=None, en_uso=False):
    return {"id": ranura, "vacia": False, "tipo": tipo, "marca": None, "color": color,
            "medido": bool(tag), "tag": tag, "restante": None, "en_uso": en_uso}  # fmt: skip


async def poner_ams(db, *bandejas, externa=None):
    from app.models import EstadoImpresora

    fila = await db.get(EstadoImpresora, 1)
    if fila is None:
        fila = EstadoImpresora(id=1)
        db.add(fila)
    fila.conectada = True
    fila.actualizado_en = datetime.now(UTC)
    fila.datos = {"estado": "lista", "ams": list(bandejas), "externa": externa}
    await db.commit()


async def crear_trabajo(
    db, nombre="Soporte", estado="terminado", fin=None, filamentos=None, bandejas=None, progreso=100
):
    t = TrabajoImpresora(
        nombre=nombre, estado=estado, inicio_en=datetime.now(UTC) - timedelta(hours=2),
        fin_en=fin or datetime.now(UTC), progreso=progreso,
        filamentos=filamentos or [{"tipo": "PLA", "color": ROJO, "gramos": 12.5}],
        gramos_total=sum(f["gramos"] for f in (filamentos or [{"gramos": 12.5}])),
        bandejas=bandejas,
    )  # fmt: skip
    db.add(t)
    await db.commit()
    return t


async def lineas(db):
    db.expire_all()
    return (
        (await db.execute(select(ConsumoFilamento).order_by(ConsumoFilamento.orden)))
        .scalars()
        .all()
    )


async def ciclo(servicio):
    servicio._spoolman_proximo = datetime.min.replace(tzinfo=UTC)
    await servicio._sincronizar_spoolman()


# ============================================================ emparejamiento (lógica pura)
def test_un_filamento_y_una_bandeja_vista_es_esa_aunque_el_tipo_no_coincida():
    (e,) = asignacion.emparejar(
        [{"tipo": "PLA", "color": ROJO, "gramos": 5}],
        [{"ranura": "2", "tipo": "PETG", "color": AZUL}],
    )
    assert e.bandeja["ranura"] == "2"


def test_varios_filamentos_se_emparejan_por_tipo_y_color():
    b = [
        {"ranura": "0", "tipo": "PLA", "color": ROJO},
        {"ranura": "1", "tipo": "PLA", "color": AZUL},
        {"ranura": "2", "tipo": "PETG", "color": BLANCO},
    ]
    fil = [
        {"tipo": "PLA", "color": "#0a0af0", "gramos": 3},
        {"tipo": "PETG", "color": "#fafafa", "gramos": 4},
        {"tipo": "PLA", "color": "#f00a0a", "gramos": 5},
    ]
    assert [e.bandeja["ranura"] for e in asignacion.emparejar(fil, b)] == ["1", "2", "0"]


def test_si_hay_duda_no_adivina():
    dos_rojos = [
        {"ranura": "0", "tipo": "PLA", "color": "#ff0000"},
        {"ranura": "1", "tipo": "PLA", "color": "#f80000"},
    ]
    assert (
        asignacion.emparejar([{"tipo": "PLA", "color": "#ff0000", "gramos": 5}], dos_rojos)[
            0
        ].bandeja
        is None
    )
    sin_vistas = asignacion.emparejar([{"tipo": "PLA", "color": ROJO, "gramos": 5}], [])
    assert sin_vistas[0].bandeja is None
    lejano = [
        {"ranura": "0", "tipo": "PLA", "color": AZUL},
        {"ranura": "1", "tipo": "PLA", "color": BLANCO},
    ]
    assert (
        asignacion.emparejar([{"tipo": "PLA", "color": ROJO, "gramos": 5}], lejano)[0].bandeja
        is None
    )


def test_misma_bobina():
    assert asignacion.misma_bobina("PLA", "#ff0000", "pla", "#fe0101")
    assert not asignacion.misma_bobina("PLA", "#ff0000", "PETG", "#ff0000")
    assert not asignacion.misma_bobina("PLA", "#ff0000", "PLA", "#0000ff")
    assert asignacion.misma_bobina(
        "PLA", None, "PLA", "#0000ff"
    )  # sin color guardado: solo el tipo


# ==================================================================== cliente HTTP
def cliente_con(handler) -> ClienteSpoolman:
    return ClienteSpoolman("http://spoolman:8000", transporte=httpx.MockTransport(handler))


async def test_el_filamento_se_reconoce_por_la_linea_del_chip_aunque_cambie_el_nombre():
    creados = []

    def fil(id_, nombre, proveedor):
        return {"id": id_, "name": nombre, "material": "PLA", "color_hex": "C12E1F",
                "vendor": {"id": proveedor}}  # fmt: skip

    existentes = [fil(8, "Basic Red", 2), fil(9, "Pure Red", 2), fil(10, "Basic Red", 5)]

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/v1/filament" and req.method == "GET":
            return httpx.Response(200, json=existentes)
        if req.url.path == "/api/v1/filament" and req.method == "POST":
            creados.append(req.content)
            return httpx.Response(200, json={"id": 99})
        return httpx.Response(404)

    c = cliente_con(handler)
    kw = dict(densidad=1.24, diametro=1.75, peso=1000.0, precio=None, material="PLA")
    # «PLA Basic» rojo de Bambu (proveedor 2) es «Basic Red»; no «Pure Red» ni el de otro proveedor.
    assert await c.filamento(proveedor_id=2, nombre="PLA Basic", color="#c12e1f", **kw) == 8
    assert await c.filamento(proveedor_id=2, nombre="Basic Red", color="#c12e1f", **kw) == 8
    # Otra línea sin filamento parecido, o un color distinto: se crea (no se mezcla lo diferente).
    assert await c.filamento(proveedor_id=2, nombre="PLA Matte", color="#c12e1f", **kw) == 99
    assert await c.filamento(proveedor_id=2, nombre="PLA Basic", color="#0000ff", **kw) == 99
    assert len(creados) == 2


async def test_cliente_lee_bobinas_y_usa_filamento():
    vistos = []

    def handler(req: httpx.Request) -> httpx.Response:
        vistos.append((req.method, req.url.path, req.content))
        if req.url.path == "/api/v1/spool" and req.method == "GET":
            return httpx.Response(200, json=[{
                "id": 7, "archived": False, "remaining_weight": 812.34, "initial_weight": 1000,
                "price": None, "location": "AMS",
                "filament": {"name": "PLA Basic", "material": "PLA", "color_hex": "FF0000",
                             "price": 59000, "weight": 1000, "vendor": {"name": "Bambu Lab"}},
                "tags": [{"uid": "0e45aabb", "format": "bambu", "added": "x"}],
            }])  # fmt: skip
        if req.url.path == "/api/v1/spool/7/use":
            return httpx.Response(200, json={"id": 7, "filament": {}, "remaining_weight": 800})
        return httpx.Response(404)

    c = cliente_con(handler)
    (b,) = await c.bobinas()
    assert (b.id, b.nombre, b.color, b.precio, b.tags) == (
        7, "Bambu Lab · PLA Basic", "#ff0000", 59000.0, ("0E45AABB",),
    )  # fmt: skip
    await c.usar(7, 12.5)
    assert vistos[-1][0] == "PUT" and b'"use_weight":12.5' in vistos[-1][2].replace(b" ", b"")
    with pytest.raises(NoExiste):
        await c.bobina(99)


async def test_cliente_distingue_los_errores():
    def conflicto(_):
        return httpx.Response(409, json={"message": "en uso", "spool_id": 3})

    with pytest.raises(TagEnUso) as e:
        await cliente_con(conflicto).vincular_tag(1, "AA")
    assert e.value.spool_id == 3

    with pytest.raises(Rechazo) as r:
        await cliente_con(lambda _: httpx.Response(503)).info()
    assert r.value.reintentable
    with pytest.raises(Rechazo) as r:
        await cliente_con(lambda _: httpx.Response(422)).info()
    assert not r.value.reintentable

    def sin_red(req):
        raise httpx.ConnectError("no hay ruta", request=req)

    with pytest.raises(NoAlcanzable):
        await cliente_con(sin_red).info()

    def lento(req):
        raise httpx.ReadTimeout("lento", request=req)

    with pytest.raises(ErrorSpoolman) as e2:
        await cliente_con(lento).usar(1, 1)
    assert not isinstance(e2.value, NoAlcanzable | Rechazo)  # ambiguo: pudo aplicarse

    # Spoolman responde sin cuerpo (204) al quitar un chip: no es un error.
    await cliente_con(lambda _: httpx.Response(204)).desvincular_tag(1, "AA")
    with pytest.raises(ErrorSpoolman):  # pero un 200 con basura sí lo es
        await cliente_con(lambda _: httpx.Response(200, content=b"<html>")).info()

    # Quitar un chip que ya no está es lo que se quería.
    await cliente_con(lambda _: httpx.Response(404)).desvincular_tag(1, "AA")


def test_validar_url():
    assert (
        validar_url("") == "" and validar_url(" http://spoolman:8000/ ") == "http://spoolman:8000"
    )
    for mala in ("ftp://x", "spoolman:8000", "http://u:p@x"):
        with pytest.raises(ValueError):
            validar_url(mala)


def test_bobina_de_tolera_datos_incompletos():
    b = bobina_de({"id": 5, "filament": {}})
    assert b.nombre == "Bobina 5" and b.color is None and b.restante_g is None and b.tags == ()


# =============================================== servicio: de un trabajo terminado a Spoolman
@pytest.fixture
def servicio(spool):
    return Servicio(cliente=None, spoolman_cliente=spool)


async def test_trabajo_con_chip_rfid_vinculado_descuenta_una_sola_vez(servicio, spool, db):
    spool.agregar(7, tags=[TAG])
    await ciclo(servicio)  # primera conexión: fija «desde»
    await crear_trabajo(db, bandejas=[{"ranura": "1", "tipo": "PLA", "color": ROJO, "tag": TAG}])
    await ciclo(servicio)
    (c,) = await lineas(db)
    assert (c.estado, c.spool_id, c.ranura, c.gramos) == ("descontado", 7, "1", Decimal("12.50"))
    assert spool.usos == [(7, 12.5)] and c.descontado_en is not None
    for _ in range(3):  # los siguientes ciclos no repiten nada
        await ciclo(servicio)
    assert spool.usos == [(7, 12.5)] and len(await lineas(db)) == 1


async def test_lo_impreso_antes_de_conectar_spoolman_no_se_descuenta(servicio, spool, db):
    spool.agregar(7, tags=[TAG])
    await crear_trabajo(
        db, fin=datetime.now(UTC) - timedelta(days=3),
        bandejas=[{"ranura": "1", "tipo": "PLA", "color": ROJO, "tag": TAG}],
    )  # fmt: skip
    await ciclo(servicio)
    assert await lineas(db) == [] and spool.usos == []


async def test_chip_sin_vincular_espera_y_se_descuenta_al_vincularlo(servicio, spool, db):
    spool.agregar(7)  # la bobina existe pero su chip no está vinculado
    await ciclo(servicio)
    await crear_trabajo(db, bandejas=[{"ranura": "1", "tipo": "PLA", "color": ROJO, "tag": TAG}])
    await ciclo(servicio)
    (c,) = await lineas(db)
    assert c.estado == "sin_bobina" and "ranura 2" in c.detalle and spool.usos == []
    await spool.vincular_tag(7, TAG)  # la persona vincula el chip
    await ciclo(servicio)
    (c,) = await lineas(db)
    assert c.estado == "descontado" and spool.usos == [(7, 12.5)]


async def test_bobina_sin_chip_usa_el_vinculo_de_la_ranura_si_sigue_igual(servicio, spool, db):
    spool.agregar(4)
    db.add(RanuraBobina(ranura="0", spool_id=4, tipo="PLA", color=ROJO))
    await db.commit()
    await ciclo(servicio)
    await crear_trabajo(db, bandejas=[{"ranura": "0", "tipo": "PLA", "color": ROJO, "tag": None}])
    await ciclo(servicio)
    (c,) = await lineas(db)
    assert c.estado == "descontado" and c.spool_id == 4


async def test_si_la_ranura_cambio_de_filamento_no_adivina(servicio, spool, db):
    spool.agregar(4)
    db.add(RanuraBobina(ranura="0", spool_id=4, tipo="PLA", color=ROJO))
    await db.commit()
    await ciclo(servicio)
    await crear_trabajo(
        db, filamentos=[{"tipo": "PETG", "color": AZUL, "gramos": 9}],
        bandejas=[{"ranura": "0", "tipo": "PETG", "color": AZUL, "tag": None}],
    )  # fmt: skip
    await ciclo(servicio)
    (c,) = await lineas(db)
    assert c.estado == "sin_bobina" and spool.usos == []


async def test_trabajo_sin_bandejas_vistas_pide_elegir(servicio, spool, db):
    spool.agregar(4)
    await ciclo(servicio)
    await crear_trabajo(db, bandejas=None)
    await ciclo(servicio)
    (c,) = await lineas(db)
    assert c.estado == "sin_bobina" and c.ranura is None and "elige la bobina" in c.detalle


async def test_trabajo_cortado_descuenta_la_parte_hecha(servicio, spool, db):
    spool.agregar(7, tags=[TAG])
    await ciclo(servicio)
    await crear_trabajo(
        db, estado="interrumpido", progreso=40,
        filamentos=[{"tipo": "PLA", "color": ROJO, "gramos": 20}],
        bandejas=[{"ranura": "1", "tipo": "PLA", "color": ROJO, "tag": TAG}],
    )  # fmt: skip
    await ciclo(servicio)
    (c,) = await lineas(db)
    assert (c.gramos_plan, c.gramos, c.estado) == (Decimal("20.00"), Decimal("8.00"), "descontado")
    assert spool.usos == [(7, 8.0)]


async def test_trabajo_cortado_sin_avance_no_descuenta(servicio, spool, db):
    spool.agregar(7, tags=[TAG])
    await ciclo(servicio)
    await crear_trabajo(
        db, estado="interrumpido", progreso=0,
        bandejas=[{"ranura": "1", "tipo": "PLA", "color": ROJO, "tag": TAG}],
    )  # fmt: skip
    await ciclo(servicio)
    (c,) = await lineas(db)
    assert c.estado == "omitido" and spool.usos == []


async def test_varios_filamentos_descuentan_cada_uno_de_su_bobina(servicio, spool, db):
    spool.agregar(7, tags=[TAG]).agregar(8, color=AZUL, tags=["AAAA000011112222"])
    await ciclo(servicio)
    await crear_trabajo(
        db,
        filamentos=[
            {"tipo": "PLA", "color": ROJO, "gramos": 10},
            {"tipo": "PLA", "color": AZUL, "gramos": 4},
        ],
        bandejas=[
            {"ranura": "0", "tipo": "PLA", "color": AZUL, "tag": "AAAA000011112222"},
            {"ranura": "1", "tipo": "PLA", "color": ROJO, "tag": TAG},
        ],
    )  # fmt: skip
    await ciclo(servicio)
    assert sorted(spool.usos) == [(7, 10.0), (8, 4.0)]


async def test_spoolman_caido_reintenta_sin_perder_ni_duplicar(servicio, spool, db):
    spool.agregar(7, tags=[TAG])
    await ciclo(servicio)
    await crear_trabajo(db, bandejas=[{"ranura": "1", "tipo": "PLA", "color": ROJO, "tag": TAG}])
    spool.caido = True
    await ciclo(servicio)
    async with SessionLocal() as s:
        est = await s.get(EstadoSpoolman, 1)
        assert est.conectado is False and "No se alcanza" in est.detalle
    assert spool.usos == []
    spool.caido = False
    await ciclo(servicio)
    await ciclo(servicio)
    (c,) = await lineas(db)
    assert c.estado == "descontado" and spool.usos == [(7, 12.5)]


async def test_si_no_se_ve_la_respuesta_no_reenvia_sola(servicio, spool, db):
    spool.agregar(7, tags=[TAG])
    await ciclo(servicio)
    await crear_trabajo(db, bandejas=[{"ranura": "1", "tipo": "PLA", "color": ROJO, "tag": TAG}])
    spool.ambiguo = True
    await ciclo(servicio)
    (c,) = await lineas(db)
    assert c.estado == "revisar" and "Confirma en Spoolman" in c.detalle
    spool.ambiguo = False
    await ciclo(servicio)
    await ciclo(servicio)
    assert spool.usos == [] and (await lineas(db))[0].estado == "revisar"


async def test_una_linea_enviando_olvidada_pasa_a_revisar(servicio, spool, db):
    spool.agregar(7)
    await ciclo(servicio)
    t = await crear_trabajo(db)
    db.add(ConsumoFilamento(
        trabajo_id=t.id, orden=0, gramos_plan=5, gramos=5, spool_id=7, estado="enviando",
        actualizado_en=datetime.now(UTC) - timedelta(minutes=10),
    ))  # fmt: skip
    await db.commit()
    await ciclo(servicio)
    assert (await lineas(db))[0].estado == "revisar" and spool.usos == []


async def test_bobina_borrada_en_spoolman_vuelve_a_pedir_eleccion(servicio, spool, db):
    spool.agregar(7)
    await ciclo(servicio)
    t = await crear_trabajo(db)
    db.add(ConsumoFilamento(trabajo_id=t.id, orden=0, gramos_plan=5, gramos=5, spool_id=99,
                            estado="por_enviar"))  # fmt: skip
    await db.commit()
    await ciclo(servicio)
    (c,) = await lineas(db)
    assert c.estado == "sin_bobina" and c.spool_id is None and "ya no existe" in c.detalle


async def test_el_servicio_anota_la_bandeja_en_uso_durante_el_trabajo(spool, db):
    from tests.test_impresora_servicio import FalsoCliente, poner

    cli = FalsoCliente()
    s = Servicio(cli, spoolman_cliente=spool)
    poner(cli, "RUNNING", progreso=5)
    cli.estado["ams"] = {"tray_now": "1", "ams": [{"id": "0", "tray": [
        {"id": "0", "tray_type": "PLA", "tray_color": "0000FFFF", "tag_uid": "0" * 16},
        {"id": "1", "tray_type": "PLA", "tray_color": "FF0000FF", "tag_uid": TAG, "remain": 50},
    ]}]}  # fmt: skip
    await s._seguir_trabajos()
    cli.estado["ams"]["tray_now"] = "0"
    await s._seguir_trabajos()
    await s._seguir_trabajos()  # repetir no duplica
    db.expire_all()
    (t,) = (await db.execute(select(TrabajoImpresora))).scalars().all()
    assert t.bandejas == [
        {"ranura": "1", "tipo": "PLA", "color": "#ff0000", "tag": TAG},
        {"ranura": "0", "tipo": "PLA", "color": "#0000ff", "tag": None},
    ]


# ============================================ registro automático de bobinas Bambu con chip
def ams_con(cli, *trays, ahora="1"):
    cli.estado["ams"] = {"tray_now": ahora, "ams": [{"id": "0", "tray": list(trays)}]}


def bandeja_cruda(id_, tag, color="FF0000FF", tipo="PLA", marca="PLA Basic", remain=100):
    return {"id": id_, "tray_type": tipo, "tray_color": color, "tag_uid": tag, "remain": remain,
            "tray_sub_brands": marca, "tray_weight": "1000"}  # fmt: skip


async def autorregistrar(servicio):
    """Un ciclo con los chips ya vistos desde hace rato (si no, esperan unos segundos)."""
    for t in servicio._tags_vistos:
        servicio._tags_vistos[t] -= timedelta(minutes=1)
    await ciclo(servicio)


async def test_bobina_bambu_nueva_se_registra_sola_con_su_chip(spool):
    from tests.test_impresora_servicio import FalsoCliente, poner

    cli = FalsoCliente()
    poner(cli, "IDLE")
    ams_con(cli, bandeja_cruda("0", TAG), bandeja_cruda("1", "0" * 16, color="0000FFFF", marca=""))
    s = Servicio(cli, spoolman_cliente=spool)
    await ciclo(s)  # recién vista: espera a que el chip se vea estable
    assert spool.creadas == []
    await autorregistrar(s)
    (c,) = spool.creadas  # solo la del chip; la sin chip no se registra sola
    assert c["filamento"]["nombre"] == "PLA Basic" and c["filamento"]["color"] == "#ff0000"
    assert c["peso"] == 1000.0 and c["usado"] == 0.0 and c["ubicacion"] == "AMS · Ranura 1"
    assert "Bambu Lab" in spool.proveedores and spool.bobinas_[c["id"]].tags == (TAG,)
    for _ in range(3):  # el mismo chip nunca se registra dos veces
        await autorregistrar(s)
    assert len(spool.creadas) == 1


async def test_el_autoregistro_respeta_chips_ya_conocidos_y_archivados(spool):
    from tests.test_impresora_servicio import FalsoCliente, poner

    cli = FalsoCliente()
    poner(cli, "IDLE")
    spool.agregar(7, tags=[TAG])
    spool.archivadas["1111222233334444"] = 55
    ams_con(cli, bandeja_cruda("0", TAG), bandeja_cruda("1", "1111222233334444"))
    s = Servicio(cli, spoolman_cliente=spool)
    await ciclo(s)
    await autorregistrar(s)
    assert spool.creadas == []


async def test_el_autoregistro_se_puede_apagar(spool, monkeypatch):
    from tests.test_impresora_servicio import FalsoCliente, poner

    monkeypatch.setattr(settings, "spoolman_autocrear", False)
    cli = FalsoCliente()
    poner(cli, "IDLE")
    ams_con(cli, bandeja_cruda("0", TAG))
    s = Servicio(cli, spoolman_cliente=spool)
    await ciclo(s)
    await autorregistrar(s)
    assert spool.creadas == []


async def test_bobina_ya_gastada_se_registra_con_lo_que_queda(spool):
    from tests.test_impresora_servicio import FalsoCliente, poner

    cli = FalsoCliente()
    poner(cli, "IDLE")
    ams_con(cli, bandeja_cruda("0", TAG, remain=35))
    s = Servicio(cli, spoolman_cliente=spool)
    await ciclo(s)
    await autorregistrar(s)
    assert (
        spool.creadas[0]["usado"] == 650.0
        and spool.bobinas_[spool.creadas[0]["id"]].restante_g == 350.0
    )


async def test_un_fallo_al_registrar_reintenta_despues_sin_duplicar(spool, monkeypatch):
    from tests.test_impresora_servicio import FalsoCliente, poner

    cli = FalsoCliente()
    poner(cli, "IDLE")
    ams_con(cli, bandeja_cruda("0", TAG))
    s = Servicio(cli, spoolman_cliente=spool)
    await ciclo(s)
    original = spool.crear_bobina

    async def falla(*a, **k):
        raise ErrorSpoolman("Spoolman no respondió a tiempo (ReadTimeout).")

    monkeypatch.setattr(spool, "crear_bobina", falla)
    await autorregistrar(s)
    assert spool.creadas == []
    await autorregistrar(s)  # en espera: no insiste de inmediato
    s._tags_reintento.clear()
    monkeypatch.setattr(spool, "crear_bobina", original)
    await autorregistrar(s)
    assert len(spool.creadas) == 1


async def test_crear_desde_la_ranura_con_chip_sin_chip_y_con_lo_que_queda(admin, con_spoolman, db):
    await poner_ams(
        db,
        {**bandeja("0", tag=TAG, color=ROJO), "marca": "PLA Basic", "peso": 1000},
        bandeja("3", tipo="PETG", color=AZUL),
    )
    r = await admin.post("/api/spoolman/ranuras/0/crear", json={"precio": 59000})
    assert r.status_code == 201 and r.json()["tipo"] == "rfid"
    c = con_spoolman.creadas[0]
    assert (c["precio"], c["peso"], c["usado"]) == (59000.0, 1000.0, 0.0)
    assert con_spoolman.bobinas_[c["id"]].tags == (TAG,)
    # Ya está vinculada: no se crea otra.
    assert (await admin.post("/api/spoolman/ranuras/0/crear", json={})).status_code == 409

    r = await admin.post(
        "/api/spoolman/ranuras/3/crear", json={"peso_g": 1000, "restante_g": 420.5}
    )
    assert r.status_code == 201 and r.json()["tipo"] == "manual"
    c2 = con_spoolman.creadas[1]
    assert c2["usado"] == 579.5 and c2["filamento"]["proveedor_id"] is None
    assert c2["filamento"]["densidad"] == 1.27  # PETG
    fila = await db.get(RanuraBobina, "3")
    assert (fila.spool_id, fila.tipo, fila.color) == (c2["id"], "PETG", AZUL)
    assert (await admin.post("/api/spoolman/ranuras/3/crear", json={})).status_code == 409
    assert (await admin.post("/api/spoolman/ranuras/2/crear", json={})).status_code == 404
    assert (
        await admin.post("/api/spoolman/ranuras/3/crear", json={"peso_g": 0})
    ).status_code == 422


async def test_crear_no_deja_bobinas_huerfanas_si_el_chip_esta_en_uso(admin, con_spoolman, db):
    con_spoolman.archivadas[TAG] = 55  # el chip lo tiene una bobina archivada
    await poner_ams(db, bandeja("0", tag=TAG))
    r = await admin.post("/api/spoolman/ranuras/0/crear", json={})
    assert r.status_code == 409
    assert con_spoolman.bobinas_ == {}  # la bobina recién creada se borró


async def test_estado_informa_si_el_autoregistro_esta_activo(admin, con_spoolman):
    assert (await admin.get("/api/spoolman")).json()["autoregistro"] is True


# ============================================================================== API
async def test_estado_apagado_sin_url(admin, monkeypatch):
    monkeypatch.setattr(settings, "spoolman_url", "")
    r = await admin.get("/api/spoolman")
    assert r.status_code == 200 and r.json()["configurado"] is False
    assert (await admin.get("/api/spoolman/bobinas")).status_code == 409


async def test_estado_con_conexion(admin, con_spoolman, db):
    async with SessionLocal() as s:
        await consumo_mod.guardar_estado(s, conectado=True, version="0.27.1", detalle=None)
        await s.commit()
    d = (await admin.get("/api/spoolman")).json()
    assert d["configurado"] and d["conectado"] and d["version"] == "0.27.1"
    assert d["url_web"] == "http://10.6.0.6:7912" and d["por_resolver"] == 0


async def test_exige_sesion_y_cabecera(publico, admin, con_spoolman):
    assert (await publico.get("/api/spoolman")).status_code == 401
    r = await admin.put(
        "/api/spoolman/ranuras/0", json={"spool_id": 1}, headers={"X-Requested-With": ""}
    )
    assert r.status_code == 403


async def test_ranuras_muestran_la_bobina_asociada(admin, con_spoolman, db):
    con_spoolman.agregar(7, nombre="Bambu Lab · PLA Basic · Rojo", tags=[TAG]).agregar(
        4, nombre="Eryone PLA"
    )
    db.add(RanuraBobina(ranura="0", spool_id=4, tipo="PLA", color=AZUL))
    await db.commit()
    await poner_ams(
        db,
        bandeja("0", color=AZUL),  # manual vigente
        bandeja("1", color=ROJO, tag=TAG, en_uso=True),  # rfid vinculado
        bandeja("2", color=BLANCO, tag="1111222233334444"),  # rfid sin vincular
        bandeja("3", color=ROJO),  # manual sin vincular
    )
    r = {x["ranura"]: x for x in (await admin.get("/api/spoolman/ranuras")).json()}
    assert r["0"]["vinculo"] == {
        "tipo": "manual",
        "estado": "ok",
        "bobina": r["0"]["vinculo"]["bobina"],
    }
    assert r["0"]["vinculo"]["bobina"]["id"] == 4 and r["0"]["nombre"] == "Ranura 1"
    assert (
        r["1"]["vinculo"]["tipo"] == "rfid"
        and r["1"]["vinculo"]["estado"] == "ok"
        and r["1"]["en_uso"]
    )
    assert (
        r["2"]["vinculo"]["estado"] == "sin_vincular"
        and r["3"]["vinculo"]["estado"] == "sin_vincular"
    )
    # Si la ranura cambió de color desde que se vinculó, pide confirmar.
    await poner_ams(db, bandeja("0", color=ROJO))
    (x,) = (await admin.get("/api/spoolman/ranuras")).json()
    assert x["vinculo"]["estado"] == "desactualizado" and x["vinculo"]["bobina"]["id"] == 4


async def test_vincular_chip_rfid_lo_guarda_en_spoolman(admin, con_spoolman, db):
    con_spoolman.agregar(7)
    await poner_ams(db, bandeja("1", tag=TAG))
    r = await admin.put("/api/spoolman/ranuras/1", json={"spool_id": 7})
    assert r.status_code == 200 and r.json()["tipo"] == "rfid"
    assert con_spoolman.bobinas_[7].tags == (TAG,)
    assert (await db.execute(select(RanuraBobina))).first() is None  # nada local para RFID
    # Desvincular quita el chip de Spoolman.
    assert (await admin.put("/api/spoolman/ranuras/1", json={"spool_id": None})).status_code == 200
    assert con_spoolman.bobinas_[7].tags == ()


async def test_chip_ya_en_otra_bobina_pide_confirmar_para_moverlo(admin, con_spoolman, db):
    con_spoolman.agregar(7, tags=[TAG]).agregar(8)
    await poner_ams(db, bandeja("1", tag=TAG))
    r = await admin.put("/api/spoolman/ranuras/1", json={"spool_id": 8})
    assert r.status_code == 409 and "n.º 7" in r.json()["detail"]
    r = await admin.put("/api/spoolman/ranuras/1", json={"spool_id": 8, "mover": True})
    assert r.status_code == 200
    assert con_spoolman.bobinas_[8].tags == (TAG,) and con_spoolman.bobinas_[7].tags == ()


async def test_vincular_bobina_sin_chip_guarda_tipo_y_color_de_la_ranura(admin, con_spoolman, db):
    con_spoolman.agregar(4)
    await poner_ams(db, bandeja("0", color=AZUL), bandeja("3", color=BLANCO))
    assert (await admin.put("/api/spoolman/ranuras/0", json={"spool_id": 4})).status_code == 200
    fila = await db.get(RanuraBobina, "0")
    assert (fila.spool_id, fila.tipo, fila.color) == (4, "PLA", AZUL)
    # La misma bobina física no puede estar en dos ranuras: se mueve.
    await admin.put("/api/spoolman/ranuras/3", json={"spool_id": 4})
    db.expire_all()
    assert (
        await db.get(RanuraBobina, "0") is None and (await db.get(RanuraBobina, "3")).spool_id == 4
    )
    assert (await admin.put("/api/spoolman/ranuras/3", json={"spool_id": None})).status_code == 200


async def test_vincular_errores(admin, con_spoolman, db):
    await poner_ams(db, bandeja("0"))
    assert (
        await admin.put("/api/spoolman/ranuras/2", json={"spool_id": 1})
    ).status_code == 404  # vacía
    assert (
        await admin.put("/api/spoolman/ranuras/0", json={"spool_id": 99})
    ).status_code == 404  # no existe
    con_spoolman.caido = True
    assert (await admin.put("/api/spoolman/ranuras/0", json={"spool_id": 1})).status_code == 502
    assert (await admin.get("/api/spoolman/bobinas")).status_code == 502


async def test_consumos_pendientes_y_decidir(admin, con_spoolman, db):
    con_spoolman.agregar(4)
    t = await crear_trabajo(db, nombre="Soporte")
    db.add_all(
        [
            ConsumoFilamento(
                trabajo_id=t.id, orden=0, tipo="PLA", color=ROJO, gramos_plan=12.5, gramos=12.5,
                estado="sin_bobina", detalle="Elige la bobina",
            ),
            ConsumoFilamento(
                trabajo_id=t.id, orden=1, gramos_plan=3, gramos=3, spool_id=4, estado="descontado"
            ),
        ]
    )  # fmt: skip
    await db.commit()
    (pend,) = (await admin.get("/api/spoolman/consumos")).json()
    assert pend["trabajo"] == "Soporte" and pend["estado"] == "sin_bobina"
    assert len((await admin.get("/api/spoolman/consumos?pendientes=false")).json()) == 2
    assert (await admin.get("/api/spoolman")).json()["por_resolver"] == 1

    r = await admin.put(f"/api/spoolman/consumos/{pend['id']}", json={"accion": "asignar"})
    assert r.status_code == 422
    r = await admin.put(
        f"/api/spoolman/consumos/{pend['id']}", json={"accion": "asignar", "spool_id": 99}
    )
    assert r.status_code == 404
    r = await admin.put(
        f"/api/spoolman/consumos/{pend['id']}",
        json={"accion": "asignar", "spool_id": 4, "gramos": 10},
    )
    assert r.status_code == 200 and r.json()["estado"] == "por_enviar" and r.json()["gramos"] == 10

    # El servicio es quien lo envía.
    s = Servicio(cliente=None, spoolman_cliente=con_spoolman)
    await ciclo(s)
    assert con_spoolman.usos == [(4, 10.0)]
    r = await admin.put(f"/api/spoolman/consumos/{pend['id']}", json={"accion": "omitir"})
    assert r.status_code == 409  # ya descontado


async def test_revisar_confirmar_o_reintentar_y_omitir(admin, con_spoolman, db):
    t = await crear_trabajo(db)
    db.add_all(
        [
            ConsumoFilamento(
                trabajo_id=t.id, orden=i, gramos_plan=5, gramos=5, spool_id=4, estado="revisar"
            )
            for i in range(2)
        ]
    )
    await db.commit()
    a, b = [c["id"] for c in (await admin.get("/api/spoolman/consumos")).json()]
    r = await admin.put(f"/api/spoolman/consumos/{a}", json={"accion": "confirmar"})
    assert r.json()["estado"] == "descontado" and r.json()["descontado_en"]
    r = await admin.put(f"/api/spoolman/consumos/{b}", json={"accion": "reintentar"})
    assert r.json()["estado"] == "por_enviar"
    r = await admin.put(f"/api/spoolman/consumos/{b}", json={"accion": "confirmar"})
    assert r.status_code == 409  # solo desde «revisar»
    r = await admin.put(f"/api/spoolman/consumos/{b}", json={"accion": "omitir"})
    assert r.json()["estado"] == "omitido"
    assert (
        await admin.put(f"/api/spoolman/consumos/{a}", json={"accion": "borrar"})
    ).status_code == 422


async def test_la_lista_de_trabajos_trae_sus_consumos(admin, db):
    t = await crear_trabajo(db, nombre="Con consumo")
    db.add(ConsumoFilamento(trabajo_id=t.id, orden=0, tipo="PLA", color=ROJO, gramos_plan=12.5,
                            gramos=12.5, estado="descontado", spool_id=7))  # fmt: skip
    await db.commit()
    (tr,) = (await admin.get("/api/impresora/trabajos")).json()
    assert [(c["estado"], c["spool_id"], c["gramos"]) for c in tr["consumos"]] == [
        ("descontado", 7, 12.5)
    ]
    r = await admin.post(f"/api/impresora/trabajos/{tr['id']}/ignorar")
    assert r.status_code == 200 and len(r.json()["consumos"]) == 1


def test_el_modulo_de_la_api_existe():
    assert api_spoolman.router.prefix == "/spoolman"


# ============================================================ consumo estimado del historial
async def test_historial_sugiere_por_color_aplica_una_vez_y_no_cuenta_dos_veces(spool, db):
    from app.spoolman import historial

    spool.agregar(2, nombre="Sunlu · Vivid Rose", color="#e31c79", restante=1000.0)
    spool.agregar(3, nombre="Bambu · Pure", color=BLANCO, restante=1000.0)
    spool.agregar(4, nombre="Ya con consumo", color=AZUL, restante=400.0)  # 600 g gastados
    for g, c in ((10, "#c31679"), (5, "#c31679"), (7, BLANCO), (3, "#0000f0"), (2, "#123456")):
        await crear_trabajo(db, filamentos=[{"tipo": "PLA", "color": c, "gramos": g}])
    await crear_trabajo(  # cortado al 50 %: cuenta la mitad
        db, estado="interrumpido", progreso=50,
        filamentos=[{"tipo": "PLA", "color": "#c31679", "gramos": 20}],
    )  # fmt: skip

    grupos = await historial.calcular(db, await spool.bobinas())
    por = {g.clave: g for g in grupos}
    rosa = por["PLA#c31679"]
    assert (float(rosa.gramos), rosa.trabajos, rosa.sugerida.id) == (25.0, 3, 2)
    assert por["PLA#ffffff"].sugerida.id == 3 and por["PLA#0000f0"].sugerida.id == 4
    assert por["PLA#123456"].sugerida is None  # sin bobina parecida: no inventa

    # Por defecto se saltan las bobinas que ya tienen consumo registrado (para no contar doble).
    mapa = {g.clave: g.sugerida.id for g in grupos if g.sugerida}
    mapa.pop("PLA#0000f0")
    n, total = await historial.aplicar(db, grupos, mapa)
    await db.commit()
    assert (n, float(total)) == (4, 32.0)
    s = Servicio(cliente=None, spoolman_cliente=spool)
    await ciclo(s)
    assert sorted(spool.usos) == sorted([(2, 10.0), (2, 5.0), (2, 10.0), (3, 7.0)])
    assert {c.estado for c in await lineas(db)} == {"descontado"}

    # Repetir no vuelve a contar los trabajos que ya tienen descuento.
    grupos2 = await historial.calcular(db, await spool.bobinas())
    assert {g.clave for g in grupos2} == {"PLA#0000f0", "PLA#123456"}


# ============ adoptar bobinas existentes, memoria de chips y ubicaciones (no duplicar jamás)
TAG2 = "0E45AABBCCDD2233"
SIN_BOBINA = {"id": "1"}  # una ranura vacía: sin tipo


async def servicio_con(cli_ams, spool, *trays):
    from tests.test_impresora_servicio import FalsoCliente, poner

    cli = cli_ams if cli_ams is not None else FalsoCliente()
    poner(cli, "IDLE")
    ams_con(cli, *trays)
    s = Servicio(cli, spoolman_cliente=spool)
    await ciclo(s)  # recién vistos: esperan a que el chip se vea estable
    return cli, s


async def chips_recordados(db):
    from app.models import ChipBobina

    db.expire_all()
    return {c.uid: c.spool_id for c in (await db.execute(select(ChipBobina))).scalars()}


async def ciclo_ubicaciones(servicio):
    servicio._ubicaciones_proximo = datetime.min.replace(tzinfo=UTC)
    await ciclo(servicio)


def test_candidatas_a_adoptar_exige_proveedor_material_color_y_sin_chip():
    base = Bobina(
        id=1, nombre="x", material="PLA", color=ROJO, restante_g=1, inicial_g=1, precio=None,
        ubicacion=None, archivada=False, tags=(), proveedor="Bambu Lab",
    )  # fmt: skip
    b = {"tipo": "PLA", "color": ROJO}
    from app.spoolman.registro import candidatas_a_adoptar as cand

    assert cand([base], b) == [base]
    assert cand([Bobina(**{**base.__dict__, "tags": ("AA",)})], b) == []  # ya tiene chip
    assert cand([Bobina(**{**base.__dict__, "archivada": True})], b) == []
    assert cand([Bobina(**{**base.__dict__, "proveedor": "Sunlu"})], b) == []
    assert cand([Bobina(**{**base.__dict__, "color": AZUL})], b) == []
    assert cand([Bobina(**{**base.__dict__, "material": "PETG"})], b) == []
    assert cand([base], {"tipo": "PLA", "color": None}) == []


async def test_un_chip_nuevo_se_vincula_a_la_bobina_existente_en_vez_de_duplicarla(spool, db):
    spool.agregar(7, nombre="Bambu Lab · Basic Red", color=ROJO)  # creada a mano, sin chip
    cli, s = await servicio_con(None, spool, bandeja_cruda("0", TAG))
    await autorregistrar(s)
    assert spool.creadas == []  # no se creó otra
    assert spool.bobinas_[7].tags == (TAG,)
    assert (await chips_recordados(db)) == {TAG: 7}


async def test_un_chip_de_otro_color_o_proveedor_no_adopta_nada_y_crea(spool):
    spool.agregar(7, color=AZUL)  # otro color
    spool.agregar(8, proveedor="Sunlu")  # otro proveedor
    _, s = await servicio_con(None, spool, bandeja_cruda("0", TAG))
    await autorregistrar(s)
    assert len(spool.creadas) == 1 and spool.bobinas_[7].tags == () and spool.bobinas_[8].tags == ()


async def test_si_varias_bobinas_podrian_ser_no_adivina_ni_crea(spool, db, caplog):
    import logging

    caplog.set_level(logging.WARNING)
    spool.agregar(7).agregar(8)  # dos rojas sin chip: ¿cuál es?
    _, s = await servicio_con(None, spool, bandeja_cruda("0", TAG))
    await autorregistrar(s)
    assert spool.creadas == [] and spool.bobinas_[7].tags == () and spool.bobinas_[8].tags == ()
    assert "No adivino" in caplog.text
    assert await chips_recordados(db) == {}  # sigue pendiente de que la persona elija


async def test_con_varias_candidatas_gana_la_que_ya_figura_en_esa_ranura(spool):
    spool.agregar(7).agregar(8, ubicacion="AMS · Ranura 1")
    _, s = await servicio_con(None, spool, bandeja_cruda("0", TAG))
    await autorregistrar(s)
    assert spool.bobinas_[8].tags == (TAG,) and spool.bobinas_[7].tags == () and spool.creadas == []


async def test_quitar_y_volver_a_poner_el_rollo_no_duplica(spool, db):
    cli, s = await servicio_con(None, spool, bandeja_cruda("0", TAG))
    await autorregistrar(s)
    assert len(spool.creadas) == 1
    for _ in range(3):  # sale el rollo (ranura vacía) y vuelve a entrar, varias veces
        ams_con(cli, {"id": "0"}, bandeja_cruda("1", TAG2, color="0000FFFF"))
        await autorregistrar(s)
        ams_con(cli, bandeja_cruda("0", TAG))
        await ciclo(s)
        await autorregistrar(s)
    assert [c["ubicacion"] for c in spool.creadas].count("AMS · Ranura 1") == 1
    assert sum(1 for b in spool.bobinas_.values() if TAG in b.tags) == 1


async def test_si_se_borra_la_bobina_el_chip_ya_leido_no_se_vuelve_a_crear(spool, db, caplog):
    import logging

    caplog.set_level(logging.WARNING)
    cli, s = await servicio_con(None, spool, bandeja_cruda("0", TAG))
    await autorregistrar(s)
    (c,) = spool.creadas
    spool.bobinas_.pop(c["id"])  # la persona borra la bobina en Spoolman
    for _ in range(3):
        await autorregistrar(s)
    assert len(spool.creadas) == 1 and spool.bobinas_ == {}
    assert "ya se había registrado" in caplog.text
    # Aunque el servicio se reinicie: la memoria está en la base, no en el proceso.
    s2 = Servicio(cli, spoolman_cliente=spool)
    await ciclo(s2)
    await autorregistrar(s2)
    assert len(spool.creadas) == 1 and spool.bobinas_ == {}
    # Y desde el panel (crear a mano en la ranura) sigue pudiéndose recrear a propósito.
    from app.spoolman.registro import crear_desde_bandeja

    nueva = await crear_desde_bandeja(
        spool, {"tipo": "PLA", "color": ROJO, "tag": TAG, "marca": "PLA Basic"}
    )
    assert spool.bobinas_[nueva.id].tags == (TAG,)


async def test_los_chips_que_ya_tiene_spoolman_tambien_se_recuerdan(spool, db):
    spool.agregar(7, tags=[TAG]).agregar(9, tags=[TAG2])  # el 9 no está en el AMS
    cli, s = await servicio_con(None, spool, bandeja_cruda("0", TAG))
    await ciclo_ubicaciones(s)
    assert await chips_recordados(db) == {TAG: 7, TAG2: 9}
    spool.bobinas_.pop(9)  # se borra una bobina cuyo rollo luego se carga en el AMS
    ams_con(cli, bandeja_cruda("0", TAG), bandeja_cruda("1", TAG2, color="0000FFFF"))
    await ciclo(s)
    await autorregistrar(s)
    assert spool.creadas == []


async def test_las_ubicaciones_siguen_al_rollo_y_limpian_el_que_salio(spool):
    spool.agregar(7, tags=[TAG], ubicacion="AMS · Ranura 3")  # vieja, de cuando estaba en otra
    cli, s = await servicio_con(None, spool, bandeja_cruda("2", TAG))
    await ciclo_ubicaciones(s)  # la primera vez solo confirma que ve lo mismo
    assert spool.bobinas_[7].ubicacion == "AMS · Ranura 3"
    await ciclo_ubicaciones(s)
    assert spool.bobinas_[7].ubicacion == "AMS · Ranura 3"  # ya era correcta
    ams_con(cli, bandeja_cruda("0", TAG))  # el rollo se cambia a la ranura 1
    await ciclo_ubicaciones(s)
    assert spool.bobinas_[7].ubicacion == "AMS · Ranura 3"  # aún no: hay que verlo dos veces
    await ciclo_ubicaciones(s)
    assert spool.bobinas_[7].ubicacion == "AMS · Ranura 1"
    ams_con(cli, SIN_BOBINA, bandeja_cruda("2", TAG2, color="0000FFFF"))  # sale del AMS
    await ciclo_ubicaciones(s)
    await ciclo_ubicaciones(s)
    assert spool.bobinas_[7].ubicacion is None


async def test_las_ubicaciones_puestas_a_mano_no_se_tocan(spool):
    spool.agregar(7, tags=[TAG], ubicacion="Estante A")  # cargada, pero la persona la ubicó
    spool.agregar(8, ubicacion="Estante B")  # guardada
    _, s = await servicio_con(None, spool, bandeja_cruda("0", TAG))
    for _ in range(3):
        await ciclo_ubicaciones(s)
    assert spool.bobinas_[7].ubicacion == "Estante A" and spool.bobinas_[8].ubicacion == "Estante B"


async def test_sin_datos_del_ams_no_se_cambia_ninguna_ubicacion(spool):
    from tests.test_impresora_servicio import FalsoCliente

    spool.agregar(7, tags=[TAG], ubicacion="AMS · Ranura 2")
    cli = FalsoCliente()  # impresora sin informar el AMS (apagada, sin conexión…)
    cli.estado = {"gcode_state": "IDLE"}
    s = Servicio(cli, spoolman_cliente=spool)
    for _ in range(3):
        await ciclo_ubicaciones(s)
    assert spool.bobinas_[7].ubicacion == "AMS · Ranura 2"


async def test_una_bobina_sin_chip_vinculada_a_mano_tambien_tiene_su_ubicacion(spool, db):
    spool.agregar(5, color="#000000", tags=[])  # el negro sin chip
    db.add(RanuraBobina(ranura="2", spool_id=5, tipo="PLA", color="#000000"))
    await db.commit()
    _, s = await servicio_con(
        None,
        spool,
        bandeja_cruda("2", "0" * 16, color="000000FF", marca=""),  # sin chip
    )
    await ciclo_ubicaciones(s)
    await ciclo_ubicaciones(s)
    assert spool.bobinas_[5].ubicacion == "AMS · Ranura 3"


# ============================================== corregir rollos, repuestos y «¿alcanza?»
async def test_corregir_un_rollo_desde_el_panel(admin, con_spoolman):
    con_spoolman.agregar(7, restante=800.0, precio=60000.0)
    r = await admin.patch("/api/spoolman/bobinas/7", json={"restante_g": 612.5, "precio": 55000})
    assert r.status_code == 200, r.text
    assert (r.json()["restante_g"], r.json()["precio"]) == (612.5, 55000.0)
    assert con_spoolman.bobinas_[7].restante_g == 612.5
    # Solo cambia lo que se manda.
    r = await admin.patch("/api/spoolman/bobinas/7", json={"restante_g": 100})
    assert r.json()["precio"] == 55000.0 and r.json()["bajo"] is True


async def test_archivar_un_rollo_terminado_lo_saca_de_las_listas(admin, con_spoolman):
    con_spoolman.agregar(7).agregar(8)
    r = await admin.patch("/api/spoolman/bobinas/7", json={"archivar": True})
    assert r.status_code == 200, r.text
    assert [b["id"] for b in (await admin.get("/api/spoolman/bobinas")).json()] == [8]


async def test_corregir_un_rollo_valida_y_avisa(admin, con_spoolman):
    con_spoolman.agregar(7)
    assert (await admin.patch("/api/spoolman/bobinas/7", json={})).status_code == 422
    assert (await admin.patch("/api/spoolman/bobinas/7", json={"restante_g": -1})).status_code == 422
    assert (await admin.patch("/api/spoolman/bobinas/99", json={"restante_g": 5})).status_code == 404
    con_spoolman.caido = True
    assert (await admin.patch("/api/spoolman/bobinas/7", json={"restante_g": 5})).status_code == 502


async def test_corregir_un_rollo_exige_sesion(publico, con_spoolman):
    con_spoolman.agregar(7)
    r = await publico.patch("/api/spoolman/bobinas/7", json={"restante_g": 5})
    assert r.status_code in (401, 403)


async def test_repuestos_son_los_rollos_fuera_del_ams_con_los_bajos_primero(admin, con_spoolman, db):
    con_spoolman.agregar(7, tags=[TAG], restante=900)  # en la ranura 1 (chip)
    con_spoolman.agregar(8, ubicacion="AMS · Ranura 2", restante=700)  # el servicio lo ubicó allí
    con_spoolman.agregar(9, nombre="Repuesto gastado", restante=90)
    con_spoolman.agregar(10, nombre="Repuesto nuevo", restante=1000)
    con_spoolman.agregar(11, nombre="Sin peso", restante=None)
    await poner_ams(db, bandeja("1", tag=TAG))
    r = (await admin.get("/api/spoolman/repuestos")).json()
    assert r["umbral_g"] == 150
    assert [b["id"] for b in r["bobinas"]] == [9, 10, 11]
    assert [b["bajo"] for b in r["bobinas"]] == [True, False, False]


async def test_alcance_sin_trabajo_o_sin_gramos_no_opina(admin, con_spoolman, db):
    assert (await admin.get("/api/spoolman/alcance")).json() == {
        "trabajo": None, "leyendo": False, "lineas": [], "alerta": False,
    }  # fmt: skip
    t = await crear_trabajo(db, nombre="Recién empezado", estado="en_curso")
    t.filamentos = None  # el archivo aún no se leyó
    await db.commit()
    r = (await admin.get("/api/spoolman/alcance")).json()
    assert r["trabajo"] == "Recién empezado" and r["leyendo"] is True and r["lineas"] == []


async def test_alcance_avisa_si_el_rollo_no_alcanza(admin, con_spoolman, db):
    con_spoolman.agregar(7, tags=[TAG], restante=80.0).agregar(8, restante=500.0)
    db.add(RanuraBobina(ranura="2", spool_id=8, tipo="PLA", color=AZUL))
    await db.commit()
    await poner_ams(db, bandeja("1", color=ROJO, tag=TAG), bandeja("2", color=AZUL))
    await crear_trabajo(
        db, nombre="Maceta", estado="en_curso",
        filamentos=[{"tipo": "PLA", "color": ROJO, "gramos": 100.0},
                    {"tipo": "PLA", "color": AZUL, "gramos": 40.0}],
    )  # fmt: skip
    r = (await admin.get("/api/spoolman/alcance")).json()
    assert r["alerta"] is True
    rojo, azul = r["lineas"]
    assert (rojo["estado"], rojo["ranura"], rojo["restante_g"]) == ("no_alcanza", "1", 80.0)
    assert rojo["gramos"] == 100.0 and rojo["ranura_nombre"] == "Ranura 2"
    assert azul["estado"] == "alcanza" and azul["ranura"] == "2"


async def test_alcance_distingue_justo_sin_bobina_y_dudoso(admin, con_spoolman, db):
    con_spoolman.agregar(7, tags=[TAG], restante=105.0)
    await poner_ams(db, bandeja("1", color=ROJO, tag=TAG), bandeja("2", color=AZUL, tag="1111222233334444"))
    await crear_trabajo(db, estado="en_curso", filamentos=[{"tipo": "PLA", "color": ROJO, "gramos": 100.0}])
    (linea,) = (await admin.get("/api/spoolman/alcance")).json()["lineas"]
    assert linea["estado"] == "justo"  # sobran 5 g: menos del margen

    # La ranura azul tiene chip pero aún no está en Spoolman: no se sabe cuánto queda.
    await db.execute(text("DELETE FROM trabajos_impresora"))
    await db.commit()
    await crear_trabajo(db, estado="en_curso", filamentos=[{"tipo": "PLA", "color": AZUL, "gramos": 30.0}])
    (linea,) = (await admin.get("/api/spoolman/alcance")).json()["lineas"]
    assert linea["estado"] == "sin_bobina" and linea["ranura"] == "2"

    # Dos ranuras igual de parecidas: no adivina, y no da alerta.
    await db.execute(text("DELETE FROM trabajos_impresora"))
    await db.commit()
    await poner_ams(db, bandeja("1", color=ROJO), bandeja("2", color=ROJO))
    await crear_trabajo(db, estado="en_curso", filamentos=[{"tipo": "PLA", "color": ROJO, "gramos": 30.0}])
    r = (await admin.get("/api/spoolman/alcance")).json()
    assert r["lineas"][0]["estado"] == "dudoso" and r["alerta"] is False
