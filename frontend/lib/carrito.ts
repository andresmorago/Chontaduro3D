"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ArticuloPublico, ColorPublico } from "./types";

/** Lo único que se guarda en el navegador: qué artículo, de qué color y cuántas. Nombres, precios y fotos
 *  se leen siempre del catálogo vigente (así un cambio de precio o un artículo retirado se refleja). */
export interface Renglon {
  articuloId: string;
  /** Nombre del color; vacío si el artículo no tiene colores. */
  color: string;
  cantidad: number;
}

export interface LineaCarrito extends Renglon {
  articulo: ArticuloPublico;
  colorInfo: ColorPublico | null;
}

const LLAVE = "mi_pedido_v1";
export const MAX_RENGLONES = 20;
export const MAX_CANTIDAD = 99;

const mismo = (a: Renglon, articuloId: string, color: string) => a.articuloId === articuloId && a.color === color;

function leer(): Renglon[] {
  try {
    const crudo = window.localStorage.getItem(LLAVE);
    if (!crudo) return [];
    const datos: unknown = JSON.parse(crudo);
    if (!Array.isArray(datos)) return [];
    return datos
      .filter((r): r is Renglon => typeof r?.articuloId === "string" && typeof r?.color === "string" && Number.isInteger(r?.cantidad) && r.cantidad >= 1 && r.cantidad <= MAX_CANTIDAD)
      .slice(0, MAX_RENGLONES);
  } catch {
    return []; // sin almacenamiento (modo privado) o datos dañados: se empieza vacío
  }
}

/** El mini carrito del catálogo: renglones (artículo + color + cantidad) que persisten en el navegador. */
export function useCarrito(articulos: ArticuloPublico[]) {
  const [renglones, setRenglones] = useState<Renglon[]>([]);
  const [listo, setListo] = useState(false);

  useEffect(() => {
    setRenglones(leer());
    setListo(true);
  }, []);

  useEffect(() => {
    if (!listo) return;
    try {
      window.localStorage.setItem(LLAVE, JSON.stringify(renglones));
    } catch {
      /* sin almacenamiento: el carrito funciona igual mientras la página siga abierta */
    }
  }, [renglones, listo]);

  // Solo cuentan los renglones cuyo artículo (y color) siguen en el catálogo.
  const lineas = useMemo<LineaCarrito[]>(
    () =>
      renglones.flatMap((r) => {
        const articulo = articulos.find((a) => a.id === r.articuloId);
        if (!articulo) return [];
        const colorInfo = articulo.colores.find((c) => c.nombre === r.color) ?? null;
        if (articulo.colores.length > 0 && !colorInfo) return [];
        return [{ ...r, articulo, colorInfo }];
      }),
    [renglones, articulos],
  );

  const agregar = useCallback((articuloId: string, color: string, cantidad: number) => {
    setRenglones((rs) => {
      const i = rs.findIndex((r) => mismo(r, articuloId, color));
      if (i >= 0) return rs.map((r, j) => (j === i ? { ...r, cantidad: Math.min(MAX_CANTIDAD, r.cantidad + cantidad) } : r));
      if (rs.length >= MAX_RENGLONES) return rs;
      return [...rs, { articuloId, color, cantidad: Math.min(MAX_CANTIDAD, cantidad) }];
    });
  }, []);

  const poner = useCallback((articuloId: string, color: string, cantidad: number) => {
    setRenglones((rs) => (cantidad <= 0 ? rs.filter((r) => !mismo(r, articuloId, color)) : rs.map((r) => (mismo(r, articuloId, color) ? { ...r, cantidad: Math.min(MAX_CANTIDAD, cantidad) } : r))));
  }, []);

  const vaciar = useCallback(() => setRenglones([]), []);

  const piezas = lineas.reduce((s, l) => s + l.cantidad, 0);
  const total = lineas.reduce((s, l) => s + l.articulo.precio * l.cantidad, 0);
  return { lineas, agregar, poner, vaciar, piezas, total, lleno: renglones.length >= MAX_RENGLONES };
}
