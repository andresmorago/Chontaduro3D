# Mis impresiones

Plataforma para un emprendimiento de impresión 3D: **artículos maestros**, **producción** (entra al inventario),
**ventas** (salen del inventario), **inventario** y un **catálogo público** donde los clientes ven los artículos
y dejan un **pedido** (que no toca el inventario).

- Backend: Python 3.13 · FastAPI · SQLAlchemy 2 (async) · Alembic · PostgreSQL 17
- Frontend: TypeScript · Next.js 15 (App Router) · diseño Hallmark, tema Squeeze (ver [design.md](design.md))
- Estructura de despliegue replicada de `misturnos` (Docker Compose, migraciones al arrancar con respaldo previo, túnel de Cloudflare)
- Impresora Bambu Lab A1 integrada (estado, trabajos y controles), configurada desde el propio panel: sin `.env` ni scripts
- Inventario de filamento con [Spoolman](docs/spoolman.md): cada trabajo de la impresora descuenta de su bobina; Spoolman solo se abre desde la red de casa (WireGuard)
- Publicación sin dominio propio: Worker de `workers.dev` → *quick tunnel* de Cloudflare, con Turnstile en el login y en el pedido del catálogo

## Arquitectura

**Diagrama interactivo: [docs/arquitectura.html](docs/arquitectura.html)** (ábrelo en el navegador; tema claro/oscuro, exportable).
GitHub no ejecuta HTML: descarga el archivo o ábrelo desde el repositorio local.

El camino de una visita es `Navegador → Worker (workers.dev) → cloudflared → Next.js → FastAPI → PostgreSQL`. La impresora y
Spoolman cuelgan de ese núcleo por dos canales distintos: **la base de datos** (el servicio `impresora` y el backend se
hablan solo a través de tablas) y **la red interna de Docker** (ambos le hablan a Spoolman por `http://spoolman:8000`).

### Servicios (`docker-compose.prod.yml`)

