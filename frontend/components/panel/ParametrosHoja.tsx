"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useAvisos } from "@/components/ui/Avisos";
import { Boton } from "@/components/ui/Boton";
import { Entrada } from "@/components/ui/Campo";
import { Hoja } from "@/components/ui/Hoja";
import { api } from "@/lib/api";
import { mensajeDe } from "@/lib/hooks";
import type { Parametros } from "@/lib/types";

interface Props {
  abierta: boolean;
  actuales: Parametros | null;
  onCerrar: () => void;
  onGuardado: (p: Parametros) => void;
}

/** Parámetros universales de energía: precio del kWh y potencia promedio de la impresora. */
export function ParametrosHoja({ abierta, actuales, onCerrar, onGuardado }: Props) {
  const { mostrar } = useAvisos();
  const [precio, setPrecio] = useState("");
  const [potencia, setPotencia] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    if (!abierta) return;
    setPrecio(actuales?.precio_kwh != null ? String(actuales.precio_kwh) : "");
    setPotencia(actuales?.potencia_impresora_w != null ? String(actuales.potencia_impresora_w) : "");
    setError(null);
  }, [abierta, actuales]);

  async function guardar(e: FormEvent) {
    e.preventDefault();
    const p = precio.trim() === "" ? null : Number(precio.replace(",", "."));
    const w = potencia.trim() === "" ? null : Number(potencia.replace(",", "."));
    if (p !== null && (!Number.isFinite(p) || p < 0)) return setError("El precio del kWh debe ser un número de 0 en adelante.");
    if (w !== null && (!Number.isFinite(w) || w <= 0)) return setError("La potencia debe ser un número mayor que 0.");
    setGuardando(true);
    setError(null);
    try {
      const r = await api.parametros.guardar({ precio_kwh: p, potencia_impresora_w: w });
      mostrar("Parámetros guardados. Se usan en los lotes que registres desde ahora.");
      onGuardado(r);
      onCerrar();
    } catch (err) {
      setError(mensajeDe(err));
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Hoja
      abierta={abierta}
      onCerrar={onCerrar}
      titulo="Parámetros de energía"
      descripcion="Valores universales para calcular el consumo de cada lote."
      pie={
        <>
          <Boton variante="secondary" onClick={onCerrar}>Cancelar</Boton>
          <Boton variante="accent" type="submit" form="form-parametros" cargando={guardando}>Guardar</Boton>
        </>
      }
    >
      <form id="form-parametros" onSubmit={guardar} style={{ display: "grid", gap: "var(--space-md)" }}>
        {error && <p className="alerta" role="alert">{error}</p>}
        <Entrada etiqueta="Precio del kWh (COP)" type="number" inputMode="decimal" min={0} step="0.01" value={precio} onChange={(e) => setPrecio(e.target.value)} ayuda="Lo que pagas por cada kWh, en tu factura de energía." />
        <Entrada etiqueta="Potencia promedio de la impresora (W)" type="number" inputMode="decimal" min={0} step="0.1" value={potencia} onChange={(e) => setPotencia(e.target.value)} ayuda="Consumo medio mientras imprime (p. ej. 150–300 W). Con el tiempo de impresión da los kWh de cada lote." />
        <p className="muted" style={{ fontSize: "var(--text-sm)" }}>
          kWh = potencia (kW) × horas. Cada lote guarda los valores con que se calculó: cambiarlos aquí no altera los lotes anteriores.
        </p>
      </form>
    </Hoja>
  );
}
