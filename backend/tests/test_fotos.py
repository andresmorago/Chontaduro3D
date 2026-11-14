"""HEIC, encuadre de la foto (zoom y posición) y foto opcional por color."""

import io
from pathlib import Path

from PIL import Image
from pillow_heif import register_heif_opener

from app.config import settings
from tests.conftest import crear_articulo

register_heif_opener()
ROJO = {"nombre": "Rojo", "hex": "#dc2626"}
AZUL = {"nombre": "Azul", "hex": "#2563eb"}


def foto(formato="PNG", ancho=60, alto=40, color=(200, 80, 40)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (ancho, alto), color).save(b, formato)
    return b.getvalue()


def entrada(c: dict, **extra) -> dict:
    """Un color tal como lo manda la interfaz (solo campos de entrada)."""
    return {"id": c["id"], "nombre": c["nombre"], "hex": c["hex"], **extra}


def archivos_en_disco() -> set[str]:
    return {p.name for p in Path(settings.media_dir).glob("*.webp")}


async def subir(c, ruta, datos, nombre="f.png", tipo="image/png"):
    return await c.put(ruta, files={"archivo": (nombre, datos, tipo)})


# ------------------------------------------------------------------------------- HEIC
async def test_heic_se_convierte_a_webp(admin, publico):
    a = await crear_articulo(admin)
    heic = foto("HEIF", 800, 600)
    assert heic[4:8] == b"ftyp"  # es un contenedor HEIF de verdad
    r = await subir(admin, f"/api/articulos/{a['id']}/imagen", heic, "IMG_0001.HEIC", "image/heic")
    assert r.status_code == 200, r.text
    url = r.json()["imagen_url"]
    img = await publico.get(url)
    assert img.headers["content-type"] == "image/webp"
    with Image.open(io.BytesIO(img.content)) as im:
        assert im.format == "WEBP" and im.size == (800, 600)


async def test_heic_sin_extension_tambien_vale_y_basura_se_rechaza(admin):
    a = await crear_articulo(admin)
    ruta = f"/api/articulos/{a['id']}/imagen"
    assert (
        await subir(admin, ruta, foto("HEIF"), "foto", "application/octet-stream")
    ).status_code == 200
    r = await subir(admin, ruta, b"ftypheic" + b"\x00" * 50, "falsa.heic", "image/heic")
    assert r.status_code == 422 and "HEIC" in r.json()["detail"]


async def test_se_conserva_resolucion_para_hacer_zoom(admin, publico):
    a = await crear_articulo(admin)
    r = await subir(admin, f"/api/articulos/{a['id']}/imagen", foto("PNG", 4000, 3000))
    img = await publico.get(r.json()["imagen_url"])
    with Image.open(io.BytesIO(img.content)) as im:
        assert max(im.size) == 2000


# ---------------------------------------------------------------------------- encuadre
async def test_encuadre_por_defecto_y_se_guarda(admin, publico):
    a = await crear_articulo(admin)
    assert (a["foto_x"], a["foto_y"], a["foto_zoom"]) == (50, 50, 1)
    r = await admin.patch(f"/api/articulos/{a['id']}",
                          json={"foto_x": 20.5, "foto_y": 80, "foto_zoom": 2.5})  # fmt: skip
    assert (r.json()["foto_x"], r.json()["foto_y"], r.json()["foto_zoom"]) == (20.5, 80, 2.5)
    cat = (await publico.get("/api/publico/articulos")).json()["articulos"][0]
    assert (cat["foto_x"], cat["foto_y"], cat["foto_zoom"]) == (20.5, 80, 2.5)


async def test_encuadre_al_crear_y_validaciones(admin):
    a = await crear_articulo(admin, foto_x=10, foto_y=90, foto_zoom=3)
    assert (a["foto_x"], a["foto_y"], a["foto_zoom"]) == (10, 90, 3)
    for malo in ({"foto_zoom": 0.5}, {"foto_zoom": 5}, {"foto_x": -1}, {"foto_y": 101},
                 {"foto_zoom": None}):  # fmt: skip
        assert (await admin.patch(f"/api/articulos/{a['id']}", json=malo)).status_code == 422, malo
    # Un cambio de encuadre no toca lo demás.
    r = await admin.patch(f"/api/articulos/{a['id']}", json={"foto_zoom": 1.5})
    assert r.json()["foto_x"] == 10 and r.json()["nombre"] == "Llavero"


# ------------------------------------------------------------------------ fotos por color
async def test_foto_por_color_es_opcional_y_se_ve_en_el_catalogo(admin, publico):
    a = await crear_articulo(admin, colores=[ROJO, AZUL])
    rojo = a["colores"][0]
    assert rojo["imagen_url"] is None and "id" in rojo
    r = await subir(admin, f"/api/articulos/{a['id']}/colores/{rojo['id']}/imagen", foto())
    assert r.status_code == 200
    cat = (await publico.get("/api/publico/articulos")).json()["articulos"][0]
    por_nombre = {c["nombre"]: c for c in cat["colores"]}
    assert (
        por_nombre["Rojo"]["imagen_url"].endswith(".webp")
        and por_nombre["Azul"]["imagen_url"] is None
    )
    assert (await publico.get(por_nombre["Rojo"]["imagen_url"])).status_code == 200


