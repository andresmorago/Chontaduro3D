# Spoolman: inventario de filamento

[Spoolman](https://github.com/Donkie/Spoolman) lleva las bobinas (marca, material, color, precio, gramos que quedan).
Mis impresiones y Spoolman se hablan siempre: **todo lo que imprime la impresora descuenta filamento de la bobina
correspondiente**, se importe o no como lote de producción.

## Qué hace

| Quién | Hace |
| --- | --- |
| **Spoolman** | Guarda las bobinas y cuánto queda de cada una. Se abre desde la red de casa. |
| **Servicio `impresora`** | Anota qué ranura del AMS usó cada trabajo; al terminar, resuelve de qué bobina salió el filamento y lo descuenta (`PUT /spool/{id}/use`). Es el **único** que escribe en Spoolman: así un descuento no se manda dos veces. |
| **Backend + panel** | Muestran el estado, dejan elegir qué bobina hay en cada ranura y resolver los descuentos que no se pudieron decidir solos (Administración → Impresora → *Filamento*). |

## Cómo se sabe de qué bobina salió el filamento

El `.3mf` dice cuántos gramos de cada filamento, pero **no en qué ranura iba** (la A1 no informa el mapeo del trabajo).
Por eso el servicio guarda, mientras el trabajo corre, las ranuras en las que estuvo la impresora (`tray_now`) y las
empareja con los filamentos por tipo y color (`app/spoolman/asignacion.py`). Si hay cualquier duda **no adivina**: la
línea queda «Falta elegir la bobina» y se resuelve en el panel.

- **Bobina Bambu con chip RFID**: se vincula **una vez** (el UID del chip queda guardado dentro de Spoolman, como *tag*
  de la bobina). Desde entonces se reconoce sola en cualquier ranura.
- **Bobina sin chip**: se elige a mano para esa ranura. Se guarda con el tipo y color que mostraba; si la ranura cambia
  de filamento, el panel pregunta «¿sigue siendo esta bobina?» en vez de asumirlo.
- **Trabajo cortado**: descuenta solo la parte hecha (`gramos × progreso`). Sin dato de avance no descuenta nada.
- **Solo lo que termina después de conectar Spoolman**: lo impreso antes no se descuenta con retraso (`spoolman_estado.desde`).

## Ciclo de un descuento (`consumos_filamento`)

```
sin_bobina ──(elige bobina / se vincula el chip)──▶ por_enviar ──▶ enviando ──▶ descontado
    │                                                                  └─ se cortó a medias ─▶ revisar
    └──▶ omitido (pruebas, fallos)
```

- Se marca `enviando` **antes** de llamar a Spoolman y `descontado` justo después. Si el proceso muere en medio, queda
  `revisar`: *no se reenvía solo*, porque pudo haberse aplicado. En el panel: «Ya se descontó» o «Descontar otra vez».
- Si Spoolman no se alcanza (la petición ni salió), se reintenta solo sin contar intentos.
- Si Spoolman responde error de servidor, 5 reintentos; si responde un 4xx o no se ve la respuesta, va a `revisar`.

## Red y seguridad

Spoolman **no tiene autenticación**. Capas, de fuera hacia dentro:

1. No pasa por el Worker/túnel de Cloudflare (el frontend no lo conoce).
2. Se publica **solo en la IP de WireGuard del servidor** (`SPOOLMAN_BIND_IP=10.6.0.6`, nunca `0.0.0.0`).
3. El cortafuegos (`ops/spoolman-firewall.sh`, regla en `DOCKER-USER`) solo acepta conexiones **nuevas** al puerto 7912
   que entren por `wg0` y vengan de la LAN de casa `10.0.4.0/24`; el resto se descarta.
4. El contenedor corre sin privilegios (`cap_drop: ALL`, `no-new-privileges`) con el usuario del anfitrión.

Se abre desde casa en `http://10.6.0.6:7912`.

### Instalar o reaplicar el cortafuegos

```bash
make spoolman-firewall          # copia el script y la unidad systemd (root), la habilita y la aplica
make spoolman-firewall-estado   # muestra las reglas y los paquetes aceptados/descartados
```

La unidad `spoolman-firewall.service` corre después de Docker (y cuando Docker se reinicia). El script es idempotente.
Para cambiar quién entra: `SPOOLMAN_ALLOWED` / `SPOOLMAN_IFACE` / `SPOOLMAN_PORT` (ver el encabezado del script).
No se usa `netfilter-persistent save`: `rules.v4` guarda también las cadenas dinámicas de Docker.

> Si el servidor arranca y Docker intenta publicar el puerto antes de que exista `wg0`, el contenedor no puede enlazar
> la IP `10.6.0.6` y `restart: always` lo reintenta hasta que la interfaz esté arriba.

## Registro de bobinas (casi no hay que hacerlo a mano)

- **Bobinas Bambu con chip RFID: se registran solas, sin duplicarse.** Cuando un chip aparece en el AMS y se ve estable
  ~15 s, el servicio decide así:
  1. **Su chip ya está vinculado a una bobina** (aunque esté archivada): no hace nada.
  2. **Ya se leyó antes** (queda guardado en la tabla `chips_bobina`) **pero su bobina ya no está en Spoolman**, porque se
     borró: **no la vuelve a crear**. Quitar el rollo y volver a ponerlo, o reiniciar el servicio, tampoco duplica. Avisa en
     el registro; si de verdad quieres la bobina de nuevo, créala con *Crear en Spoolman* en su ranura (eso sí se permite).
  3. **Es nuevo y existe UNA bobina de Bambu Lab sin chip con el mismo material y color**: le **vincula el chip** (la
     «adopta») en vez de crear otra. Así lo que registraste a mano desde el catálogo no se duplica.
  4. **Es nuevo y hay varias que podrían ser** (p. ej. dos rojas sin chip): no adivina ni crea; si una de ellas ya figura en
     esa ranura, gana esa. Si no, elige cuál en el panel (*Elegir existente*).
  5. **Es nuevo y no hay candidata**: crea la bobina (proveedor *Bambu Lab*, marca/material/color/peso del chip) y le
     vincula el chip. Si el chip informa entre 1 y 99 % restante, la crea con ese consumo.
  Apágalo con `SPOOLMAN_AUTOCREAR=0` si prefieres crearlas tú.
- **Para quitar una bobina, archívala, no la borres.** Archivada, su chip se sigue reconociendo y nada se recrea.
- **Ubicaciones al día.** Cada ~30 s el servicio escribe en cada bobina la ranura en que está puesta («AMS · Ranura 2») y
  borra la de las que salieron del AMS (con los dos pasos de confirmación: solo cambia si ve lo mismo dos veces seguidas, y
  no toca nada si la impresora no informa el AMS). **Solo toca ubicaciones vacías o que empiecen por «AMS · »**: lo que
  pongas a mano («Estante A») se respeta. Funciona también para las bobinas sin chip vinculadas a mano a una ranura.
- **Bobinas sin chip: un clic por ranura.** En el panel, *Crear en Spoolman* en la ranura: pide el peso, **cuánto queda** (para
  rollos ya gastados) y el precio (opcional), y la crea con el material y color de la ranura.
- **Filamentos compartidos**: varias bobinas iguales (mismo proveedor, nombre, material y color) comparten el filamento. Pon el
  **precio una vez** en el filamento (Spoolman → Filaments) y las bobinas nuevas lo heredan.
- Lo que ya existe en Spoolman se puede asociar con *Elegir existente*.

## Primeros pasos

1. Carga el AMS: las bobinas con chip aparecen solas en Spoolman; para las demás usa *Crear en Spoolman* en su ranura.
2. Ajusta lo que quede de cada rollo (en el panel al crear, o en Spoolman → Edit spool → *Remaining weight*), y los precios.
3. Listo: el siguiente trabajo que termine descuenta solo. Lo que no se pueda decidir aparece en *Descuentos por resolver*.

## Configuración

| Variable | Dónde | Para qué |
| --- | --- | --- |
| `SPOOLMAN_URL` | backend e `impresora` | Dirección interna (`http://spoolman:8000`). Vacía = integración apagada. |
| `SPOOLMAN_WEB` | backend | Enlace «Abrir Spoolman» del panel. No se usa para conectar. |
| `SPOOLMAN_AUTOCREAR` | backend e `impresora` | `1` (por defecto): registra solas las bobinas Bambu con chip. |
| `SPOOLMAN_AUTOVINCULAR` | `impresora` | `1` (por defecto): une solos los rollos sin chip cuando hay una única candidata. |
| `SPOOLMAN_BIND_IP` / `SPOOLMAN_PORT` | compose | IP y puerto en que se publica en el anfitrión. |

## Datos, respaldos y actualización

- Datos en `data/spoolman/` (SQLite). Spoolman hace respaldos automáticos diarios en `data/spoolman/backups/`.
  Incluye esa carpeta en tus copias del servidor.
- La versión de la imagen está fijada en `docker-compose.prod.yml` (`ghcr.io/donkie/spoolman:0.27.1`). Para actualizar:
  cambia el número, `make prod-up`, y revisa las [notas de versión](https://github.com/Donkie/Spoolman/releases).
- Los gramos descontados viven en Spoolman; en Mis impresiones queda el registro por trabajo (`consumos_filamento`).

## Producción ↔ Spoolman (el filamento de un lote)

Cada línea de filamento de un lote (Producción → *Filamento y tiempo → Por filamento*) puede **apuntar a una bobina**
de Spoolman en vez de ser texto libre:

- **Elegir la bobina**: el selector lista las bobinas activas (primero las del AMS, con lo que queda de cada una). *Otro
  (escribir a mano)* deja el texto libre de siempre (los lotes viejos como «PLA Fucsia» siguen funcionando).
- **El nombre es el de Spoolman, en vivo**: si renombras o archivas una bobina allí, todos los lotes que la usan muestran el
  nombre nuevo. Al guardar también queda una copia del nombre por si Spoolman no responde (entonces se ve esa copia).
- **Importar un trabajo de la impresora**: si Spoolman ya descontó ese filamento de una bobina, la línea **viene con esa
  bobina y con los gramos descontados**, así el lote y Spoolman dicen lo mismo. Las que no tengan descuento (trabajos de
  antes de conectar Spoolman, o filamentos sin bobina asignada) vienen como texto, para que elijas la bobina si quieres.
- **Elegir una bobina en un lote NO descuenta nada**: descontar sigue siendo cosa del servicio `impresora` (así no se
  cuenta dos veces). El vínculo sirve para identificar y para que Producción y Spoolman hablen de la misma bobina. Un lote
  que no viene de la impresora no mueve Spoolman.
- **Se puede citar una bobina archivada** (un rollo terminado). Al corregir un lote viejo no se exige que sus bobinas
  sigan existiendo: solo se valida lo que cambias. Si Spoolman está apagado no hay selector y todo sigue como texto.
- Datos: `produccion_filamentos.spool_id` (sin clave foránea: Spoolman es otro sistema). API: `filamentos[].spool_id` al
  guardar; al leer trae además `bobina` y `color` (los actuales de Spoolman).

## Consumo estimado de lo ya impreso

Lo impreso antes de conectar Spoolman no descuenta solo. Para repartirlo entre las bobinas una vez registradas:

```bash
docker exec misimpresiones-prod-impresora-1 python -m app.spoolman.historial            # vista previa (no cambia nada)
docker exec misimpresiones-prod-impresora-1 python -m app.spoolman.historial --aplicar --mapa "PLA#ffffff=3,PLA#c12e1f=7"
```

Suma los gramos por tipo y color y sugiere la bobina de ese color. Es una **estimación**: el color del `.3mf` es el del
programa de laminado (no siempre el del rollo) y un color pudo salir de varios rollos, por eso se confirma antes de
aplicar con `--mapa`. Sin `--mapa`, `--aplicar` usa lo sugerido y **se salta las bobinas que ya tienen consumo** (para no
contarlo dos veces; `--incluir-gastadas` lo fuerza). Crea un descuento por trabajo que envía el servicio; repetirlo no
duplica nada (un trabajo con descuentos ya no se cuenta de nuevo).

## Gramos: de dónde salen y por qué pueden cambiar

Un trabajo detectado en vivo toma sus gramos del `.3mf` que está en la impresora (se busca primero el archivo con el
**nombre exacto** que informa la impresora, en `/` y en `/cache`). Unos minutos después, si el trabajo también está en
Bambu Cloud, los gramos de la nube (los que muestra Bambu web) **corrigen** esos datos. Lo ya descontado en Spoolman no
se reescribe solo: si un trabajo se descontó con un peso distinto del definitivo, se corrige con una línea de ajuste en
`consumos_filamento` (así queda el rastro). El servicio avisa en el registro cuando un trabajo dura mucho más o menos de
lo que decía su archivo, que es la señal de un archivo equivocado.

## Desde el panel, sin entrar a Spoolman

Todo esto está en **Administración → Impresora → Filamento**, y usa la API de Spoolman por detrás.

- **Ajustar un rollo.** El botón *Ajustar* de una ranura o de un repuesto deja corregir **cuánto queda** (el peso del filamento, sin el
  carrete: si pesas el rollo, réstale el carrete vacío) y el **precio**. También *Archivar (se terminó)*: sale de las listas pero su chip
  se sigue reconociendo, así que no se vuelve a registrar. API: `PATCH /api/spoolman/bobinas/{id}` con `restante_g`, `precio`, `archivar`.
- **Rollos de repuesto.** Los rollos activos de Spoolman que **no** están puestos en el AMS, con los más bajos primero. «Queda poco» es por
  debajo de **150 g** (`BAJO_G` en `backend/app/api/spoolman.py`). Un rollo cuenta como «en el AMS» si está en una ranura ahora o si su
  ubicación empieza por «AMS · ». API: `GET /api/spoolman/repuestos`.
- **¿Alcanza el filamento para este trabajo?** Va dentro de cada ranura de «En la impresora ahora» (no es una sección aparte): mientras se imprime, compara los gramos de cada filamento del `.3mf` con lo que queda en la bobina
  de la ranura que le corresponde (por tipo y color, con la misma regla conservadora de siempre: con duda no opina). Estados: *alcanza*, *va justo*
  (sobran menos de 15 g: los gramos del archivo son estimados), *no alcanza* (alerta roja), y *no sé* si la ranura no está unida a una bobina, la
  bobina no tiene peso o hay dos ranuras parecidas. Spoolman descuenta al terminar, así que lo que queda allí es lo de antes del trabajo y por eso se
  compara con los gramos completos. API: `GET /api/spoolman/alcance`.

## Releer el chip RFID de una ranura

El botón **Releer chip** de cada ranura del AMS hace lo mismo que el botón de actualizar de Bambu Studio: manda a la impresora el G-code
`M620 R<ranura>` (`gcode_line`), y el AMS vuelve a leer la etiqueta de esa bobina. La impresora informa el resultado sola (color, tipo y UID del chip);
en unos segundos se ve en el panel y, si es una bobina nueva, el registro automático la crea en Spoolman.

- **Solo mientras NO se imprime** (preparando, imprimiendo o en pausa se desactiva). **No hay que descargar el rollo que está en uso**: igual que en
  Bambu Studio, se puede releer con el filamento cargado.
- **Se ve el código.** Cada ranura con chip muestra su UID (código RFID) junto a la bobina. Al pulsar *Releer chip* aparece «Leyendo…» y, a los pocos
  segundos, «Chip leído: <UID>» con un botón para copiarlo; si la impresora no detecta nada lo dice (rollo sin chip o mal asentado).
- Sin chip (rollos no Bambu) no hay nada que leer: esas bobinas se asocian a mano.
- **Puede ser rechazada.** Va por el mismo canal que las demás órdenes (G-code `M620`), y los firmwares con control de autorización rechazan las órdenes no firmadas. El servicio espera la
  respuesta de la impresora (o su aviso HMS de verificación) y el panel muestra el motivo en vez de quedarse esperando. Lo mismo aplica a pausar, luz, velocidad, temperaturas y ventiladores.
- Es una orden más del panel (`leer_rfid`, ver «Controles»): el backend la deja en `impresora_comandos` y el servicio la envía; queda en la auditoría.
- Fuente del comando: `MachineObject::command_ams_refresh_rfid` y `StatusPanel::on_ams_refresh_rfid` de Bambu Studio (código abierto). Para impresoras
  de la plataforma nueva (H2D) Studio usa otra orden (`ams_get_rfid`); la A1 usa el G-code.

## Cuando el rollo cambia (o llega uno nuevo desde la impresora)

**La impresora manda en lo que hay cargado; Spoolman lleva el inventario.** Para cambiar un rollo lo cargas en la impresora (o en Bambu Studio) y la app lo ve sola. Esta
app **no escribe el filamento en el AMS**: el firmware de la A1 solo acepta esas órdenes si van firmadas por Bambu Studio o Handy y, si no, muestra
`HMS_0500-0500-0001-0007 «MQTT Command verification failed»`. Activar el Modo LAN + Modo desarrollador lo evitaría, pero desconecta la impresora de la nube de Bambu
(Handy a distancia y el historial de Bambu Cloud que alimenta los gramos reales), así que no se usa.

| Situación | Qué pasa |
| --- | --- |
| **Rollo Bambu con chip** entra al AMS | La impresora lo lee; en unos segundos se registra solo en Spoolman (o se «adopta» una bobina sin chip del mismo material y color). Si no se lee, *Releer chip*. |
| **Rollo sin chip** (Sunlu, etc.) configurado en la impresora | Aparece en la ranura con el color y material que le pusiste. Pasados ~15 s estables, si en Spoolman hay **una sola** bobina del mismo material base (PLA+ y PLA Basic cuentan como PLA), con color parecido (cercano en RGB o del mismo tono: el violeta que eliges en la paleta de la impresora rara vez coincide con el de Spoolman), sin chip y que no esté en otra ranura, **se une sola** (`SPOOLMAN_AUTOVINCULAR`). Con dos candidatas o ninguna, el panel pregunta («Sí, es «…»») o deja *Crear en Spoolman*. |
| **El rollo de una ranura sin chip cambia** | El vínculo anterior queda «desactualizado» y su ubicación en Spoolman se limpia. Si la bobina vinculada sigue siendo del mismo material y de un color parecido al nuevo (cambiaste el color de la ranura en Bambu Studio), el vínculo se **confirma solo**; si no, se repite lo de arriba con el rollo nuevo. |
| **Cambias la bobina desde el panel** (*Cambiar de bobina*) | Spoolman queda al día (ubicación y consumo). La impresora no se entera: la fila muestra el color de la bobina elegida y una etiqueta «la impresora lo ve así» si el de la impresora es muy distinto. |

**Actividad reciente** (desplegable bajo «En la impresora ahora»): cambios de rollo que vio la app («Ranura 3: PLA negro → PLA violeta») y lo que hizo en Spoolman (rollo unido solo, registrado,
adoptado, ajustado). Sale de la auditoría (`ams_cambio`, `spoolman_ranura_autovinculada`, …); API: `GET /api/spoolman/actividad?limite=20`. Una ranura debe verse igual ~15 s para contar como cambio;
al arrancar el servicio solo se toma la foto inicial.

## Costo del filamento de un lote

Cada línea de filamento de un lote que apunta a una bobina con **precio** guarda su costo: `gramos × precio del rollo ÷ gramos del rollo`.

- **Se congela al guardar** (`produccion_filamentos.costo`), igual que el precio de una venta y la energía: si el rollo sube de precio después,
  los lotes viejos no cambian. Al corregir un lote, una línea que no cambió (misma bobina y mismos gramos) conserva su costo; si cambias los gramos o la
  bobina, se recalcula con el precio de hoy.
- El lote muestra la suma (`costo_filamento`). Si alguna línea no tiene precio (texto libre, o una bobina sin precio) el costo se marca como **parcial**
  («≥ $…»): el real es mayor. Pon el precio en el rollo (*Ajustar*) o una vez en el filamento de Spoolman y las bobinas nuevas lo heredan.
- La moneda es la que uses en Spoolman: la app la muestra como pesos.

## Qué no hace (todavía)

- No sincroniza el «restante» que mide el AMS en las bobinas con chip hacia Spoolman (en tu A1 todas las ranuras informan 100 %, así que no aporta).
- No avisa por fuera del panel (correo, WhatsApp) cuando un rollo queda bajo: el aviso solo se ve en la página.
- No mezcla el costo del filamento con el de energía en un solo «costo del lote»: se muestran por separado.

## Pruebas

`backend/tests/test_spoolman.py` (incluye ajustar rollos, repuestos y «¿alcanza?») y `backend/tests/test_produccion_bobinas.py` (costo del filamento): emparejamiento (lógica pura), cliente HTTP con transporte simulado, el flujo completo
del servicio contra Postgres con un Spoolman de mentira (descuento único, caída de Spoolman, respuesta perdida, trabajo
cortado…) y la API. El cliente también se probó contra un Spoolman real.
