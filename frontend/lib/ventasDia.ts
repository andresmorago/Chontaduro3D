"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { limitesDeMes } from "./calendario";
import { mensajeDe } from "./hooks";
import type { Venta, VentaDia } from "./types";

/** Las ventas del día elegido y el resumen por día del mes que se ve en el calendario. Mientras llega
 *  el día nuevo `datos` es `null` (nunca se muestran las ventas de otro día bajo el título del nuevo). */
export function useVentasDelDia(dia: string, mes: string) {
  const [lista, setLista] = useState<{ dia: string; ventas: Venta[] } | null>(null);
  const [resumen, setResumen] = useState<{ mes: string; dias: VentaDia[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const vigente = useRef({ dia, mes });
  vigente.current = { dia, mes };

  const cargarDia = useCallback(async (d: string) => {
    try {
      const ventas = await api.ventas.deDia(d);
      if (vigente.current.dia === d) {
        setLista({ dia: d, ventas });
        setError(null);
      }
    } catch (e) {
      if (vigente.current.dia === d) setError(mensajeDe(e));
    }
  }, []);

  const cargarMes = useCallback(async (m: string) => {
    try {
      const [desde, hasta] = limitesDeMes(m);
      const dias = await api.ventas.resumen(desde, hasta);
      if (vigente.current.mes === m) setResumen({ mes: m, dias });
    } catch {
      /* el calendario se ve sin marcas; la lista del día ya avisa si algo falla */
    }
  }, []);

  useEffect(() => void cargarDia(dia), [dia, cargarDia]);
  useEffect(() => void cargarMes(mes), [mes, cargarMes]);

  const recargar = useCallback(
    () => Promise.all([cargarDia(vigente.current.dia), cargarMes(vigente.current.mes)]).then(() => undefined),
    [cargarDia, cargarMes],
  );

  return {
    datos: lista?.dia === dia ? lista.ventas : null,
    error,
    resumen: resumen?.mes === mes ? resumen.dias : null,
    recargar,
  };
}
