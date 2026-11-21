# Mis impresiones

Plataforma para un emprendimiento de impresión 3D: **artículos maestros**, **producción** (entra al inventario),
**ventas** (salen del inventario), **inventario** y un **catálogo público** donde los clientes ven los artículos
y dejan un **pedido** (que no toca el inventario).

- Backend: Python 3.13 · FastAPI · SQLAlchemy 2 (async) · Alembic · PostgreSQL 17
- Frontend: TypeScript · Next.js 15 (App Router) · diseño Hallmark, tema Squeeze (ver [design.md](design.md))
- Estructura de despliegue replicada de `misturnos` (Docker Compose, migraciones al arrancar con respaldo previo, túnel de Cloudflare)
- Impresora Bambu Lab A1 integrada (estado, trabajos y controles), configurada desde el propio panel: sin `.env` ni scripts
- Inventario de filamento con [Spoolman](docs/spoolman.md): cada trabajo de la impresora descuenta de su bobina; Spoolman solo se abre desde la red de casa (WireGuard)

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
| Registrar una venta | **Vender**: igual que Producción (+, contador y filas por color); el **+** se bloquea al llegar a lo que hay de ese color. Forma de pago, *Registrar venta* → resta del inventario del color vendido. Hay *Deshacer* y *Anular* (la pieza vuelve a su color). Opcional: elige el **pedido que atiendes** para asociarla y cerrarlo (ver abajo). |
| Ver o corregir el stock por color | **Inventario**: cada artículo con colores muestra su desglose («● Rojo 3 · ● Azul 0»). *Corregir el conteo* pide elegir el color. Ver [docs/inventario-por-color.md](docs/inventario-por-color.md). |
| Atender un pedido y cerrarlo con la venta | En **Pedidos**, *Atender con una venta* abre **Vender** con los artículos, colores y cantidades del pedido ya cargados (limitados al stock; lo que no se pueda cargar se avisa) y el cliente puesto. Al *Registrar venta* el pedido queda **Cerrado** (casilla «Cerrar el pedido al registrar la venta»; desmárcala para una entrega parcial). En Vender también puedes elegir el pedido a mano, o dejar la venta suelta. La tarjeta del pedido muestra lo **vendido**. Ver [docs/carrito-de-pedidos.md](docs/carrito-de-pedidos.md#atender-un-pedido-con-una-venta). |
| Corregir un conteo | **Inventario → artículo → Corregir el conteo** (queda en el historial de movimientos). |
| Dar acceso a otra persona o cambiar contraseñas | **Administración → Cuenta y usuarios**: crear usuarios, restablecer la contraseña de otro (cierra sus sesiones), desactivar/activar, y *Mi cuenta* para cambiar la tuya. Sin roles por ahora. |
| Conectar la impresora y mi cuenta de Bambu Lab | **Administración → Conexión**: IP, número de serie y código de acceso de la impresora, y vincular la cuenta de Bambu (correo, contraseña y código de verificación). Ver [Impresora 3D](#impresora-3d-bambu-lab-a1). |
| Ver o controlar la impresora | **Administración → Impresora**: estado, temperaturas, filamento (AMS), pausar/reanudar/cancelar, luz, velocidad y ventiladores. |
| Ver TODO lo que imprimió la impresora (desde Bambu Studio/web o desde su pantalla) | **Producción → Trabajos de la impresora → Todos** (también *Por revisar*, *Importados*, *Ignorados*). Cada trabajo muestra inicio y fin (hora de Bogotá), quién lo envió y su estado en Spoolman. Los lanzados desde la pantalla no aparecen en Bambu Studio/web: solo los ve este servicio. Los gramos coinciden con Bambu web (la nube corrige lo leído del `.3mf`). |
| Saber cuánto filamento queda y de qué bobina salió | **Administración → Impresora → Bobinas (Spoolman)**: asocia la bobina de cada ranura del AMS; cada trabajo terminado descuenta solo y lo dudoso se resuelve ahí. Spoolman se abre desde casa en `http://10.6.0.6:7912`. Ver [docs/spoolman.md](docs/spoolman.md). |
| Ver lo que pidieron los clientes | **Pedidos**: un pedido puede traer **varios artículos y colores** (el cliente usa el mini carrito del catálogo); se ven todos los renglones, las piezas y un total estimado a precios de hoy. Botón directo a WhatsApp, estados y **Atender con una venta**. No descuenta inventario por sí solo. Ver [docs/carrito-de-pedidos.md](docs/carrito-de-pedidos.md). |

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
make test    # unas 310 pruebas de backend contra un Postgres desechable (proyecto compose aparte, nunca la base real)
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
3. **Controles**: pausar, reanudar, cancelar, luz, velocidad, temperaturas y ventiladores. El backend deja la orden en una tabla y el servicio la envía; una orden de más de 30 s no se ejecuta.

### Configuración desde el panel (Administración → Conexión)

No hace falta `.env` ni ningún script: todo se hace en la pestaña **Conexión**.

**Impresora.** Escribe la IP (Ajustes → WLAN en la pantalla de la impresora), el número de serie y el código de acceso, y pulsa *Guardar y conectar*. El servicio toma los datos de la base, reconecta solo y el panel te dice si quedó **En línea** (con cuándo respondió la impresora y qué está haciendo), si el **código de acceso fue rechazado** o si **no se alcanza la IP** (impresora apagada, IP errónea o VPN caída). *Probar conexión* descarta la conexión actual y abre una nueva con lo guardado: es una prueba de punta a punta. Para cambiar solo la IP, deja el código vacío: se conserva el guardado.

**Cuenta de Bambu Lab** (historial de Studio y Handy): *Vincular cuenta* con tu correo y contraseña; si Bambu pide verificación, escribes el código que llega al correo (o el de tu app 2FA). Si Bambu bloquea el inicio de sesión desde el servidor, *Pegar el token* (cookie `token` de bambulab.com). *Vinculada* solo significa que hay un acceso guardado; lo que prueba que Bambu responde es **Probar y sincronizar** (consulta la nube de verdad y dice cuántos trabajos trajo). La etiqueta pasa a **En línea** si Bambu respondió en los últimos 25 minutos, y a «Sin respuesta», «Sin verificar» o «Hay que volver a vincular» si no. También puedes **Desvincular**.

Cómo se protege (detalle en [docs/conexion-impresora.md](docs/conexion-impresora.md)):

- El código de acceso y el token se guardan **cifrados** en la base (Fernet, clave derivada de `SECRET_KEY`); la API nunca los devuelve y los respaldos no los llevan en claro.
- La contraseña de Bambu solo pasa hacia Bambu para entrar: **no se guarda** ni se registra; se conserva únicamente el token, que el servicio renueva solo.
- La IP debe ser de red local o VPN (se rechaza internet, loopback y link-local) y el número de serie solo admite letras y números.
- Si cambias `SECRET_KEY`, lo guardado deja de poder leerse y el panel pide escribirlo otra vez.

**Si ya usabas `.env`:** al arrancar, el servicio importa **una vez** `BAMBU_IP`, `BAMBU_SERIAL` y `BAMBU_ACCESS_CODE` (y el token viejo de `data/nube/bambu.json`, que no se borra: puedes eliminarlo cuando quieras) a la base. Después puedes quitarlos del `.env`. `make bambu-login` ya no existe.

En desarrollo: `make impresora-up` (perfil `impresora`) y `make impresora-logs`. En producción corre con el stack: `make prod-impresora-logs`. `make bambu-nube-prueba` muestra la forma de los datos de la nube (sin secretos), útil si Bambu cambia su API.

Limitaciones: la A1 no guarda historial de trabajos, así que solo se registran los que ocurren con el servicio encendido (o los que trae Bambu Cloud); los gramos son los **estimados del slicer** (en un trabajo cancelado sobrestiman); el tiempo es el *medido* (impresora ocupada, o el que informa la nube) y, si no, el estimado del archivo. La conexión usa el certificado propio de la impresora, sin verificarlo: se asume una red local/VPN de confianza.

### Historial de Bambu Cloud

La A1 no guarda historial; el que ves en Bambu Studio y Bambu Handy está en la nube de Bambu. Con la cuenta vinculada, el servicio consulta la nube al arrancar, cada 10 minutos y cuando pulsas *Sincronizar ahora*, y trae los últimos `BAMBU_NUBE_DIAS` (7 por defecto, único ajuste que sigue en `.env`). Cada trabajo se une con el detectado en vivo (mismo identificador, o mismo nombre y hora), así que no se duplica, y suma el **tiempo medido** que informa la nube. Lo que ya importaste o ignoraste no se revierte.

Es una API **no oficial**: puede cambiar o bloquearse sin aviso. Si falla, el resto de la app sigue igual y los trabajos en vivo siguen llegando; la pestaña Conexión muestra el motivo.

## Un solo stack en marcha

Normalmente solo corre **producción** (`misimpresiones-prod`: `make prod-up-tunnel`). El stack de **desarrollo** (`misimpresiones`: `make up`) y el de pruebas (`make test`, `make e2e`) se levantan solo mientras se trabaja, y se apagan con `make down` (conserva los datos de `data/postgres`). `make e2e` y `make iphone` necesitan el de desarrollo encendido.

## Estructura del repositorio

| Ruta | Qué hay |
| --- | --- |
| `backend/` | API FastAPI (`app/api`), modelos y migraciones, servicio de la impresora (`app/impresora`) y pruebas (`tests/`) |
| `frontend/` | Next.js: catálogo público, panel (`app/panel/*`) y componentes |
| `cloudflare/` | Worker de workers.dev y `urlsync` (mantiene el Worker apuntando al túnel) |
| `e2e/` | Pruebas con navegador real (Playwright): recorrido, desbordes e iPhone |
| `docs/` | [Túnel de Cloudflare](docs/tunel-cloudflare.md), [inventario por color](docs/inventario-por-color.md), [carrito de pedidos](docs/carrito-de-pedidos.md), [conexión de la impresora](docs/conexion-impresora.md) |
| `data/` | Datos locales (ignorado por git): bases, imágenes y respaldos |
| `design.md` | Sistema de diseño bloqueado (Squeeze) |

## Variables de entorno (`.env`)

`.env.example` documenta todas; las que más importan: `POSTGRES_*` y `DATABASE_URL`, `SECRET_KEY` (obligatoria en producción; también cifra la configuración de la impresora), `ADMIN_EMAIL`/`ADMIN_PASSWORD` (para `make admin`), `TURNSTILE_*`, `WHATSAPP_NEGOCIO`, `NOMBRE_NEGOCIO`, `PROXY_SHARED_SECRET`/`TRUST_PROXY` y las de Cloudflare (`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `WORKER_NOMBRE`). La impresora **no** se configura aquí (ver arriba). El `.env` no se versiona.
