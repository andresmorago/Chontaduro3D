import { hoyISO } from "./format";
import type { ExtraProduccion, Parametros, Produccion, TrabajoImpresora } from "./types";

export type ModoFilamento = "total" | "por_filamento";

/** Lo que se escribe en el formulario del lote (todo texto: lo valida y convierte `aExtra`). */
export interface EstadoLote {
  modo: ModoFilamento;
  total: string;
  filamentos: { descripcion: string; gramos: string }[];
  horas: string;
  minutos: string;
  /** Fecha de producción (YYYY-MM-DD): hoy, o una pasada para cargar lotes viejos. */
  fecha: string;
  /** false = carga histórica: solo historial y métricas, sin sumar al stock de hoy. */
  sumar: boolean;
  /** Energía propia de este lote (vacío = usar los parámetros de hoy). */
  precioPropio: string;
  potenciaPropia: string;
}

export const loteVacio = (fecha: string = hoyISO()): EstadoLote => ({
  modo: "total",
  total: "",
  filamentos: [{ descripcion: "", gramos: "" }],
  horas: "",
  minutos: "",
  fecha,
  sumar: true,
  precioPropio: "",
  potenciaPropia: "",
});

/** El formulario de un lote ya guardado, para corregirlo. La energía congelada se muestra como
 *  valores propios del lote: así quedan visibles y no se recalculan con los parámetros de hoy. */
export const loteDesde = (p: Produccion): EstadoLote => {
  const min = p.minutos_impresion;
  return {
    modo: p.filamentos.length > 0 ? "por_filamento" : "total",
    total: p.filamentos.length === 0 && p.gramos_total != null ? String(p.gramos_total) : "",
    filamentos: p.filamentos.length > 0 ? p.filamentos.map((f) => ({ descripcion: f.descripcion, gramos: String(f.gramos) })) : [{ descripcion: "", gramos: "" }],
    horas: min != null && Math.floor(min / 60) > 0 ? String(Math.floor(min / 60)) : "",
    minutos: min != null && min % 60 > 0 ? String(min % 60) : "",
    fecha: p.fecha,
    sumar: p.afecta_inventario,
    precioPropio: min != null && p.precio_kwh != null ? String(p.precio_kwh) : "",
    potenciaPropia: min != null && p.potencia_w != null ? String(p.potencia_w) : "",
  };
};

/** Un trabajo de la impresora como borrador de lote: fecha, tiempo y filamento ya puestos. Las
 *  piezas y la nota las completa la persona. Con un solo filamento se usa el total; con varios, el
 *  desglose por color. */
export const loteDesdeTrabajo = (t: TrabajoImpresora): EstadoLote => {
  const base = loteVacio(t.fecha);
  const min = t.minutos;
  const tiempo = {
    horas: min != null && Math.floor(min / 60) > 0 ? String(Math.floor(min / 60)) : "",
    minutos: min != null && min % 60 > 0 ? String(min % 60) : "",
  };
  if (t.filamentos.length > 1) {
    return {
      ...base,
      ...tiempo,
      modo: "por_filamento",
      filamentos: t.filamentos.map((f) => ({ descripcion: [f.tipo, f.color].filter(Boolean).join(" "), gramos: String(f.gramos) })),
    };
  }
  return { ...base, ...tiempo, total: t.gramos_total != null ? String(t.gramos_total) : "" };
};

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
  if (!e.fecha) return { error: "Pon la fecha de producción." };
  if (e.fecha > hoyISO()) return { error: "La fecha de producción no puede ser futura." };
  if (e.fecha !== hoyISO()) extra.fecha = e.fecha;
  if (!e.sumar) extra.afecta_inventario = false;
  if (e.precioPropio.trim() !== "") {
    const v = num(e.precioPropio);
    if (!Number.isFinite(v) || v < 0) return { error: "El precio del kWh de este lote debe ser 0 o más." };
    extra.precio_kwh = v;
  }
  if (e.potenciaPropia.trim() !== "") {
    const v = num(e.potenciaPropia);
    if (!Number.isFinite(v) || v <= 0) return { error: "La potencia de este lote debe ser mayor que 0." };
    extra.potencia_w = v;
  }
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
export function energiaEstimada(
  minutos: number,
  p: Parametros | null,
  propia?: { precio: string; potencia: string },
): { kwh: number; costo: number | null } | null {
  const potPropia = propia && propia.potencia.trim() !== "" ? num(propia.potencia) : NaN;
  const prePropio = propia && propia.precio.trim() !== "" ? num(propia.precio) : NaN;
  const potencia = Number.isFinite(potPropia) ? potPropia : p?.potencia_impresora_w;
  const precio = Number.isFinite(prePropio) ? prePropio : p?.precio_kwh;
  if (!potencia || !minutos) return null;
  const kwh = (potencia / 1000) * (minutos / 60);
  return { kwh, costo: precio != null ? kwh * precio : null };
}

export function tiempoLargo(min: number): string {
  const h = Math.floor(min / 60);
  const m = min % 60;
  if (h === 0) return `${m} min`;
  return m === 0 ? `${h} h` : `${h} h ${m} min`;
}

export const gramos = (g: number) => `${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 }).format(g)} g`;
export const kwhTexto = (k: number) => `${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 3 }).format(k)} kWh`;
