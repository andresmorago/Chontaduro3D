from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.core import imagenes

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/{nombre}")
async def imagen(nombre: str) -> FileResponse:
    ruta = imagenes.ruta_de(nombre)
    if ruta is None or not ruta.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Imagen no encontrada.")
    return FileResponse(
        ruta, media_type="image/webp",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )  # fmt: skip
