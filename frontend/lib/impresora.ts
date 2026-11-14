import type { EstadoMaquina } from "./types";

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
