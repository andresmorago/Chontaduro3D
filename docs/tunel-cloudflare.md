# Dominio público con Cloudflare (sin dominio propio)

La app se publica en una dirección **estable** de `workers.dev`, aunque por dentro use un *quick tunnel* de
Cloudflare cuya URL (`*.trycloudflare.com`) cambia cada vez que el túnel se reinicia.

```
Visitante ──► https://misimpresiones.<subdominio>.workers.dev      (Worker, URL fija)
                  │  añade x-proxy-secret, x-real-client-ip, x-forwarded-*
                  ▼
              https://<aleatorio>.trycloudflare.com               (quick tunnel, URL cambiante)
                  ▼
              cloudflared ──► frontend:3000 ──(/api/*)──► backend:8000 ──► db
```

## Piezas

| Pieza | Dónde | Qué hace |
| --- | --- | --- |
| Worker | `cloudflare/worker/index.js` | Proxy hacia el túnel. Fija las cabeceras de confianza (ignora las que mande el cliente) y reescribe redirecciones. |
| `cloudflared` | servicio `cloudflared` (perfil `tunnel`) | Quick tunnel hacia `frontend:3000`, con métricas en `:2000/quicktunnel`. |
| `urlsync` | `cloudflare/urlsync/urlsync.py`, servicio `urlsync` | Lee la URL del túnel y vuelve a subir el Worker con `ORIGIN` actualizado (API de Cloudflare). Sin socket de Docker, solo biblioteca estándar. |
| Secreto compartido | `PROXY_SHARED_SECRET` | El frontend responde **403** a lo que no traiga `x-proxy-secret`: la URL directa del túnel deja de servir la app. El backend solo cree `x-real-client-ip` si llega con ese secreto. |

## Credenciales

En `.env` (modo 600, **nunca** en git): `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `WORKER_NOMBRE`, `PROXY_SHARED_SECRET`, `TRUST_PROXY=1`.

El token necesita el permiso **Workers Scripts: Edit** (cuenta). Crearlo en *My Profile → API Tokens*, con vigencia larga y
solo ese permiso. **Si un token se comparte en un chat o un ticket, rótalo.**

> ⚠ El token usado en la puesta en marcha caduca el **2026-11-18**. Después de esa fecha `urlsync` no podrá
> actualizar el Worker cuando el túnel cambie de URL. Crea un token nuevo, ponlo en `.env` y reinicia `urlsync`:
> `make prod-restart s=urlsync`.

## Operación

```bash
make prod-build && make prod-up-tunnel   # levanta todo, incluido el túnel y urlsync
make prod-admin                          # crea/actualiza el administrador (ADMIN_EMAIL / ADMIN_PASSWORD)
make worker-publicar                     # sube el Worker una vez, a mano
make prod-logs s=urlsync                 # ver cuándo se actualizó el Worker
```

Si el túnel se reinicia, la URL de `trycloudflare.com` cambia y hay un corte de unos segundos hasta que `urlsync`
actualiza el Worker (revisa cada 15 s). La dirección pública no cambia.

## Limitaciones

- Los quick tunnels son un servicio gratuito sin garantía de disponibilidad (Cloudflare los pensó para pruebas).
  Para algo crítico, lo ideal es un dominio propio con un *named tunnel*: cambia `cloudflared` a
  `tunnel run --token …` y apunta el hostname desde el panel de Zero Trust (igual que en `misturnos`).
- Un Worker gratuito admite 100 000 peticiones al día.
