// Fechas del calendario de ventas (todo en UTC: sin sorpresas por zonas horarias).

export const pad = (n: number) => String(n).padStart(2, "0");
export const partes = (mes: string): [number, number] => {
  const [a, m] = mes.split("-").map(Number);
  return [a ?? 1970, m ?? 1];
};

/** YYYY-MM un número de meses antes o después. */
export function sumarMes(mes: string, n: number): string {
  const [a, m] = partes(mes);
  const f = new Date(Date.UTC(a, m - 1 + n, 1));
  return `${f.getUTCFullYear()}-${pad(f.getUTCMonth() + 1)}`;
}

/** Primer y último día (YYYY-MM-DD) de un mes. */
export function limitesDeMes(mes: string): [string, string] {
  const [a, m] = partes(mes);
  const ultimo = new Date(Date.UTC(a, m, 0)).getUTCDate();
  return [`${mes}-01`, `${mes}-${pad(ultimo)}`];
}
