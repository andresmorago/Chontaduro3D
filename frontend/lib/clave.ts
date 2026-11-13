const ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"; // sin 0/O/1/l/I: se lee y se dicta sin confundir

/** Contraseña aleatoria legible (criptográficamente aleatoria, sin sesgo de módulo). */
export function claveAleatoria(largo = 16): string {
  const tope = Math.floor(0x100000000 / ALFABETO.length) * ALFABETO.length;
  let salida = "";
  const buf = new Uint32Array(1);
  while (salida.length < largo) {
    crypto.getRandomValues(buf);
    const n = buf[0] ?? 0;
    if (n < tope) salida += ALFABETO[n % ALFABETO.length];
  }
  return salida;
}

/** Mismas reglas que el servidor, para avisar antes de enviar (el servidor siempre decide). */
export function motivoClaveDebil(c: string): string | null {
  if (c.length < 10) return "La contraseña debe tener al menos 10 caracteres.";
  if (/^\d+$/.test(c)) return "La contraseña es solo números. Mezcla letras.";
  return null;
}
