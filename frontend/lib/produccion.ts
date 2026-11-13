import type { ExtraProduccion, Parametros } from "./types";

export type ModoFilamento = "total" | "por_filamento";

/** Lo que se escribe en el formulario del lote (todo texto: lo valida y convierte `aExtra`). */
export interface EstadoLote {
  modo: ModoFilamento;
  total: string;
  filamentos: { descripcion: string; gramos: string }[];
  horas: string;
  minutos: string;
}

export const loteVacio = (): EstadoLote => ({
  modo: "total",
  total: "",
  filamentos: [{ descripcion: "", gramos: "" }],
  horas: "",
  minutos: "",
});

const num = (s: string): number => (s.trim() === "" ? NaN : Number(s.replace(",", ".")));

export function minutosDe(e: EstadoLote): number {
  const h = e.horas.trim() === "" ? 0 : num(e.horas);
  const m = e.minutos.trim() === "" ? 0 : num(e.minutos);
  return Math.round(h * 60 + m);
}

export function totalGramos(e: EstadoLote): number | null {
  if (e.modo === "total") {
    const t = num(e.total);
    return Number.isFinite(t) && t > 0 ? t : null;
  }
  const s = e.filamentos.reduce((acc, f) => acc + (Number.isFinite(num(f.gramos)) ? num(f.gramos) : 0), 0);
  return s > 0 ? Math.round(s * 100) / 100 : null;
}

/** Convierte el formulario en lo que espera la API, o devuelve el mensaje del primer problema. */
export function aExtra(e: EstadoLote): { extra: ExtraProduccion } | { error: string } {
  const extra: ExtraProduccion = {};
  if (e.modo === "total") {
    if (e.total.trim() !== "") {
      const t = num(e.total);
      if (!Number.isFinite(t) || t <= 0) return { error: "Los gramos totales deben ser un número mayor que 0." };
      extra.gramos_total = t;
    }
  } else {
    const llenas = e.filamentos.filter((f) => f.gramos.trim() !== "" || f.descripcion.trim() !== "");
    for (const f of llenas) {
      const g = num(f.gramos);
      if (!Number.isFinite(g) || g <= 0) return { error: `Pon los gramos de «${f.descripcion.trim() || "cada filamento"}» (mayor que 0).` };
    }
    if (llenas.length > 0) extra.filamentos = llenas.map((f) => ({ descripcion: f.descripcion.trim(), gramos: num(f.gramos) }));
  }
  if (e.horas.trim() !== "" || e.minutos.trim() !== "") {
    const h = e.horas.trim() === "" ? 0 : num(e.horas);
    const m = e.minutos.trim() === "" ? 0 : num(e.minutos);
    if (!Number.isFinite(h) || !Number.isFinite(m) || h < 0 || m < 0) return { error: "El tiempo debe tener horas y minutos válidos." };
    const total = minutosDe(e);
    if (total < 1) return { error: "El tiempo de impresión debe ser de al menos 1 minuto." };
    if (total > 60 * 24 * 30) return { error: "El tiempo de impresión no puede pasar de 30 días." };
    extra.minutos_impresion = total;
  }
  return { extra };
}

/** Vista previa de energía con los parámetros vigentes (el servidor calcula y congela el valor real). */
export function energiaEstimada(minutos: number, p: Parametros | null): { kwh: number; costo: number | null } | null {
  if (!p?.potencia_impresora_w || !minutos) return null;
  const kwh = (p.potencia_impresora_w / 1000) * (minutos / 60);
  return { kwh, costo: p.precio_kwh != null ? kwh * p.precio_kwh : null };
}

export function tiempoLargo(min: number): string {
  const h = Math.floor(min / 60);
  const m = min % 60;
  if (h === 0) return `${m} min`;
  return m === 0 ? `${h} h` : `${h} h ${m} min`;
}

export const gramos = (g: number) => `${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 }).format(g)} g`;
export const kwhTexto = (k: number) => `${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 3 }).format(k)} kWh`;
