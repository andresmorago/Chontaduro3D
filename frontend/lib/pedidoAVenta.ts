import { clave, nombreColor, stockDe } from "./lineas";
import type { Articulo, Pedido } from "./types";

export interface LineaVenta {
  cantidad: number;
  precio: number | null; // null = precio de la lista
}

/** Convierte lo pedido en líneas de venta: cada renglón (artículo, color) pasa a su clave, con el color
 *  buscado por nombre y la cantidad limitada a lo que hay. Lo que no se pueda cargar se avisa en
 *  `avisos` (color por elegir, sin stock…) para que la persona lo resuelva a mano. */
export function lineasDePedido(p: Pedido, porId: Map<string, Articulo>): { lineas: Record<string, LineaVenta>; avisos: string[] } {
  const lineas: Record<string, LineaVenta> = {};
  const avisos: string[] = [];
  for (const i of p.items) {
    const a = porId.get(i.articulo_id);
    if (!a) {
      avisos.push(`${i.articulo} ya no está disponible.`);
      continue;
    }
    let colorId: string | null = null;
    if (a.colores.length > 0) {
      const c = a.colores.find((x) => x.nombre.toLowerCase() === (i.color ?? "").toLowerCase());
      if (!c) {
        avisos.push(`De ${a.nombre} falta elegir el color (${i.cantidad} pedidas).`);
        continue;
      }
      colorId = c.id;
    }
    const k = clave(a.id, colorId);
    const nombre = `${a.nombre}${colorId ? ` (${nombreColor(a, colorId)})` : ""}`;
    const hay = Math.max(0, stockDe(a, colorId) - (lineas[k]?.cantidad ?? 0));
    const n = Math.min(i.cantidad, hay);
    if (n <= 0) {
      avisos.push(`De ${nombre} no queda stock (${i.cantidad} pedidas).`);
      continue;
    }
    if (n < i.cantidad) avisos.push(`De ${nombre} solo quedan ${n} de ${i.cantidad} pedidas.`);
    lineas[k] = { cantidad: (lineas[k]?.cantidad ?? 0) + n, precio: null };
  }
  return { lineas, avisos };
}
