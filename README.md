# Mis impresiones

Plataforma para un emprendimiento de impresión 3D: **artículos maestros**, **producción** (entra al inventario),
**ventas** (salen del inventario), **inventario** y un **catálogo público** donde los clientes ven los artículos
y dejan un **pedido** (que no toca el inventario).

- Backend: Python 3.13 · FastAPI · SQLAlchemy 2 (async) · Alembic · PostgreSQL 17
- Frontend: TypeScript · Next.js 15 (App Router) · diseño Hallmark, tema Terrazzo
- Estructura de despliegue replicada de `misturnos` (Docker Compose, migraciones al arrancar con respaldo previo, túnel de Cloudflare)

## Arrancar en desarrollo

```bash
cp .env.example .env        # completar: POSTGRES_PASSWORD, SECRET_KEY (openssl rand -hex 32), ADMIN_EMAIL, ADMIN_PASSWORD, DATABASE_URL
chmod 600 .env
make bootstrap              # levanta, migra, siembra y crea el administrador
make demo                   # (opcional) 3 artículos de EJEMPLO para probar
```

- Catálogo: <http://localhost:3100> · Panel: <http://localhost:3100/panel> · API (docs): <http://localhost:8100/api/docs>
- `make help` lista todos los comandos.

## Cómo se usa

| Quiero… | Voy a… |
| --- | --- |
| Dar de alta un producto | **Artículos → Nuevo artículo** (nombre, foto, descripción, precio). El precio se puede cambiar cuando quieras; queda historial y las ventas pasadas no cambian. |
| Registrar lo que imprimí | **Producción**: tocar los artículos, guardar → suma al inventario. |
| Registrar una venta | **Vender**: tocar los artículos, forma de pago, *Registrar venta* → resta del inventario. Hay *Deshacer* y *Anular*. |
| Corregir un conteo | **Inventario → artículo → Corregir el conteo** (queda en el historial de movimientos). |
| Ver lo que pidieron los clientes | **Pedidos**: botón directo a WhatsApp y estados. No descuenta inventario. |

## Modelo en una línea

El stock **no es un contador**: es la suma de los movimientos (`movimientos_inventario`: producción +, venta −, anulación +, ajuste ±).
Vender y ajustar bloquean la fila del artículo, así dos ventas simultáneas no pueden dejar el stock en negativo.

## Migraciones (Alembic, idempotentes)

- `backend/alembic/versions/`: cada migración usa los ayudantes de `backend/app/idempotente.py`
  (`crear_tabla_si_no_existe`, `crear_indice_si_no_existe`, …) y puede repetirse sobre un esquema parcial.
- `backend/app/migrar.py` corre al arrancar el contenedor: candado de Postgres, **respaldo `pg_dump` antes de migrar**
  (en `data/respaldos/`, conserva los 10 últimos) y `alembic upgrade head`. Si el respaldo falla, no migra.
- Nueva migración: `make makemigration m="descripción"` y revisarla (usar los ayudantes idempotentes).

## Pruebas

```bash
make test    # 75 pruebas de backend contra un Postgres desechable (proyecto compose aparte, nunca la base real)
make e2e     # recorrido completo con navegador real (Playwright) contra el stack de desarrollo; capturas en e2e/out
make typecheck
make iphone  # WebKit (el motor de Safari) con perfiles de iPhone SE, 13 y 15 Pro Max: desbordes, hoja de pedido, login con toque real y panel
```

## Producción y dominio público (Cloudflare, sin dominio propio)

Ver [docs/tunel-cloudflare.md](docs/tunel-cloudflare.md). Resumen:

```bash
make prod-build && make prod-up-tunnel && make prod-admin
```

La app queda en `https://<WORKER_NOMBRE>.<tu-subdominio>.workers.dev` (estable aunque el túnel cambie de URL).

## Cloudflare Turnstile (el «reCAPTCHA» de Cloudflare)

Protege el **login** y el **pedido del catálogo**. El navegador solo muestra el widget; el servidor valida el token contra
Cloudflare con la llave secreta (`backend/app/core/turnstile.py`) y **falla cerrado** si Cloudflare no responde.

1. Panel de Cloudflare → **Turnstile** → *Add widget*: hostname `misimpresiones.<tu-subdominio>.workers.dev`, modo *Managed*.
2. Copia la **Site key** (pública) y la **Secret key** a `.env` como `TURNSTILE_SITEKEY` y `TURNSTILE_SECRETKEY`.
3. `make prod-up-tunnel` (recrea el backend). Vacías = apagado.

En desarrollo se usan las llaves de prueba de Cloudflare (siempre aprueban), así el flujo con widget se ejercita sin configurar nada.

## Seguridad (lo que ya está)

Cookies `HttpOnly` + `SameSite=Lax` (+ `Secure` tras HTTPS), refresh con rotación y detección de reutilización,
cabecera anti-CSRF en toda mutación, CSP con nonce, límites de intentos (ingreso y pedidos) guardados en la base,
imágenes validadas por contenido y re-codificadas, el catálogo público nunca expone el stock exacto,
`/api/docs` apagado en producción y la URL directa del túnel bloqueada por un secreto compartido con el Worker.
