/** Nombre en español del color más parecido a un valor hexadecimal (#rrggbb): sirve para rotular el
 *  filamento de un trabajo de la impresora («PLA Rojo») en vez de mostrar un código. */
const BASE: [string, [number, number, number]][] = [
  ["Negro", [20, 20, 20]],
  ["Blanco", [245, 245, 245]],
  ["Gris", [140, 140, 140]],
  ["Plateado", [200, 200, 205]],
  ["Rojo", [200, 30, 30]],
  ["Naranja", [240, 130, 30]],
  ["Naranja claro", [255, 182, 115]],
  ["Amarillo", [240, 210, 30]],
  ["Verde", [40, 150, 60]],
  ["Verde claro", [140, 210, 100]],
  ["Turquesa", [40, 180, 170]],
  ["Celeste", [130, 200, 235]],
  ["Azul", [30, 80, 200]],
  ["Azul oscuro", [20, 30, 110]],
  ["Morado", [120, 70, 170]],
  ["Morado oscuro", [70, 45, 140]],
  ["Rosado", [240, 150, 190]],
  ["Fucsia", [210, 40, 140]],
  ["Café", [110, 70, 40]],
  ["Beige", [225, 200, 160]],
  ["Dorado", [210, 170, 60]],
];

export function nombreDeColor(hex: string | null | undefined): string | null {
  const m = /^#?([0-9a-f]{6})/i.exec(hex ?? "");
  if (!m) return null;
  const n = parseInt(m[1]!, 16);
  const rgb: [number, number, number] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  let mejor = BASE[0]!;
  let d = Infinity;
  for (const c of BASE) {
    // Distancia «a ojo»: el verde pesa más y el azul menos (aproxima la percepción humana).
    const dist = 2 * (rgb[0] - c[1][0]) ** 2 + 4 * (rgb[1] - c[1][1]) ** 2 + 3 * (rgb[2] - c[1][2]) ** 2;
    if (dist < d) {
      d = dist;
      mejor = c;
    }
  }
  return mejor[0];
}
