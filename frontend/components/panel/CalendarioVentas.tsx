"use client";

import { useRef } from "react";
import { partes, pad, sumarMes } from "@/lib/calendario";
import { dinero } from "@/lib/format";
import type { VentaDia } from "@/lib/types";

interface Props {
  /** Día elegido (YYYY-MM-DD). */
  dia: string;
  /** Hoy (YYYY-MM-DD): los días posteriores no se pueden elegir. */
  hoy: string;
  /** Mes que se ve (YYYY-MM). */
  mes: string;
  onMes: (mes: string) => void;
  onDia: (dia: string) => void;
  /** Ventas por día del mes que se ve (`null` mientras carga). */
  resumen: VentaDia[] | null;
}

const SEMANA = [
  { corto: "L", largo: "lunes" },
  { corto: "M", largo: "martes" },
  { corto: "X", largo: "miércoles" },
  { corto: "J", largo: "jueves" },
  { corto: "V", largo: "viernes" },
  { corto: "S", largo: "sábado" },
  { corto: "D", largo: "domingo" },
];

/** Las celdas del mes (semanas de lunes a domingo): el día YYYY-MM-DD o `null` para los huecos. */
function celdasDelMes(mes: string): (string | null)[] {
  const [a, m] = partes(mes);
  const inicio = (new Date(Date.UTC(a, m - 1, 1)).getUTCDay() + 6) % 7;
  const dias = new Date(Date.UTC(a, m, 0)).getUTCDate();
  const celdas: (string | null)[] = Array.from({ length: inicio }, () => null);
  for (let d = 1; d <= dias; d++) celdas.push(`${mes}-${pad(d)}`);
  while (celdas.length % 7 !== 0) celdas.push(null);
  return celdas;
}

const tituloMes = (mes: string) => {
  const [a, m] = partes(mes);
  const t = new Intl.DateTimeFormat("es-CO", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(a, m - 1, 1)));
  return t.charAt(0).toUpperCase() + t.slice(1); // «noviembre de 2026» → «Noviembre de 2026»
};

const nombreDia = (iso: string) => {
  const [a, m, d] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat("es-CO", { day: "numeric", month: "long", timeZone: "UTC" }).format(new Date(Date.UTC(a ?? 1970, (m ?? 1) - 1, d ?? 1)));
};

/** Calendario mensual para elegir el día de las ventas: marca los días con ventas (cuántas) y deja
 *  moverse con las flechas del teclado. */
export function CalendarioVentas({ dia, hoy, mes, onMes, onDia, resumen }: Props) {
  const rejilla = useRef<HTMLDivElement>(null);
  const porDia = new Map((resumen ?? []).map((r) => [r.fecha, r]));
  const mesDeHoy = hoy.slice(0, 7);
  // Un solo día entra con Tab (el elegido, o uno del mes que se ve); con las flechas se recorre el resto.
  const foco = dia.startsWith(mes) ? dia : hoy.startsWith(mes) ? hoy : `${mes}-01`;
  const totalMes = (resumen ?? []).reduce((s, r) => s + r.total, 0);
  const ventasMes = (resumen ?? []).reduce((s, r) => s + r.ventas, 0);

  // Flechas: ±1 día y ±7 días entre los días que se pueden elegir; Inicio/Fin: primero/último.
  function teclas(e: React.KeyboardEvent) {
    const paso: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
    const botones = Array.from(rejilla.current?.querySelectorAll<HTMLButtonElement>("button[data-fecha]:not(:disabled)") ?? []);
    const i = botones.findIndex((b) => b === document.activeElement);
    if (i < 0) return;
    let destino = i;
    if (e.key in paso) destino = Math.min(botones.length - 1, Math.max(0, i + (paso[e.key] ?? 0)));
    else if (e.key === "Home") destino = 0;
    else if (e.key === "End") destino = botones.length - 1;
    else return;
    e.preventDefault();
    botones[destino]?.focus();
  }

  return (
    <div className="cal" role="group" aria-label="Calendario de ventas">
      <div className="cal__cab">
        <button type="button" className="cal__nav" aria-label="Mes anterior" onClick={() => onMes(sumarMes(mes, -1))}>‹</button>
        <h3 className="cal__titulo" aria-live="polite">{tituloMes(mes)}</h3>
        <button type="button" className="cal__nav" aria-label="Mes siguiente" disabled={mes >= mesDeHoy} onClick={() => onMes(sumarMes(mes, 1))}>›</button>
      </div>
      <div className="cal__semana" aria-hidden="true">
        {SEMANA.map((d) => <span key={d.largo} title={d.largo}>{d.corto}</span>)}
      </div>
      <div className="cal__dias" ref={rejilla} onKeyDown={teclas}>
        {celdasDelMes(mes).map((f, i) => {
          if (f === null) return <span key={`h${i}`} className="cal__hueco" aria-hidden="true" />;
          const r = porDia.get(f);
          const futuro = f > hoy;
          const elegido = f === dia;
          const etiqueta = `${nombreDia(f)}${f === hoy ? " (hoy)" : ""}: ${r ? `${r.ventas} ${r.ventas === 1 ? "venta" : "ventas"}, ${dinero(r.total)}` : futuro ? "aún no" : "sin ventas"}`;
          return (
            <button
              key={f}
              type="button"
              className="cal__dia"
              data-fecha={f}
              data-hoy={f === hoy}
              data-ventas={Boolean(r)}
              aria-pressed={elegido}
              aria-label={etiqueta}
              title={r ? `${r.ventas} ${r.ventas === 1 ? "venta" : "ventas"} · ${dinero(r.total)}` : undefined}
              disabled={futuro}
              tabIndex={f === foco ? 0 : -1}
              onClick={() => onDia(f)}
            >
              <span className="cal__n num">{Number(f.slice(8))}</span>
              {r && <span className="cal__v num" aria-hidden="true">{r.ventas}</span>}
            </button>
          );
        })}
      </div>
      <p className="cal__pie num" role="status">
        {resumen == null ? "Cargando…" : ventasMes === 0 ? "Sin ventas este mes" : <>{ventasMes} {ventasMes === 1 ? "venta" : "ventas"} · <strong>{dinero(totalMes)}</strong> este mes</>}
      </p>
      <button type="button" className="cal__hoy" disabled={dia === hoy && mes === mesDeHoy} onClick={() => { onMes(mesDeHoy); onDia(hoy); }}>Ir a hoy</button>
    </div>
  );
}
