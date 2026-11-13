#!/bin/sh
# Entrada del contenedor de producción: migra la base y luego arranca la app.
#
# Si la migración falla NO se sale: un contenedor que muere y se reinicia en
# bucle reintentaría una migración a medias cada pocos segundos. Se queda vivo
# sin servir nada —el healthcheck lo marca `unhealthy` y el frontend no
# arranca—, con el error al final de los logs.
# Para repetir el intento: `make prod-restart s=backend`.

if ! python -m app.migrar; then
    echo "[arrancar] La migración falló. La app NO arrancó." >&2
    echo "[arrancar] Revisa el error de arriba. El respaldo previo (si se alcanzó a sacar) está en ./data/respaldos." >&2
    trap 'exit 1' TERM INT
    sleep infinity &
    wait
fi

exec "$@"