| Servicio | Imagen / tecnología | Puerto | Qué hace |
| --- | --- | --- | --- |
| `frontend` | Next.js 15 (App Router) | 3000 (interno) | Catálogo público y panel. Responde **403** a lo que no traiga `x-proxy-secret`; reenvía `/api/*` al backend; CSP con nonce. |
| `backend` | FastAPI · Python 3.13 · 2 workers | 8000 (interno) | API `/api`, autenticación, reglas de inventario, Turnstile, panel de la impresora y de Spoolman. Migra la base al arrancar (con respaldo). |
| `db` | PostgreSQL 17 | sin publicar | Negocio (artículos, producción, ventas, pedidos, inventario) y estado de la impresora y de Spoolman. |
| `impresora` | Mismo código del backend (`python -m app.impresora.servicio`) | sin puerto | Habla con la A1 y con Bambu Cloud, y es **el único que descuenta filamento en Spoolman**. |
| `spoolman` | `ghcr.io/donkie/spoolman:0.27.1` · SQLite | 7912, **solo** en la IP de WireGuard (`10.6.0.6`) | Inventario de bobinas. No tiene autenticación: ver [docs/spoolman.md](docs/spoolman.md#red-y-seguridad). |
| `cloudflared` | `cloudflare/cloudflared` (perfil `tunnel`) | métricas 2000 | *Quick tunnel* hacia `frontend:3000`. |
| `urlsync` | Python 3.13, solo biblioteca estándar (perfil `tunnel`) | — | Lee la URL vigente del túnel y vuelve a subir el Worker con ella (cada 15 s). |

En desarrollo (`make up`) el frontend sale por el puerto **3100**, la API por **8100** y la base por **5433**; no hay túnel.

### Integraciones

| Con quién | Cómo | Para qué | Dónde está |
| --- | --- | --- | --- |
| Cloudflare Worker + túnel | HTTPS; el Worker fija `x-proxy-secret` y `x-real-client-ip` | Dirección pública estable sin dominio propio | `cloudflare/worker`, `cloudflare/urlsync`, [docs/tunel-cloudflare.md](docs/tunel-cloudflare.md) |
| Cloudflare Turnstile | El backend valida el token (`siteverify`); falla cerrado | Proteger el login y el pedido del catálogo | `backend/app/core/turnstile.py` |
| Bambu Lab A1 | MQTT 8883 (estado y controles) y FTPS 990 (lee el `.3mf`) por la red local/WireGuard | Estado, trabajos y controles | `backend/app/impresora/bambu.py`, `lector3mf.py` |
| Bambu Cloud | API **no oficial**, cada 10 min y a demanda | Historial, tiempo medido y gramos definitivos | `backend/app/impresora/nube.py`, `nube_login.py` |
| Spoolman | REST v1 por la red interna | Bobinas, tags RFID, ubicaciones y descuento de gramos | `backend/app/spoolman/` |
| WireGuard + `iptables` | Regla en `DOCKER-USER`: solo `10.0.4.0/24` por `wg0` llega al puerto 7912 | Abrir Spoolman desde casa y nada más | `ops/spoolman-firewall.sh` |

### Módulos del backend (`backend/app/`)

| Carpeta | Responsabilidad |
| --- | --- |
| `api/` | Routers: `articulos`, `produccion`, `ventas`, `pedidos`, `inventario`, `publico` (catálogo), `auth`, `usuarios`, `parametros`, `panel`, `media`, `impresora`, `impresora_conexion`, `spoolman`. |
| `core/` | Reglas de inventario (stock = suma de movimientos), energía, sesión (JWT + refresh rotativo), argon2id, Turnstile, imágenes, cifrado de secretos (Fernet), tope de cuerpo y auditoría. |
| `models/` | Tablas SQLAlchemy 2 (async) por dominio; las migraciones de Alembic son idempotentes (`idempotente.py`). |
| `impresora/` | Servicio de la A1: protocolo MQTT (`bambu.py`), máquina de estados de trabajos (`maquina.py`), lector de `.3mf`, historial de Bambu Cloud y su unión con lo detectado en vivo (`sincronizacion.py`), configuración cifrada (`ajustes.py`). |
| `spoolman/` | Cliente REST, emparejamiento ranura↔bobina (`asignacion.py`), registro automático de bobinas con chip (`registro.py`), descuento de gramos (`consumo.py`) y consumo estimado del histórico (`historial.py`). |
| `seeds/` | Datos mínimos, administrador y demo (artículos de ejemplo). |

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
| Saber qué hay que imprimir | **Pedidos → Por producir**: la demanda de los pedidos abiertos agrupada por artículo y color, contra el stock actual. Ver [docs/carrito-de-pedidos.md](docs/carrito-de-pedidos.md#por-producir-demanda-agrupada-por-artículo). |
| Ver las ventas de un día | **Vender → calendario**: elige un día y ves sus ventas por venta y artículo (el resumen por día sale de `GET /api/ventas/resumen`). |
| Corregir un conteo | **Inventario → artículo → Corregir el conteo** (queda en el historial de movimientos). |
| Dar acceso a otra persona o cambiar contraseñas | **Administración → Cuenta y usuarios**: crear usuarios, restablecer la contraseña de otro (cierra sus sesiones), desactivar/activar, y *Mi cuenta* para cambiar la tuya. Sin roles por ahora. |
| Conectar la impresora y mi cuenta de Bambu Lab | **Administración → Conexión**: IP, número de serie y código de acceso de la impresora, y vincular la cuenta de Bambu (correo, contraseña y código de verificación). Ver [Impresora 3D](#impresora-3d-bambu-lab-a1). |
| Ver o controlar la impresora | **Administración → Impresora**: estado, temperaturas, filamento (AMS), pausar/reanudar/cancelar, luz, velocidad y ventiladores. |
| Ver TODO lo que imprimió la impresora (desde Bambu Studio/web o desde su pantalla) | **Producción → Trabajos de la impresora → Todos** (también *Por revisar*, *Importados*, *Ignorados*). Cada trabajo muestra inicio y fin (hora de Bogotá), quién lo envió y su estado en Spoolman. Los lanzados desde la pantalla no aparecen en Bambu Studio/web: solo los ve este servicio. Los gramos coinciden con Bambu web (la nube corrige lo leído del `.3mf`). |
| Saber cuánto filamento queda y de qué bobina salió | **Administración → Impresora → Filamento**: asocia la bobina de cada ranura del AMS; cada trabajo terminado descuenta solo y lo dudoso se resuelve ahí. Spoolman se abre desde casa en `http://10.6.0.6:7912`. Ver [Spoolman](#inventario-de-filamento-spoolman) y [docs/spoolman.md](docs/spoolman.md). |
| Forzar que el AMS vuelva a leer el chip de una bobina | **Administración → Impresora → Filamento → Releer chip** (en el menú *Más* de cada ranura; no hace falta descargar el rollo, solo que no se esté imprimiendo). Muestra el código del chip leído; si el firmware rechaza la orden, el panel lo dice. Es lo mismo que el botón de actualizar de Bambu Studio. Ver [docs/spoolman.md](docs/spoolman.md#releer-el-chip-rfid-de-una-ranura). |
| Cargar un rollo nuevo (Bambu o Sunlu) | Cárgalo en la **impresora o en Bambu Studio**: la app lo ve sola. Con chip Bambu se registra en Spoolman; sin chip se une solo a la bobina de Spoolman del mismo material y color si hay una única, o te pregunta cuál es. «Actividad reciente» muestra qué vio. La app no escribe en el AMS (el firmware solo acepta órdenes firmadas por Bambu). Ver [docs/spoolman.md](docs/spoolman.md#cuando-el-rollo-cambia-o-llega-uno-nuevo-desde-la-impresora). |
| Ver el UID del chip RFID de una bobina | En **Spoolman** (`http://10.6.0.6:7912`) es el *tag* de la bobina; por API: `GET /api/v1/spool?allow_archived=true` y campo `tags[].uid`. El panel de Mis impresiones no lo muestra. Los chips ya leídos quedan también en la tabla `chips_bobina`. |
| Corregir un rollo o ver los de repuesto | **Administración → Impresora → Filamento**: *Ajustar* (cuánto queda, precio, archivar un rollo terminado) y la lista de **Rollos de repuesto** con los que quedan poco primero. Sin entrar a Spoolman. |
| Saber si el filamento alcanza para lo que imprimo | En la misma sección, mientras hay un trabajo en curso: cada ranura de «En la impresora ahora» dice «Este trabajo usa X g» y si le alcanza, comparando los gramos del archivo con lo que queda en su rollo. |
| Ligar un lote de producción a una bobina | **Producción → Filamento y tiempo → Por filamento**: cada línea puede apuntar a una bobina de Spoolman (nombre en vivo). Importar un trabajo de la impresora ya trae la bobina y los gramos descontados. |
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
make test    # unas 480 pruebas de backend contra un Postgres desechable (proyecto compose aparte, nunca la base real)
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


**Auditoría OWASP Top 10 (2026-11-21)** y lo que se corrigió:

- **Sesión:** el refresh tiene una ventana de gracia de 15 s para dos peticiones simultáneas (ya no cierra todas las sesiones por una carrera); la contraseña rechaza las más comunes y las iguales al correo; se purgan solas las sesiones y los intentos fallidos viejos.
- **Producción falla cerrado:** el backend no arranca sin `TRUST_PROXY` + `PROXY_SHARED_SECRET` ni sin llaves de Turnstile, y el frontend responde 503 si falta el secreto compartido. El servicio `impresora` exige `SECRET_KEY` de ≥ 32 caracteres.
- **SSRF:** la IP de la impresora no puede estar en las redes internas de Docker (`172.16.0.0/12`); `BAMBU_REDES_PERMITIDAS` la limita a tus redes.
- **Datos externos:** el UID del chip se valida antes de usarse en rutas de Spoolman; los gramos y el progreso que informan la impresora o Bambu Cloud tienen tope; un descuento se reclama de forma atómica (no se envía si se omitió justo antes).
- **Contenedores:** `backend`, `frontend`, `impresora` y `urlsync` corren sin capacidades (`cap_drop: ALL`, `no-new-privileges`) y `urlsync` ya no es root. `npm ci` con `package-lock.json` en el frontend.
- **Pendiente / aceptado:** no hay roles (cualquier usuario con sesión administra a los demás); Python sin lockfile con hashes; `cloudflared:latest` sin versión fijada; TLS hacia la impresora sin verificar (certificado propio de Bambu); `postcss` anidado en Next 15 con avisos de `npm audit` (se corrigen con Next 16, cambio mayor).

## Impresora 3D (Bambu Lab A1)

Un servicio aparte (`impresora`) se conecta a la A1 por la red local (MQTT en el puerto 8883 y FTPS en el 990) y hace tres cosas:

1. **Estado**: lo guarda en la base para la página *Administración → Impresora* (progreso, temperaturas, AMS, luz, velocidad).
2. **Trabajos**: detecta cada trabajo (empieza, termina, se cancela) y lee del `.3mf` los gramos por filamento y el tiempo estimado. Aparecen en *Producción → Trabajos de la impresora*: se **importan** como producción (traen fecha, tiempo y gramos; si el trabajo trae los gramos de cada filamento, el lote se abre en **«Por filamento»** con cada uno rotulado por su color, p. ej. «PLA Rojo 24,5 g»; las piezas y su color los eliges tú) o se **ignoran**. Un trabajo no se puede importar dos veces.
3. **Controles**: pausar, reanudar, cancelar, luz, velocidad, temperaturas, ventiladores y releer el chip RFID de una ranura. El backend deja la orden en una tabla y el servicio la envía; una orden de más de 30 s no se ejecuta.

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

## Inventario de filamento (Spoolman)

[Spoolman](docs/spoolman.md) lleva las bobinas (marca, material, color, precio, gramos que quedan). Mis impresiones y Spoolman
se hablan siempre: **todo lo que imprime la impresora descuenta de su bobina**, se importe o no como lote de producción.

- **Una sola mano escribe.** El servicio `impresora` es el único que descuenta (`PUT /spool/{id}/use`); el backend solo lee,
  vincula y deja decidir lo dudoso desde el panel. Así un descuento nunca se manda dos veces.
- **De qué bobina salió.** La A1 no informa el mapeo del trabajo, solo la bandeja en uso (`tray_now`); el servicio la empareja con los
  filamentos del `.3mf` por tipo y color. Con duda **no adivina**: la línea queda «Falta elegir la bobina».
- **Chip RFID.** Las bobinas Bambu con chip se registran solas (sin duplicarse: el UID es único y queda como *tag* de la bobina en
  Spoolman y en `chips_bobina`). Las que no tienen chip se crean con un clic por ranura (*Crear en Spoolman*) o se asocian a mano.
- **Ciclo de un descuento** (`consumos_filamento`): `sin_bobina → por_enviar → enviando → descontado`; si el proceso muere a medias
  queda `revisar` y no se reenvía solo. Un trabajo cortado descuenta solo lo hecho (`gramos × progreso`).
- **Ubicaciones.** Cada ~30 s se escribe en la bobina su ranura («AMS · Ranura 2»); lo que pongas a mano se respeta.
- **Producción ↔ Spoolman.** Una línea de filamento de un lote puede apuntar a una bobina (`produccion_filamentos.spool_id`) y guarda su **costo**
  (gramos × precio del rollo), congelado al guardar; el lote suma el costo del filamento.
- **Desde el panel.** Ajustar «cuánto queda» y el precio, archivar rollos terminados, lista de repuestos con aviso de «queda poco» (< 150 g) y
  aviso «¿alcanza?» mientras se imprime.
- **Lo impreso antes de conectar** se reparte con `python -m app.spoolman.historial` (vista previa por defecto).
- **Red.** Sin autenticación, así que: sin pasar por el Worker, publicado solo en la IP de WireGuard, cortafuegos en `DOCKER-USER`
  (`make spoolman-firewall`, `make spoolman-firewall-estado`) y contenedor sin privilegios. Datos y respaldos en `data/spoolman/`.

Detalle, variables, primeros pasos y límites: [docs/spoolman.md](docs/spoolman.md).

## Un solo stack en marcha

Normalmente solo corre **producción** (`misimpresiones-prod`: `make prod-up-tunnel`). El stack de **desarrollo** (`misimpresiones`: `make up`) y el de pruebas (`make test`, `make e2e`) se levantan solo mientras se trabaja, y se apagan con `make down` (conserva los datos de `data/postgres`). `make e2e` y `make iphone` necesitan el de desarrollo encendido.

## Estructura del repositorio

| Ruta | Qué hay |
| --- | --- |
| `backend/` | API FastAPI (`app/api`), modelos y migraciones, servicio de la impresora (`app/impresora`) y pruebas (`tests/`) |
| `frontend/` | Next.js: catálogo público, panel (`app/panel/*`) y componentes |
| `cloudflare/` | Worker de workers.dev y `urlsync` (mantiene el Worker apuntando al túnel) |
| `ops/` | Cortafuegos de Spoolman (`spoolman-firewall.sh` y su unidad systemd) |
| `e2e/` | Pruebas con navegador real (Playwright): recorrido, desbordes e iPhone |
| `docs/` | [Arquitectura (diagrama)](docs/arquitectura.html), [Spoolman](docs/spoolman.md), [túnel de Cloudflare](docs/tunel-cloudflare.md), [inventario por color](docs/inventario-por-color.md), [carrito de pedidos](docs/carrito-de-pedidos.md), [conexión de la impresora](docs/conexion-impresora.md) |
| `data/` | Datos locales (ignorado por git): bases, imágenes y respaldos |
| `design.md` | Sistema de diseño bloqueado (Squeeze) |

## Variables de entorno (`.env`)

`.env.example` documenta todas; las que más importan: `POSTGRES_*` y `DATABASE_URL`, `SECRET_KEY` (obligatoria en producción; también cifra la configuración de la impresora), `ADMIN_EMAIL`/`ADMIN_PASSWORD` (para `make admin`), `TURNSTILE_*`, `WHATSAPP_NEGOCIO`, `NOMBRE_NEGOCIO`, `PROXY_SHARED_SECRET`/`TRUST_PROXY` y las de Cloudflare (`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `WORKER_NOMBRE`). La impresora **no** se configura aquí (ver arriba). De Spoolman: `SPOOLMAN_BIND_IP` (IP de WireGuard en que se publica; **nunca** `0.0.0.0`), `SPOOLMAN_PORT` (7912), `SPOOLMAN_WEB` (enlace «Abrir Spoolman» del panel), `SPOOLMAN_URL` (por defecto `http://spoolman:8000`) y `SPOOLMAN_AUTOCREAR` (`1`: registra solas las bobinas con chip). `BAMBU_NUBE_DIAS` (7) son los días de historial de Bambu Cloud. El `.env` no se versiona y trae secretos (contraseñas, token de Cloudflare): `chmod 600` y rótalos si alguna vez pasan por un chat o un ticket.
