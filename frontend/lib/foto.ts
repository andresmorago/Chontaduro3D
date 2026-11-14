import type { CSSProperties } from "react";

/** Encuadre de una foto (no destructivo): centro horizontal y vertical en % de la foto, y zoom 1–4. */
export interface Encuadre {
  x: number;
  y: number;
  zoom: number;
}

export const CENTRADO: Encuadre = { x: 50, y: 50, zoom: 1 };
export const ZOOM_MIN = 1;
export const ZOOM_MAX = 4;

export const encuadreDe = (o: { foto_x: number; foto_y: number; foto_zoom: number }): Encuadre => ({ x: o.foto_x, y: o.foto_y, zoom: o.foto_zoom });
export const aCampos = (e: Encuadre) => ({ foto_x: redondear(e.x), foto_y: redondear(e.y), foto_zoom: redondear(e.zoom) });

export const acotar = (n: number, min: number, max: number) => Math.min(max, Math.max(min, n));
export const redondear = (n: number) => Math.round(n * 100) / 100;

/** Tamaño (en % del cuadro) que ocupa la foto: «cubrir» el cuadrado, multiplicado por el zoom. */
export function dimensiones(ratio: number, zoom: number) {
  return { ancho: Math.max(1, ratio) * zoom * 100, alto: Math.max(1, 1 / ratio) * zoom * 100 };
}

/** Estilo de la imagen dentro de un cuadro cuadrado: posición y tamaño en %, sin deformar la foto. */
export function geometria(ratio: number, e: Encuadre): CSSProperties {
  const { ancho, alto } = dimensiones(ratio, e.zoom);
  return { width: `${ancho}%`, height: `${alto}%`, left: `${((100 - ancho) * e.x) / 100}%`, top: `${((100 - alto) * e.y) / 100}%` };
}

/** Los .heic/.heif los lee el servidor, pero el navegador de escritorio no sabe mostrarlos. */
export const esHeic = (f: File) => /hei[cf]/i.test(f.type) || /\.hei[cf]$/i.test(f.name);
