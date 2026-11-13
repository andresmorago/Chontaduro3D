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

export function hora(iso: string): string {
  return new Intl.DateTimeFormat("es-CO", { timeZone: ZONA, hour: "numeric", minute: "2-digit" }).format(
    new Date(iso),
  );
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
