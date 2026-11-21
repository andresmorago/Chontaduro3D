#!/usr/bin/env bash
# Cortafuegos de Spoolman (que no tiene autenticación): el puerto publicado solo acepta conexiones
# NUEVAS que entren por la interfaz de WireGuard y vengan de la LAN de casa. Todo lo demás se descarta.
#
# Las reglas van en DOCKER-USER (Docker no la borra) y filtran por el puerto ORIGINAL (antes del DNAT
# de Docker). Los paquetes de respuesta no se tocan. Es idempotente: se puede repetir sin duplicar.
# Lo aplica la unidad systemd spoolman-firewall.service tras arrancar Docker. Ver docs/spoolman.md.
set -euo pipefail

PUERTO="${SPOOLMAN_PORT:-7912}"
IFAZ="${SPOOLMAN_IFACE:-wg0}"
PERMITIDO="${SPOOLMAN_ALLOWED:-10.0.4.0/24}"
ETIQ="spoolman-wg"

ipt() { iptables -w 5 "$@"; }

# Si la cadena no existe todavía (Docker no ha arrancado), no hay nada que proteger ni dónde poner reglas.
ipt -S DOCKER-USER >/dev/null 2>&1 || { echo "DOCKER-USER no existe: ¿Docker está corriendo?" >&2; exit 1; }

# Quita las reglas anteriores (las identifica el comentario), cualesquiera que fueran sus parámetros.
while read -r regla; do
  [ -n "$regla" ] || continue
  # shellcheck disable=SC2086
  ipt ${regla/-A /-D }
done < <(ipt -S DOCKER-USER | grep -- "--comment $ETIQ" || true)

COMUN=(-p tcp -m conntrack --ctstate DNAT --ctorigdstport "$PUERTO" --ctdir ORIGINAL -m comment --comment "$ETIQ")
# Orden: primero la excepción (RETURN deja que las reglas normales de Docker sigan), luego el descarte.
ipt -I DOCKER-USER 1 "${COMUN[@]}" -j DROP
ipt -I DOCKER-USER 1 -i "$IFAZ" -s "$PERMITIDO" "${COMUN[@]}" -j RETURN
echo "Spoolman: puerto $PUERTO solo desde $PERMITIDO por $IFAZ."
