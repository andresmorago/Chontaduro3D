# Inventario por color

Un artículo puede ofrecerse en colores (**Artículos → editar → Colores disponibles**). Cuando los tiene, el
inventario se lleva **por color**: cada pieza producida, vendida o ajustada pertenece a un color, y el stock
total del artículo es la suma de los colores.

## Reglas

| Operación | Artículo **con** colores | Artículo **sin** colores |
| --- | --- | --- |
| Producir (Producción, editar lote, importar un trabajo de la impresora) | Hay que elegir el color de cada línea. | No lleva color. |
| Vender | Hay que elegir el color; el stock se valida **por color** (error: «Llavero (Azul): pides 2, hay 1»). | Como siempre. |
| Anular una venta | La pieza vuelve al **mismo color** de donde salió. | Como siempre. |
| Corregir el conteo (ajuste) | Hay que elegir el color. | Como siempre. |
| Editar un lote | Se ajusta cada color por la diferencia; no se puede bajar un color por debajo de lo ya vendido de ese color. | Como siempre. |
| Quitar un color del artículo | **No se puede** si todavía tiene unidades: se ajusta a 0 antes (Inventario → Corregir el conteo). | — |
| Renombrar o reordenar un color | Conserva su stock y su foto (el color tiene un id estable). | — |

El catálogo público nunca muestra cifras: solo «Disponible / Sobre pedido» por color.

## Stock «sin color asignado»

Los artículos que ya tenían stock **antes** de existir los colores (o antes de que se les agregaran) no se reescriben:
ese stock queda como **«sin color asignado»**. Mientras haya:

- Se puede **vender** (aparece como una fila más en *Vender*).
- Se puede **restar** con un ajuste. Para reasignarlo a un color: ajuste −N «sin color asignado» y ajuste +N en el color.
- **No** se puede sumar ni producir «sin color»: siempre hay que elegir un color.

## Datos

- `movimientos_inventario.color_id`, `produccion_items.color_id`, `venta_items.color_id` (FK a `articulo_colores`,
  `ON DELETE SET NULL`). `NULL` = artículo sin colores o stock sin color asignado.
- Migración `k1a8b4c6d2e7` (idempotente, reversible): solo agrega columnas; no reescribe datos.
- API: `GET /api/articulos` y `/api/inventario` traen `stock_colores` (`color_id`, `nombre`, `hex`, `stock`);
  producción, ventas y ajustes reciben `color_id` por línea; el kardex y los lotes devuelven el nombre del color.
- Pruebas: `backend/tests/test_inventario_color.py`.
