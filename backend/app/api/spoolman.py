"""Spoolman: estado, bobinas, qué bobina hay en cada ranura del AMS y los descuentos de filamento.

El backend lee y vincula, pero NO descuenta: el descuento lo hace solo el servicio `impresora`
(así no se manda dos veces). Aquí la persona decide de qué bobina salió un consumo y el servicio lo
envía en unos segundos."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select

from app.config import settings
from app.core import auditoria
from app.core.deps import DB, PROTEGIDO, Admin
from app.core.tokens import ahora
from app.models import (
    ConsumoFilamento,
    EstadoImpresora,
    EstadoSpoolman,
    RanuraBobina,
    TrabajoImpresora,
)
from app.schemas.spoolman import (
    BobinaOut,
    AlcanceLineaOut,
    AlcanceOut,
    ConsumoAccionIn,
    ConsumoOut,
    CrearBobinaIn,
    EditarBobinaIn,
    EstadoSpoolmanOut,
    RanuraOut,
    RepuestosOut,
    VincularIn,
    VinculoOut,
)
from app.spoolman import asignacion
from app.spoolman.cliente import (
    Bobina,
    ClienteSpoolman,
    ErrorSpoolman,
    NoExiste,
    TagEnUso,
)
from app.spoolman.consumo import titulo_ranura
from app.spoolman.dependencia import cliente_spoolman
from app.spoolman.registro import PREFIJO_UBICACION, crear_desde_bandeja
from app.spoolman.salida import consumo_out

router = APIRouter(prefix="/spoolman", tags=["spoolman"], dependencies=PROTEGIDO)

Cliente = Annotated[ClienteSpoolman, Depends(cliente_spoolman)]
LATIDO_MAX_S = 40
POR_RESOLVER = ("sin_bobina", "revisar")
# Por debajo de esto un rollo «queda poco»; y un trabajo «va justo» si le sobran menos gramos que esto
# (los gramos del .3mf son estimados del slicer y el peso de Spoolman no es una medición exacta).
BAJO_G = 150
JUSTO_G = 15


def _bobina_out(b: Bobina) -> BobinaOut:
    return BobinaOut(
        id=b.id, nombre=b.nombre, material=b.material, color=b.color,
        restante_g=b.restante_g, inicial_g=b.inicial_g, ubicacion=b.ubicacion, precio=b.precio,
        bajo=b.restante_g is not None and b.restante_g < BAJO_G,
    )  # fmt: skip


async def _llamar(coro):
    """Un fallo de Spoolman llega al panel como un aviso claro, no como un error 500."""
    try:
        return await coro
    except TagEnUso:
        raise  # lo decide quien llama (es un 409 con su propio mensaje)
    except NoExiste as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None
    except ErrorSpoolman as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from None


# --------------------------------------------------------------------------- estado
@router.get("", response_model=EstadoSpoolmanOut)
async def estado(db: DB) -> EstadoSpoolmanOut:
    if not settings.spoolman_url:
        return EstadoSpoolmanOut(configurado=False)
    fila = await db.get(EstadoSpoolman, 1)
    por_resolver = (
        await db.execute(
            select(func.count())
            .select_from(ConsumoFilamento)
            .where(ConsumoFilamento.estado.in_(POR_RESOLVER))
        )
    ).scalar_one()
    # El servicio escribe cada pocos segundos: si el dato es viejo, no está corriendo.
    vivo = fila is not None and (ahora() - fila.actualizado_en).total_seconds() < LATIDO_MAX_S
    return EstadoSpoolmanOut(
        configurado=True,
        conectado=bool(vivo and fila and fila.conectado),
        version=fila.version if fila else None,
        ultimo_ok_en=fila.ultimo_ok_en if fila else None,
        detalle=(
            fila.detalle if vivo and fila else "El servicio de la impresora no está respondiendo."
        ),
        url_web=settings.spoolman_web or None,
        por_resolver=por_resolver,
        autoregistro=settings.spoolman_autocrear,
    )


@router.get("/bobinas", response_model=list[BobinaOut])
async def bobinas(cliente: Cliente) -> list[BobinaOut]:
    return [_bobina_out(b) for b in await _llamar(cliente.bobinas())]


@router.patch("/bobinas/{spool_id}", response_model=BobinaOut)
async def editar_bobina(
    spool_id: int, datos: EditarBobinaIn, db: DB, cliente: Cliente, usuario: Admin
) -> BobinaOut:
    """Corrige un rollo sin entrar a Spoolman: cuánto queda (pesado o estimado), su precio, o lo
    archiva cuando se terminó. Solo cambia lo que se manda."""
    if datos.restante_g is None and datos.precio is None and datos.archivar is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No hay nada que cambiar.")
    b = await _llamar(
        cliente.editar(
            spool_id,
            restante=float(datos.restante_g) if datos.restante_g is not None else None,
            precio=float(datos.precio) if datos.precio is not None else None,
            archivada=datos.archivar,
        )
    )
    auditoria.registrar(
        db, "spoolman_bobina_editada", usuario_id=usuario.id,
        detalle={
            "spool_id": spool_id,
            "restante_g": float(datos.restante_g) if datos.restante_g is not None else None,
            "precio": float(datos.precio) if datos.precio is not None else None,
            "archivar": datos.archivar,
        },
    )  # fmt: skip
    await db.commit()
    return _bobina_out(b)


async def _bobinas_en_el_ams(db, bandejas: list[dict], todas: list[Bobina]) -> set[int]:
    """Números de las bobinas que están puestas ahora en alguna ranura."""
    spools = {b.id: b for b in todas}
    por_tag = {t: b for b in todas for t in b.tags}
    filas = {r.ranura: r for r in (await db.execute(select(RanuraBobina))).scalars()}
    vinculos = (_vinculo(b, spools, por_tag, filas.get(b["id"])) for b in bandejas)
    return {v.bobina.id for v in vinculos if v.bobina is not None}


@router.get("/repuestos", response_model=RepuestosOut)
async def repuestos(db: DB, cliente: Cliente) -> RepuestosOut:
    """Los rollos que no están en el AMS (los de repuesto), con los más bajos primero."""
    todas = await _llamar(cliente.bobinas())
    en_ams = await _bobinas_en_el_ams(db, await _bandejas_actuales(db), todas)
    sueltas = [
        b for b in todas
        if b.id not in en_ams and not (b.ubicacion or "").startswith(PREFIJO_UBICACION)
    ]  # fmt: skip
    # Sin peso conocido al final: no se sabe si queda poco.
    sueltas.sort(key=lambda b: (b.restante_g is None, b.restante_g or 0, b.nombre))
    return RepuestosOut(umbral_g=BAJO_G, bobinas=[_bobina_out(b) for b in sueltas])


@router.get("/alcance", response_model=AlcanceOut)
async def alcance(db: DB, cliente: Cliente) -> AlcanceOut:
    """¿Alcanza el filamento de cada ranura para el trabajo que se está imprimiendo?

    Compara los gramos de cada filamento del .3mf con lo que queda en la bobina de la ranura que
    le corresponde por tipo y color. Spoolman descuenta al terminar, así que lo que queda allí es
    lo de antes del trabajo: por eso se compara contra los gramos completos. Con duda, no opina."""
    trabajo = (
        await db.execute(
            select(TrabajoImpresora)
            .where(TrabajoImpresora.estado == "en_curso")
            .order_by(TrabajoImpresora.inicio_en.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if trabajo is None:
        return AlcanceOut()
    filamentos = [f for f in (trabajo.filamentos or []) if float(f.get("gramos") or 0) > 0]
    if not filamentos:
        return AlcanceOut(trabajo=trabajo.nombre, leyendo=True)

    bandejas = await _bandejas_actuales(db)
    todas = await _llamar(cliente.bobinas())
    spools = {b.id: b for b in todas}
    por_tag = {t: b for b in todas for t in b.tags}
    filas = {r.ranura: r for r in (await db.execute(select(RanuraBobina))).scalars()}

    lineas: list[AlcanceLineaOut] = []
    for f, emp in zip(filamentos, asignacion.emparejar(filamentos, bandejas), strict=True):
        gramos = float(f["gramos"])
        base = {"tipo": f.get("tipo"), "color": f.get("color"), "gramos": gramos}
        if emp.bandeja is None:
            lineas.append(AlcanceLineaOut(**base, estado="dudoso"))
            continue
        b = emp.bandeja
        bobina = _vinculo(b, spools, por_tag, filas.get(b["id"])).bobina
        donde = {"ranura": b["id"], "ranura_nombre": titulo_ranura(b["id"])}
        if bobina is None:
            lineas.append(AlcanceLineaOut(**base, **donde, estado="sin_bobina"))
        elif bobina.restante_g is None:
            lineas.append(AlcanceLineaOut(**base, **donde, bobina=bobina.nombre, estado="sin_peso"))
        else:
            sobra = bobina.restante_g - gramos
            estado = "no_alcanza" if sobra < 0 else "justo" if sobra < JUSTO_G else "alcanza"
            lineas.append(
                AlcanceLineaOut(
                    **base, **donde, bobina=bobina.nombre, restante_g=bobina.restante_g,
                    estado=estado,
                )
            )  # fmt: skip
    return AlcanceOut(
        trabajo=trabajo.nombre, lineas=lineas, alerta=any(x.estado == "no_alcanza" for x in lineas)
    )


# --------------------------------------------------------------------------- ranuras
async def _bandejas_actuales(db) -> list[dict]:
    fila = await db.get(EstadoImpresora, 1)
    if (
        fila is None
        or not fila.datos
        or (ahora() - fila.actualizado_en).total_seconds() > LATIDO_MAX_S
    ):
        return []
    d = fila.datos
    return [b for b in [*(d.get("ams") or []), d.get("externa")] if b and not b.get("vacia")]


def _vinculo(b: dict, spools: dict[int, Bobina], por_tag: dict[str, Bobina], fila) -> VinculoOut:
    if b.get("tag"):
        s = por_tag.get(str(b["tag"]).upper())
        return VinculoOut(
            tipo="rfid",
            estado="ok" if s else "sin_vincular",
            bobina=_bobina_out(s) if s else None,
        )
    s = spools.get(fila.spool_id) if fila is not None else None
    if s is None:
        return VinculoOut(tipo="manual", estado="sin_vincular")
    vigente = asignacion.misma_bobina(fila.tipo, fila.color, b.get("tipo"), b.get("color"))
    return VinculoOut(
        tipo="manual", estado="ok" if vigente else "desactualizado", bobina=_bobina_out(s)
    )


@router.get("/ranuras", response_model=list[RanuraOut])
async def ranuras(db: DB, cliente: Cliente) -> list[RanuraOut]:
    """Cada ranura con filamento y la bobina de Spoolman que se le ha asociado."""
    bandejas = await _bandejas_actuales(db)
    if not bandejas:
        return []
    todas = await _llamar(cliente.bobinas())
    spools = {b.id: b for b in todas}
    por_tag = {t: b for b in todas for t in b.tags}
    filas = {r.ranura: r for r in (await db.execute(select(RanuraBobina))).scalars()}
    return [
        RanuraOut(
            ranura=b["id"],
            nombre=titulo_ranura(b["id"]),
            tipo=b.get("tipo"),
            marca=b.get("marca"),
            color=b.get("color"),
            en_uso=bool(b.get("en_uso")),
            vinculo=_vinculo(b, spools, por_tag, filas.get(b["id"])),
        )  # fmt: skip
        for b in bandejas
    ]


@router.put("/ranuras/{ranura}", response_model=VinculoOut)
async def vincular(
    ranura: str, datos: VincularIn, db: DB, cliente: Cliente, usuario: Admin
) -> VinculoOut:
    """Asocia (o quita) la bobina de una ranura. Bobina Bambu con chip: el UID del chip se vincula
    DENTRO de Spoolman (así se reconoce en cualquier ranura y en cualquier herramienta). Sin chip:
    se guarda para esa ranura, con el tipo y color que tiene ahora."""
    bandeja = next((b for b in await _bandejas_actuales(db) if b["id"] == ranura), None)
    if bandeja is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Esa ranura está vacía o la impresora no la informa ahora."
        )
    nueva = None
    if datos.spool_id is not None:
        nueva = await _llamar(cliente.bobina(datos.spool_id))
    tag = bandeja.get("tag")

    if tag:
        todas = await _llamar(cliente.bobinas())
        titular = next((b for b in todas if str(tag).upper() in b.tags), None)
        if nueva is None:  # desvincular
            if titular is not None:
                await _llamar(cliente.desvincular_tag(titular.id, tag))
        elif titular is None or titular.id != nueva.id:
            if titular is not None and not datos.mover:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    f"El chip de esta bobina ya está en «{titular.nombre}» (n.º {titular.id}) de "
                    "Spoolman. Confirma para moverlo a la bobina elegida.",
                )
            if titular is not None:
                await _llamar(cliente.desvincular_tag(titular.id, tag))
            try:
                await _llamar(cliente.vincular_tag(nueva.id, tag))
            except TagEnUso:  # alguien lo vinculó justo ahora
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "El chip ya está vinculado a otra bobina."
                ) from None
        resultado = VinculoOut(
            tipo="rfid", estado="ok" if nueva else "sin_vincular",
            bobina=_bobina_out(nueva) if nueva else None,
        )  # fmt: skip
    else:
        if nueva is None:
            await db.execute(delete(RanuraBobina).where(RanuraBobina.ranura == ranura))
        else:
            # Una bobina física solo está en una ranura a la vez.
            await db.execute(
                delete(RanuraBobina).where(
                    RanuraBobina.spool_id == nueva.id, RanuraBobina.ranura != ranura
                )
            )
            fila = await db.get(RanuraBobina, ranura)
            if fila is None:
                fila = RanuraBobina(ranura=ranura)
                db.add(fila)
            fila.spool_id, fila.tipo, fila.color = (
                nueva.id,
                bandeja.get("tipo"),
                bandeja.get("color"),
            )
            fila.vinculada_en = ahora()
        resultado = VinculoOut(
            tipo="manual", estado="ok" if nueva else "sin_vincular",
            bobina=_bobina_out(nueva) if nueva else None,
        )  # fmt: skip
    auditoria.registrar(
        db, "spoolman_vinculo", usuario_id=usuario.id,
        detalle={"ranura": ranura, "spool_id": datos.spool_id, "rfid": bool(tag)},
    )  # fmt: skip
    await db.commit()
    return resultado


@router.post(
    "/ranuras/{ranura}/crear", response_model=VinculoOut, status_code=status.HTTP_201_CREATED
)
async def crear_desde_ranura(
    ranura: str, datos: CrearBobinaIn, db: DB, cliente: Cliente, usuario: Admin
) -> VinculoOut:
    """Crea en Spoolman la bobina que está en la ranura (con lo que informa la impresora: marca,
    material y color) y la deja asociada. Así no hace falta registrarla a mano en Spoolman."""
    bandeja = next((b for b in await _bandejas_actuales(db) if b["id"] == ranura), None)
    if bandeja is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Esa ranura está vacía o la impresora no la informa ahora."
        )
    tag = bandeja.get("tag")
    todas = await _llamar(cliente.bobinas())
    if tag and any(str(tag).upper() in b.tags for b in todas):
        raise HTTPException(status.HTTP_409_CONFLICT, "El chip de esta bobina ya está en Spoolman.")
    fila = await db.get(RanuraBobina, ranura)
    if not tag and fila is not None and any(b.id == fila.spool_id for b in todas):
        vigente = asignacion.misma_bobina(
            fila.tipo, fila.color, bandeja.get("tipo"), bandeja.get("color")
        )
        if vigente:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Esa ranura ya tiene una bobina asociada."
            )

    try:
        nueva = await _llamar(
            crear_desde_bandeja(
                cliente, bandeja, peso=float(datos.peso_g),
                precio=float(datos.precio) if datos.precio is not None else None,
                restante=float(datos.restante_g) if datos.restante_g is not None else None,
                ubicacion=f"AMS · {titulo_ranura(ranura)}",
            )
        )  # fmt: skip
    except TagEnUso:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "El chip de esta bobina ya está vinculado a otra bobina."
        ) from None
    if not tag:
        await db.execute(delete(RanuraBobina).where(RanuraBobina.spool_id == nueva.id))
        if fila is None:
            fila = RanuraBobina(ranura=ranura)
            db.add(fila)
        fila.spool_id, fila.tipo, fila.color = nueva.id, bandeja.get("tipo"), bandeja.get("color")
        fila.vinculada_en = ahora()
    auditoria.registrar(
        db, "spoolman_bobina_creada", usuario_id=usuario.id,
        detalle={"ranura": ranura, "spool_id": nueva.id, "rfid": bool(tag)},
    )  # fmt: skip
    await db.commit()
    return VinculoOut(tipo="rfid" if tag else "manual", estado="ok", bobina=_bobina_out(nueva))


# ---------------------------------------------------------------------------- consumos
@router.get("/consumos", response_model=list[ConsumoOut])
async def consumos(
    db: DB,
    pendientes: bool = True,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ConsumoOut]:
    """`pendientes`: los que esperan una decisión (sin bobina o por revisar). Si no, los últimos."""
    q = select(ConsumoFilamento, TrabajoImpresora).join(
        TrabajoImpresora, TrabajoImpresora.id == ConsumoFilamento.trabajo_id
    )
    if pendientes:
        q = q.where(ConsumoFilamento.estado.in_(POR_RESOLVER))
    q = q.order_by(func.coalesce(TrabajoImpresora.fin_en, TrabajoImpresora.inicio_en).desc()).limit(
        limite
    )
    return [consumo_out(c, t) for c, t in (await db.execute(q)).all()]


@router.put("/consumos/{consumo_id}", response_model=ConsumoOut)
async def decidir_consumo(
    consumo_id: UUID, datos: ConsumoAccionIn, db: DB, cliente: Cliente, usuario: Admin
) -> ConsumoOut:
    c = (
        await db.execute(
            select(ConsumoFilamento).where(ConsumoFilamento.id == consumo_id).with_for_update()
        )
    ).scalar_one_or_none()
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese descuento no existe.")
    if c.estado in ("enviando", "descontado"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ese descuento ya se envió a Spoolman." if c.estado == "descontado"
            else "Ese descuento se está enviando; espera unos segundos.",
        )  # fmt: skip

    if datos.accion == "asignar":
        if datos.spool_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Elige una bobina.")
        await _llamar(cliente.bobina(datos.spool_id))
        c.spool_id = datos.spool_id
        if datos.gramos is not None:
            c.gramos = datos.gramos
        c.estado, c.detalle, c.intentos = ("por_enviar" if c.gramos > 0 else "omitido"), None, 0
    elif datos.accion == "omitir":
        c.estado, c.detalle = "omitido", "Omitido: no se descuenta de Spoolman."
    elif datos.accion in ("reintentar", "confirmar"):
        if c.estado != "revisar":
            raise HTTPException(status.HTTP_409_CONFLICT, "Ese descuento no está por revisar.")
        if datos.accion == "reintentar":
            c.estado, c.detalle, c.intentos = "por_enviar", None, 0
        else:
            c.estado, c.detalle, c.descontado_en = "descontado", None, ahora()
    auditoria.registrar(
        db, f"spoolman_consumo_{datos.accion}", usuario_id=usuario.id,
        detalle={"consumo": str(c.id), "spool_id": c.spool_id, "gramos": float(c.gramos)},
    )  # fmt: skip
    t = await db.get(TrabajoImpresora, c.trabajo_id)
    await db.commit()
    return consumo_out(c, t)
