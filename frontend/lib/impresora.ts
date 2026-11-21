import type { ConsumoFilamento, EstadoConsumo, EstadoMaquina } from "./types";

export const ETIQUETA_ESTADO: Record<EstadoMaquina, string> = {
  lista: "Lista",
  preparando: "Preparando",
  imprimiendo: "Imprimiendo",
  pausada: "En pausa",
  terminada: "Terminada",
  fallida: "Fallida o cancelada",
  desconocido: "Sin datos",
};

export const VELOCIDADES: { valor: string; etiqueta: string }[] = [
  { valor: "1", etiqueta: "Silencioso" },
  { valor: "2", etiqueta: "Estándar" },
  { valor: "3", etiqueta: "Deportivo" },
  { valor: "4", etiqueta: "Ludicrous" },
];

export const grados = (t: number | null) => (t == null ? "—" : `${Math.round(t)} °C`);

export function restante(min: number | null): string {
  if (min == null) return "—";
  if (min < 1) return "menos de 1 min";
  const h = Math.floor(min / 60);
  const m = min % 60;
  return h === 0 ? `${m} min` : m === 0 ? `${h} h` : `${h} h ${m} min`;
}

export const ETIQUETA_CONSUMO: Record<EstadoConsumo, string> = {
  sin_bobina: "Falta elegir la bobina",
  por_enviar: "Descontando…",
  enviando: "Descontando…",
  descontado: "Descontado",
  omitido: "Omitido",
  revisar: "Por revisar",
};

/** Una línea para el trabajo: qué pasó con su filamento en Spoolman. `null` si no aplica. */
export function resumenConsumo(consumos: ConsumoFilamento[]): { texto: string; clase: "ok" | "aviso" | "tenue" } | null {
  if (consumos.length === 0) return null;
  const por = (e: EstadoConsumo) => consumos.filter((c) => c.estado === e).length;
  if (por("sin_bobina") + por("revisar") > 0) return { texto: "Spoolman: falta una decisión", clase: "aviso" };
  if (por("por_enviar") + por("enviando") > 0) return { texto: "Spoolman: descontando…", clase: "tenue" };
  if (por("descontado") > 0) return { texto: "Descontado en Spoolman", clase: "ok" };
  return { texto: "Spoolman: omitido", clase: "tenue" };
}

/** «#rrggbb» → fondo válido para una muestra de color, o undefined. */
export const muestra = (c: string | null) => (c && /^#[0-9a-f]{6}$/i.test(c) ? c : undefined);

export const gramosTexto = (g: number | null) => (g == null ? "—" : `${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 }).format(g)} g`);

/** Distancia entre dos colores «#rrggbb» (0–441); null si alguno no es válido. */
export function distanciaColor(a: string | null | undefined, b: string | null | undefined): number | null {
  const rgb = (c: string | null | undefined): [number, number, number] | null =>
    c && /^#[0-9a-f]{6}$/i.test(c) ? [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)] : null;
  const x = rgb(a), y = rgb(b);
  if (!x || !y) return null;
  return Math.hypot(x[0] - y[0], x[1] - y[1], x[2] - y[2]);
}

/** «PLA Basic» / «PLA-CF» / «pla+» → «pla»: el material base, para comparar el de la impresora con el de Spoolman. */
export const normTipo = (t: string | null | undefined): string => (t ?? "").match(/[A-Za-z]+/)?.[0].toLowerCase() ?? "";

/** Tono (0–360°) de un color con color propio; null para negros, blancos y grises. */
function tono(c: string | null | undefined): number | null {
  if (!c || !/^#[0-9a-f]{6}$/i.test(c)) return null;
  const r = parseInt(c.slice(1, 3), 16) / 255, g = parseInt(c.slice(3, 5), 16) / 255, b = parseInt(c.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
  if (max < 0.15 || (max === 0 ? 0 : d / max) < 0.2) return null;
  const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return (h * 60 + 360) % 360;
}

/** ¿Es el «mismo» color? Cerca en RGB o, para colores con color propio, del mismo tono (igual que el servicio). */
export function colorParecido(a: string | null | undefined, b: string | null | undefined): boolean {
  const d = distanciaColor(a, b);
  if (d === null) return false;
  if (d <= 48) return true;
  const ta = tono(a), tb = tono(b);
  if (ta === null || tb === null) return false;
  const dif = Math.abs(ta - tb);
  return Math.min(dif, 360 - dif) <= 28;
}
