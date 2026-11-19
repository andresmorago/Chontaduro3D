# Carrito de pedidos (catálogo público)

El cliente puede pedir **varios artículos y colores en un solo pedido**.

## Flujo del cliente

1. Toca un artículo → ficha ampliada (foto, descripción, precio, «Disponible / Sobre pedido» del color elegido).
2. Elige **color** (si el artículo tiene) y **cantidad** (se puede escribir) → **Agregar al pedido**.
3. Sigue mirando el catálogo: arriba aparece **Mi pedido (N)** y abajo una barra con las piezas y el total.
4. **Mi pedido**: lista de renglones (foto, color, precio, cantidad editable, *Quitar*), total estimado, nombre y WhatsApp
   (+ verificación de Cloudflare). **Enviar pedido**.

El carrito se guarda en el navegador (`localStorage`, clave `mi_pedido_v1`) y sobrevive a recargar la página. Solo guarda
(artículo, color, cantidad): nombres, precios y fotos se leen siempre del catálogo vigente, y un artículo retirado desaparece
solo del carrito. Si el navegador no permite almacenar (modo privado), funciona igual mientras la página siga abierta.

Límites: hasta 20 renglones distintos y 99 piezas por renglón. El mismo artículo y color agregado dos veces se suma.

## API

`POST /api/publico/pedidos`:

```json
{ "nombre": "Ana", "whatsapp": "300 123 4567",
  "items": [ { "articulo_id": "…", "color": "Azul", "cantidad": 2 },
             { "articulo_id": "…", "cantidad": 1 } ],
  "sitio_web": "", "turnstile": "…" }
```

- Se valida **todo antes de guardar**: si un renglón falla (artículo oculto, falta el color) no se guarda nada.
- El formato anterior (`articulo_id`, `cantidad`, `color` sueltos) sigue aceptándose como un pedido de un renglón.
- Siguen los límites anti-abuso (por origen y globales) y Turnstile; **no toca el inventario**.

## Panel

**Pedidos** muestra un pedido por cliente con sus renglones, las piezas y el **total estimado a precios de hoy** (el precio
final se acuerda al vender). El mensaje de WhatsApp lista todos los renglones.

## Datos

- Tabla `pedido_items` (pedido, artículo, color como texto, cantidad). Migración `l2b9c5d7e3f8` (idempotente): copia cada pedido
  existente como un renglón; las columnas antiguas de `pedidos` (`articulo_id`, `cantidad`, `color`) quedan deprecadas y opcionales.
  Revertir la migración conserva el primer renglón de cada pedido.
- Pruebas: `backend/tests/test_carrito.py` y el recorrido `make e2e`.

## Atender un pedido con una venta

Una venta puede asociarse (opcionalmente) a un pedido, y así el pedido se cierra con la venta realizada.

- **Desde Pedidos**: *Atender con una venta* abre `/panel/vender?pedido=<id>`; Vender carga los renglones del pedido
  (el color se busca por nombre; la cantidad se limita a lo que hay), pone el cliente y marca *Cerrar el pedido al
  registrar la venta*. Lo que no se pueda cargar (color por elegir, sin stock) se avisa en pantalla.
- **Desde Vender**: el selector *Pedido que atiendes (opcional)* lista los pedidos «nuevo» y «contactado». Si la venta
  está vacía se cargan sus artículos; si ya tenía líneas no se pisan (botón *Cargar los artículos del pedido*).
- **API**: `POST /api/ventas` acepta `pedido_id` y `cerrar_pedido`. Solo se asocian pedidos nuevos o contactados
  (409 si ya están cerrados o descartados, 422 si no existe). Si no se escribe cliente, se usa el nombre del pedido.
  Un pedido puede tener varias ventas (entregas parciales): `cerrar_pedido` decide cuándo se cierra.
- **Qué NO hace**: asociar no cambia el inventario (lo mueve la venta, como siempre) ni el precio (la venta usa el
  precio de hoy o el que escribas). **Anular** una venta no reabre el pedido: la tarjeta del pedido marca la venta
  como anulada y no la cuenta en *Vendido*; el estado se cambia a mano.
- Datos: `ventas.pedido_id` (FK, `ON DELETE SET NULL`); `PedidoOut.ventas` y `total_vendido`; `VentaOut.pedido_id`
  y `pedido_nombre`.


## Por producir (demanda agrupada por artículo)

En **Pedidos → Por producir** se ve, por artículo (y por color), cuánto piden los pedidos *por
atender* (nuevos y contactados), cuánto hay en stock y **cuánto falta producir**
(`GET /api/pedidos/demanda`).

- Lo ya vendido a un pedido (ventas asociadas no anuladas) no cuenta como pendiente: esas piezas ya
  salieron del inventario. Anular la venta lo devuelve al pendiente.
- Los pedidos cerrados o descartados no cuentan.
- El stock «sin color asignado» de un artículo con colores cubre lo que falte de cualquiera de sus
  colores; por eso «Producir» del artículo puede ser menor que la suma de sus colores.
- No reserva inventario ni crea lotes: es solo una guía para planear la producción.