async def test_foto_de_color_acepta_heic_y_reemplazar_borra_la_anterior(admin):
    a = await crear_articulo(admin, colores=[ROJO])
    ruta = f"/api/articulos/{a['id']}/colores/{a['colores'][0]['id']}/imagen"
    u1 = (await subir(admin, ruta, foto("HEIF"), "a.heic", "image/heic")).json()["colores"][0][
        "imagen_url"
    ]
    u2 = (await subir(admin, ruta, foto())).json()["colores"][0]["imagen_url"]
    assert u1 != u2 and Path(settings.media_dir, u1.rsplit("/", 1)[1]).exists() is False


async def test_quitar_foto_de_color(admin):
    a = await crear_articulo(admin, colores=[ROJO])
    ruta = f"/api/articulos/{a['id']}/colores/{a['colores'][0]['id']}/imagen"
    await subir(admin, ruta, foto())
    antes = archivos_en_disco()
    r = await admin.delete(ruta)
    assert (
        r.json()["colores"][0]["imagen_url"] is None and len(archivos_en_disco()) == len(antes) - 1
    )


async def test_color_ajeno_o_inexistente_da_404(admin):
    a = await crear_articulo(admin, colores=[ROJO])
    b = await crear_articulo(admin, nombre="Otro", colores=[AZUL])
    idb = b["colores"][0]["id"]
    for cid in (idb, "00000000-0000-0000-0000-000000000000"):
        r = await subir(admin, f"/api/articulos/{a['id']}/colores/{cid}/imagen", foto())
        assert r.status_code == 404


async def test_editar_colores_con_id_conserva_la_foto(admin):
    a = await crear_articulo(admin, colores=[ROJO, AZUL])
    rojo = a["colores"][0]
    await subir(admin, f"/api/articulos/{a['id']}/colores/{rojo['id']}/imagen", foto())
    # Renombrar, reordenar, cambiar encuadre y agregar uno nuevo: el rojo sigue con su foto e id.
    r = await admin.patch(f"/api/articulos/{a['id']}", json={"colores": [
        {"nombre": "Verde", "hex": "#16a34a"},
        {"id": rojo["id"], "nombre": "Rojo vivo", "hex": "#ff0000", "foto_zoom": 2},
    ]})  # fmt: skip
    cs = r.json()["colores"]
    assert [c["nombre"] for c in cs] == ["Verde", "Rojo vivo"]
    assert cs[1]["id"] == rojo["id"] and cs[1]["imagen_url"] and cs[1]["foto_zoom"] == 2
    assert cs[0]["id"] not in (rojo["id"], a["colores"][1]["id"])  # el nuevo tiene su propio id


async def test_intercambiar_nombres_de_colores_no_choca(admin):
    a = await crear_articulo(admin, colores=[ROJO, AZUL])
    r_id, a_id = a["colores"][0]["id"], a["colores"][1]["id"]
    r = await admin.patch(f"/api/articulos/{a['id']}", json={"colores": [
        {"id": r_id, "nombre": "Azul", "hex": "#2563eb"},
        {"id": a_id, "nombre": "Rojo", "hex": "#dc2626"},
    ]})  # fmt: skip
    assert r.status_code == 200 and [c["nombre"] for c in r.json()["colores"]] == ["Azul", "Rojo"]


async def test_quitar_un_color_borra_su_foto_del_disco(admin):
    a = await crear_articulo(admin, colores=[ROJO, AZUL])
    rojo = a["colores"][0]
    await subir(admin, f"/api/articulos/{a['id']}/colores/{rojo['id']}/imagen", foto())
    n = len(archivos_en_disco())
    azul = a["colores"][1]
    r = await admin.patch(f"/api/articulos/{a['id']}", json={"colores": [entrada(azul)]})
    assert [c["nombre"] for c in r.json()["colores"]] == ["Azul"]
    assert len(archivos_en_disco()) == n - 1


async def test_ids_de_colores_invalidos_se_rechazan_sin_cambios(admin):
    a = await crear_articulo(admin, colores=[ROJO])
    rojo = a["colores"][0]
    for colores in (
        [{"id": "00000000-0000-0000-0000-000000000000", "nombre": "X", "hex": "#000000"}],
        [entrada(rojo), entrada(rojo, nombre="Copia")],  # el mismo id dos veces
    ):
        r = await admin.patch(f"/api/articulos/{a['id']}", json={"colores": colores})
        assert r.status_code == 422
    assert [
        c["nombre"] for c in (await admin.get(f"/api/articulos/{a['id']}")).json()["colores"]
    ] == ["Rojo"]


async def test_fotos_requieren_sesion(admin, publico):
    a = await crear_articulo(admin, colores=[ROJO])
    ruta = f"/api/articulos/{a['id']}/colores/{a['colores'][0]['id']}/imagen"
    assert (await subir(publico, ruta, foto())).status_code == 401
    assert (await publico.delete(ruta)).status_code == 401
