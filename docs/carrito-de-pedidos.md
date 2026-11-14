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
