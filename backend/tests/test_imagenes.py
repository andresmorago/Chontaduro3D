import io

from PIL import Image

from app.config import settings
from tests.conftest import crear_articulo


def png(ancho=50, alto=50) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (ancho, alto), (200, 80, 40)).save(b, "PNG")
    return b.getvalue()


async def subir(c, a, datos: bytes, nombre="foto.png", tipo="image/png"):
    return await c.put(f"/api/articulos/{a['id']}/imagen", files={"archivo": (nombre, datos, tipo)})


async def test_subir_y_servir_imagen(admin, publico):
    a = await crear_articulo(admin)
    r = await subir(admin, a, png(3000, 2000))
    assert r.status_code == 200
    url = r.json()["imagen_url"]
    assert url.startswith("/api/media/") and url.endswith(".webp")
    img = await publico.get(url)  # el catálogo público la ve sin sesión
    assert img.status_code == 200 and img.headers["content-type"] == "image/webp"
    with Image.open(io.BytesIO(img.content)) as im:
        assert max(im.size) <= 2000 and im.format == "WEBP"


async def test_reemplazar_borra_la_anterior(admin, publico):
    a = await crear_articulo(admin)
    u1 = (await subir(admin, a, png())).json()["imagen_url"]
    u2 = (await subir(admin, a, png(60, 60))).json()["imagen_url"]
    assert u1 != u2
    assert (await publico.get(u1)).status_code == 404
    assert (await publico.get(u2)).status_code == 200


async def test_rechaza_lo_que_no_es_imagen_aunque_diga_que_lo_es(admin):
    a = await crear_articulo(admin)
    r = await subir(admin, a, b"<?php echo 'hola'; ?>", "foto.png", "image/png")
    assert r.status_code == 422
    r = await subir(
        admin,
        a,
        b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>",
        "x.svg",
        "image/svg+xml",
    )
    assert r.status_code == 422


async def test_rechaza_archivo_demasiado_grande(admin):
    a = await crear_articulo(admin)
    r = await subir(admin, a, b"0" * ((settings.max_upload_mb + 1) * 1024 * 1024 + 1))
    assert r.status_code == 413


async def test_no_se_puede_pedir_rutas_arbitrarias_de_media(publico):
    for nombre in ("../etc/passwd", "..%2fetc%2fpasswd", "x.webp", "A" * 32 + ".webp"):
        assert (await publico.get(f"/api/media/{nombre}")).status_code == 404


async def test_subir_imagen_exige_sesion(publico):
    r = await publico.put(
        "/api/articulos/00000000-0000-0000-0000-000000000000/imagen",
        files={"archivo": ("a.png", png(), "image/png")},
    )
    assert r.status_code == 401
