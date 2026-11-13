"use client";

import { Boton } from "@/components/ui/Boton";
import { Segmentado } from "@/components/ui/Segmentado";
import { dinero } from "@/lib/format";
import { energiaEstimada, gramos, kwhTexto, minutosDe, tiempoLargo, totalGramos, type EstadoLote } from "@/lib/produccion";
import type { Parametros } from "@/lib/types";

interface Props {
  valor: EstadoLote;
  onCambio: (v: EstadoLote) => void;
  parametros: Parametros | null;
  onAbrirParametros: () => void;
}

/** Filamento (total o por filamento) y tiempo de impresión del lote, con la energía estimada. */
export function FilamentoTiempo({ valor, onCambio, parametros, onAbrirParametros }: Props) {
  const set = (parcial: Partial<EstadoLote>) => onCambio({ ...valor, ...parcial });
  const setFil = (i: number, campo: "descripcion" | "gramos", v: string) =>
    set({ filamentos: valor.filamentos.map((f, j) => (j === i ? { ...f, [campo]: v } : f)) });
  const minutos = minutosDe(valor);
  const suma = totalGramos(valor);
  const energia = energiaEstimada(minutos, parametros);

  return (
    <fieldset className="filtiempo">
      <legend className="field__label">Filamento y tiempo (opcional)</legend>

      <Segmentado
        etiqueta="Cómo registrar el filamento"
        valor={valor.modo}
        opciones={[{ valor: "total", etiqueta: "Gramos totales" }, { valor: "por_filamento", etiqueta: "Por filamento" }]}
        onCambio={(modo) => set({ modo })}
      />

      {valor.modo === "total" ? (
        <label className="field">
          <span className="field__label">Gramos de filamento del lote</span>
          <input className="input num" type="number" inputMode="decimal" min={0} step="0.1" placeholder="Ej. 187,5" value={valor.total} onChange={(e) => set({ total: e.target.value })} />
        </label>
      ) : (
        <div className="filamentos">
          {valor.filamentos.map((f, i) => (
            <div key={i} className="filamento">
              <label className="field">
                <span className="field__label">Filamento {i + 1}</span>
                <input className="input" maxLength={60} placeholder="Ej. PLA negro" value={f.descripcion} onChange={(e) => setFil(i, "descripcion", e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Gramos</span>
                <input className="input num" type="number" inputMode="decimal" min={0} step="0.1" placeholder="0" value={f.gramos} onChange={(e) => setFil(i, "gramos", e.target.value)} />
              </label>
              {valor.filamentos.length > 1 && (
                <Boton variante="ghost" pequeno aria-label={`Quitar filamento ${i + 1}`} onClick={() => set({ filamentos: valor.filamentos.filter((_, j) => j !== i) })}>
                  Quitar
                </Boton>
              )}
            </div>
          ))}
          {valor.filamentos.length < 20 && (
            <Boton variante="secondary" pequeno onClick={() => set({ filamentos: [...valor.filamentos, { descripcion: "", gramos: "" }] })}>
              + Agregar filamento
            </Boton>
          )}
          <p className="field__hint num">Total: <strong>{suma ? gramos(suma) : "—"}</strong></p>
        </div>
      )}

      <div className="tiempo">
        <label className="field">
          <span className="field__label">Horas</span>
          <input className="input num" type="number" inputMode="numeric" min={0} step={1} placeholder="0" value={valor.horas} onChange={(e) => set({ horas: e.target.value })} />
        </label>
        <label className="field">
          <span className="field__label">Minutos</span>
          <input className="input num" type="number" inputMode="numeric" min={0} max={59} step={1} placeholder="0" value={valor.minutos} onChange={(e) => set({ minutos: e.target.value })} />
        </label>
      </div>

      <p className="field__hint num">
        {minutos > 0 && <>Tiempo de impresión: <strong>{tiempoLargo(minutos)}</strong>. </>}
        {energia ? (
          <>Energía estimada: <strong>{kwhTexto(energia.kwh)}</strong>{energia.costo != null && <> · <strong>{dinero(energia.costo)}</strong></>}. </>
        ) : minutos > 0 ? (
          <>Para ver la energía, define la potencia de tu impresora. </>
        ) : null}
        <button type="button" className="enlace" onClick={onAbrirParametros}>Parámetros de energía</button>
      </p>
    </fieldset>
  );
}
