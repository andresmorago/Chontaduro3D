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
