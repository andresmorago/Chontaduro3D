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
| Cargar producción de meses atrás (carga retrospectiva) | **Producción**: elige la *Fecha de producción* (hasta 5 años atrás). Desmarca *Sumar al inventario actual* si esas piezas ya se vendieron: quedan en el historial y las métricas sin inflar el stock de hoy. Cada lote puede llevar sus propios valores de energía (kWh y potencia de esa época). |
| Registrar lo que imprimí | **Producción**: cada ficha trae un **+** (un toque suma una pieza) y, al elegir, un contador −/n/+ cuyo número también se puede **escribir**. Un artículo con colores ocupa dos columnas con una fila por color (cada una con su contador). Guardar → suma al inventario **de ese color**. Opcional: gramos de filamento (total o **por filamento**) y **tiempo de impresión**; con los *Parámetros de energía* (precio del kWh y potencia de la impresora) cada lote guarda sus kWh y su costo de energía. |
| Registrar una venta | **Vender**: igual que Producción (+, contador y filas por color); el **+** se bloquea al llegar a lo que hay de ese color. Forma de pago, *Registrar venta* → resta del inventario del color vendido. Hay *Deshacer* y *Anular* (la pieza vuelve a su color). |
| Ver o corregir el stock por color | **Inventario**: cada artículo con colores muestra su desglose («● Rojo 3 · ● Azul 0»). *Corregir el conteo* pide elegir el color. Ver [docs/inventario-por-color.md](docs/inventario-por-color.md). |
| Corregir un conteo | **Inventario → artículo → Corregir el conteo** (queda en el historial de movimientos). |
| Dar acceso a otra persona o cambiar contraseñas | **Administración**: crear usuarios, restablecer la contraseña de otro (cierra sus sesiones), desactivar/activar, y *Mi cuenta* para cambiar la tuya. Sin roles por ahora. |
| Ver lo que pidieron los clientes | **Pedidos**: un pedido puede traer **varios artículos y colores** (el cliente usa el mini carrito del catálogo); se ven todos los renglones, las piezas y un total estimado a precios de hoy. Botón directo a WhatsApp y estados. No descuenta inventario. Ver [docs/carrito-de-pedidos.md](docs/carrito-de-pedidos.md). |

## Modelo en una línea

El stock **no es un contador**: es la suma de los movimientos (`movimientos_inventario`: producción +, venta −, anulación +, ajuste ±).
Vender y ajustar bloquean la fila del artículo, así dos ventas simultáneas no pueden dejar el stock en negativo.
Cada movimiento lleva además su **color** (`color_id`): el stock de un artículo con colores se lleva **por color** y el total es la suma
(ver [docs/inventario-por-color.md](docs/inventario-por-color.md)).

## Migraciones (Alembic, idempotentes)

- `backend/alembic/versions/`: cada migración usa los ayudantes de `backend/app/idempotente.py`
  (`crear_tabla_si_no_existe`, `crear_indice_si_no_existe`, …) y puede repetirse sobre un esquema parcial.
- `backend/app/migrar.py` corre al arrancar el contenedor: candado de Postgres, **respaldo `pg_dump` antes de migrar**
  (en `data/respaldos/`, conserva los 10 últimos) y `alembic upgrade head`. Si el respaldo falla, no migra.
- Nueva migración: `make makemigration m="descripción"` y revisarla (usar los ayudantes idempotentes).

## Pruebas

```bash
make test    # unas 270 pruebas de backend contra un Postgres desechable (proyecto compose aparte, nunca la base real)
make e2e     # recorrido completo con navegador real (Playwright) contra el stack de desarrollo; capturas en e2e/out
make typecheck
make desbordes  # detector: recorre sitio público y panel a 9 anchos (1800–320 px) y falla si algún texto se sale de su tarjeta
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


## Impresora 3D (Bambu Lab A1)

Un servicio aparte (`impresora`) se conecta a la A1 por la red local (MQTT en el puerto 8883 y FTPS en el 990) y hace tres cosas:

1. **Estado**: lo guarda en la base para la página *Administración → Impresora* (progreso, temperaturas, AMS, luz, velocidad).
2. **Trabajos**: detecta cada trabajo (empieza, termina, se cancela) y lee del `.3mf` los gramos por filamento y el tiempo estimado. Aparecen en *Producción → Trabajos de la impresora*: se **importan** como producción (traen fecha, tiempo y gramos; si el trabajo trae los gramos de cada filamento, el lote se abre en **«Por filamento»** con cada uno rotulado por su color, p. ej. «PLA Rojo 24,5 g»; las piezas y su color los eliges tú) o se **ignoran**. Un trabajo no se puede importar dos veces.
3. **Controles**: pausar, reanudar, cancelar, luz y velocidad. El backend deja la orden en una tabla y el servicio la envía; una orden de más de 30 s no se ejecuta.

Configuración (solo en `.env`, nunca versionada): `BAMBU_IP`, `BAMBU_SERIAL`, `BAMBU_ACCESS_CODE` (ver `.env.example`). Solo el servicio `impresora` las recibe; el backend web no.
En desarrollo: `make impresora-up` (perfil `impresora`) y `make impresora-logs`. En producción corre con el stack: `make prod-impresora-logs`.

Limitaciones: la A1 no guarda historial de trabajos, así que solo se registran los que ocurren con el servicio encendido; los gramos son los **estimados del slicer** (en un trabajo cancelado sobrestiman); el tiempo es el *medido* (impresora ocupada) cuando se vio el inicio y, si no, el estimado del archivo. La conexión usa el certificado propio de la impresora, sin verificarlo: se asume una red local/VPN de confianza.

### Historial de Bambu Cloud (trabajos previos)

La A1 no guarda historial; el que ves en Bambu Studio y Bambu Handy está en la nube de Bambu. Para traerlo a *Producción → Trabajos de la impresora*:

1. Corre `make bambu-login` en tu terminal (correo, contraseña y el código que Bambu envía a tu correo; si el inicio de sesión falla o se bloquea, `make bambu-login ARGS=--pegar` para pegar el token copiado del navegador). Guarda **solo el token** en `data/nube/bambu.json` (modo 600, fuera de git); la contraseña no se guarda. El servicio lo renueva solo; si vence del todo, la página *Administración → Impresora* lo avisa.
2. El servicio `impresora` consulta la nube al arrancar y cada 10 minutos y trae los últimos `BAMBU_NUBE_DIAS` (7 por defecto). Cada trabajo se une con el detectado en vivo (mismo identificador, o mismo nombre y hora), así que no se duplica, y suma el **tiempo medido** que informa la nube. Lo que ya importaste o ignoraste no se revierte.
3. `make bambu-nube-prueba` muestra la forma de los datos de la nube (sin secretos), útil si Bambu cambia su API.

Es una API **no oficial**: puede cambiar o bloquearse sin aviso. Si falla, el resto de la app sigue igual y los trabajos en vivo siguen llegando.

## Un solo stack en marcha

Normalmente solo corre **producción** (`misimpresiones-prod`: `make prod-up-tunnel`). El stack de **desarrollo** (`misimpresiones`: `make up`) y el de pruebas (`make test`, `make e2e`) se levantan solo mientras se trabaja, y se apagan con `make down` (conserva los datos de `data/postgres`). `make e2e` y `make iphone` necesitan el de desarrollo encendido.
