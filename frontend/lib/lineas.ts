import type { Articulo } from "./types";

/** Una línea de producción o de venta es un (artículo, color): la clave las distingue. Un artículo
 *  sin colores usa color vacío. */
export const clave = (articuloId: string, colorId: string | null | undefined) => `${articuloId}|${colorId ?? ""}`;

export function partirClave(k: string): { articuloId: string; colorId: string | null } {
  const [articuloId = "", colorId = ""] = k.split("|");
  return { articuloId, colorId: colorId || null };
}

/** Unidades en inventario de un (artículo, color); sin color = el total de un artículo sin colores o el
 *  stock «sin color asignado» de uno con colores. */
export function stockDe(a: Articulo, colorId: string | null): number {
  if (a.colores.length === 0) return a.stock;
  return a.stock_colores.find((s) => s.color_id === colorId)?.stock ?? 0;
}

export const tieneColores = (a: Articulo) => a.colores.length > 0;
export const nombreColor = (a: Articulo, colorId: string | null) => (colorId ? (a.colores.find((c) => c.id === colorId)?.nombre ?? null) : null);
export const hexColor = (a: Articulo, colorId: string | null) => (colorId ? (a.colores.find((c) => c.id === colorId)?.hex ?? null) : null);
