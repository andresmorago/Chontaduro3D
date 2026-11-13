"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorApi } from "./api";

/** Carga datos al montar y permite recargarlos. Ignora respuestas que llegan tarde. */
export function useCargar<T>(cargar: () => Promise<T>) {
  const [datos, setDatos] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);
  const version = useRef(0);
  const fn = useRef(cargar);
  fn.current = cargar;

  const recargar = useCallback(async () => {
    const mia = ++version.current;
    try {
      const d = await fn.current();
      if (mia === version.current) {
        setDatos(d);
        setError(null);
      }
    } catch (e) {
      if (mia === version.current) setError(e instanceof ErrorApi ? e.message : "No se pudo cargar.");
    } finally {
      if (mia === version.current) setCargando(false);
    }
  }, []);

  useEffect(() => {
    void recargar();
  }, [recargar]);

  return { datos, error, cargando, recargar };
}

export const mensajeDe = (e: unknown, alternativa = "No se pudo completar la acción.") =>
  e instanceof ErrorApi ? e.message : alternativa;
