"use client";

import { Boton } from "@/components/ui/Boton";
import { Segmentado } from "@/components/ui/Segmentado";
import { dinero } from "@/lib/format";
import { energiaEstimada, gramos, kwhTexto, minutosDe, tiempoLargo, totalGramos, type EstadoLote } from "@/lib/produccion";
import type { BobinaSpoolman, Parametros } from "@/lib/types";

interface Props {
  valor: EstadoLote;
  onCambio: (v: EstadoLote) => void;
  parametros: Parametros | null;
  onAbrirParametros: () => void;
  /** Bobinas de Spoolman para elegir; `null` = Spoolman no está conectado (solo texto libre). */
  bobinas?: BobinaSpoolman[] | null;
}

const peso = (g: number | null) => (g == null ? "" : ` · ${Math.round(g)} g`);
const etiquetaBobina = (b: BobinaSpoolman) => `${b.nombre}${peso(b.restante_g)}`;

/** Filamento (total o por filamento) y tiempo de impresión del lote, con la energía estimada. */
export function FilamentoTiempo({ valor, onCambio, parametros, onAbrirParametros, bobinas = null }: Props) {
  const set = (parcial: Partial<EstadoLote>) => onCambio({ ...valor, ...parcial });
  const setFil = (i: number, campo: "descripcion" | "gramos", v: string) =>
    set({ filamentos: valor.filamentos.map((f, j) => (j === i ? { ...f, [campo]: v } : f)) });
  /** Elegir una bobina pone su nombre como texto; «Otro» la suelta y deja el texto a mano. */
  const elegirBobina = (i: number, id: string) => {
    const b = id === "" ? null : bobinas?.find((x) => String(x.id) === id) ?? null;
    set({
      filamentos: valor.filamentos.map((f, j) =>
        j !== i ? f : b ? { ...f, spool_id: b.id, descripcion: b.nombre } : { ...f, spool_id: id === "" ? null : f.spool_id },
      ),
    });
  };
  const enAms = (bobinas ?? []).filter((b) => (b.ubicacion ?? "").startsWith("AMS"));
  const guardadas = (bobinas ?? []).filter((b) => !(b.ubicacion ?? "").startsWith("AMS"));
  const minutos = minutosDe(valor);
  const suma = totalGramos(valor);
  const energia = energiaEstimada(minutos, parametros, { precio: valor.precioPropio, potencia: valor.potenciaPropia });

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
              {bobinas && (
                <label className="field">
                  <span className="field__label">{valor.filamentos.length > 1 ? `Filamento ${i + 1}` : "Filamento"}</span>
                  <select className="select" value={f.spool_id ?? ""} onChange={(e) => elegirBobina(i, e.target.value)}>
                    <option value="">Otro (escribir a mano)</option>
                    {f.spool_id != null && !bobinas.some((b) => b.id === f.spool_id) && <option value={f.spool_id}>{f.descripcion || `Bobina n.º ${f.spool_id}`} (archivada)</option>}
                    {enAms.length > 0 && <optgroup label="En el AMS">{enAms.map((b) => <option key={b.id} value={b.id}>{etiquetaBobina(b)}</option>)}</optgroup>}
                    {guardadas.length > 0 && <optgroup label="Guardadas">{guardadas.map((b) => <option key={b.id} value={b.id}>{etiquetaBobina(b)}</option>)}</optgroup>}
                  </select>
                </label>
              )}
              {(!bobinas || f.spool_id == null) && (
                <label className="field">
                  <span className="field__label">{bobinas ? "Nombre del filamento" : `Filamento ${i + 1}`}</span>
                  <input className="input" maxLength={60} placeholder="Ej. PLA negro" value={f.descripcion} onChange={(e) => setFil(i, "descripcion", e.target.value)} />
                </label>
              )}
              <div className="filamento__pie">
                <label className="field filamento__gramos">
                  <span className="field__label">Gramos</span>
                  <input className="input num" type="number" inputMode="decimal" min={0} step="0.1" placeholder="0" value={f.gramos} onChange={(e) => setFil(i, "gramos", e.target.value)} />
                </label>
                {valor.filamentos.length > 1 && (
                  <Boton variante="ghost" pequeno aria-label={`Quitar filamento ${i + 1}`} onClick={() => set({ filamentos: valor.filamentos.filter((_, j) => j !== i) })}>
                    Quitar
                  </Boton>
                )}
              </div>
            </div>
          ))}
          {valor.filamentos.length < 20 && (
            <Boton variante="secondary" pequeno onClick={() => set({ filamentos: [...valor.filamentos, { descripcion: "", gramos: "", spool_id: null }] })}>
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

      <details className="energia-propia" open={Boolean(valor.precioPropio || valor.potenciaPropia)}>
        <summary>Usar otros valores de energía en este lote</summary>
        <p className="field__hint">Para lotes viejos, cuando el kWh o la impresora eran otros. Vacío = los parámetros de hoy.</p>
        <div className="tiempo">
          <label className="field">
            <span className="field__label">Precio del kWh de este lote (COP)</span>
            <input className="input num" type="number" inputMode="decimal" min={0} step="0.01" placeholder={parametros?.precio_kwh != null ? String(parametros.precio_kwh) : "—"} value={valor.precioPropio} onChange={(e) => set({ precioPropio: e.target.value })} />
          </label>
          <label className="field">
            <span className="field__label">Potencia de este lote (W)</span>
            <input className="input num" type="number" inputMode="decimal" min={0} step="0.1" placeholder={parametros?.potencia_impresora_w != null ? String(parametros.potencia_impresora_w) : "—"} value={valor.potenciaPropia} onChange={(e) => set({ potenciaPropia: e.target.value })} />
          </label>
        </div>
      </details>
    </fieldset>
  );
}
