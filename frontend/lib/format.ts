const COP = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  maximumFractionDigits: 0,
});

export const dinero = (n: number) => COP.format(n);

export const ZONA = "America/Bogota";

/** Fecha de hoy en Bogotá, como YYYY-MM-DD. */
export function hoyISO(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: ZONA }).format(new Date());
}

export function fechaLarga(iso: string): string {
  const [a, m, d] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat("es-CO", { weekday: "long", day: "numeric", month: "long" }).format(
    new Date(a ?? 1970, (m ?? 1) - 1, d ?? 1),
  );
}

/** «12 oct 2025» a partir de YYYY-MM-DD (sin pasar por zonas horarias). */
export function fechaCorta(iso: string): string {
  const [a, m, d] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat("es-CO", { day: "numeric", month: "short", year: "numeric" })
    .format(new Date(a ?? 1970, (m ?? 1) - 1, d ?? 1))
    .replace(/\./g, "");
}

/** YYYY-MM-DD de `iso` menos `dias` días. */
export function restarDias(iso: string, dias: number): string {
  const [a, m, d] = iso.split("-").map(Number);
  const f = new Date(Date.UTC(a ?? 1970, (m ?? 1) - 1, (d ?? 1) - dias));
  return f.toISOString().slice(0, 10);
}

export function diaCorto(iso: string): string {
  const [a, m, d] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat("es-CO", { weekday: "short" })
    .format(new Date(a ?? 1970, (m ?? 1) - 1, d ?? 1))
    .replace(".", "");
}

export function hace(iso: string): string {
  const seg = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seg < 60) return "hace un momento";
  const min = Math.floor(seg / 60);
  if (min < 60) return `hace ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `hace ${h} h`;
  const dias = Math.floor(h / 24);
  return dias === 1 ? "ayer" : `hace ${dias} días`;
}

/** «11:31 p. m.» con espacios duros: la hora nunca se parte en dos líneas. */
export function hora(iso: string): string {
  return new Intl.DateTimeFormat("es-CO", { timeZone: ZONA, hour: "numeric", minute: "2-digit" })
    .format(new Date(iso))
    .replace(/[\s\u202f]+/g, "\u00a0");
}

const PAGOS: Record<string, string> = { efectivo: "Efectivo", transferencia: "Transferencia", otro: "Otro" };
/** Nombre de un método de pago para mostrarlo («efectivo» → «Efectivo»). */
export function etiquetaPago(metodo: string): string {
  return PAGOS[metodo] ?? metodo;
}

export function fechaHora(iso: string): string {
  return new Intl.DateTimeFormat("es-CO", {
    timeZone: ZONA,
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(iso));
}

/** Enlace de WhatsApp con un mensaje listo. El número se limpia a solo dígitos. */
export function enlaceWhatsapp(numero: string, mensaje: string): string {
  let digitos = numero.replace(/\D/g, "");
  // Celular colombiano escrito sin indicativo (10 dígitos que empiezan por 3): se añade 57.
  if (digitos.length === 10 && digitos.startsWith("3")) digitos = `57${digitos}`;
  return `https://wa.me/${digitos}?text=${encodeURIComponent(mensaje)}`;
}
