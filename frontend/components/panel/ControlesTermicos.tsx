"use client";

import { useState } from "react";
import { Boton } from "@/components/ui/Boton";
import { grados } from "@/lib/impresora";
import type { ComandoImpresora, DatosImpresora } from "@/lib/types";

interface Props {
  datos: DatosImpresora | null;
  /** Hay conexión con la impresora: sin ella no se envía nada. */
  conectada: boolean;
  /** La orden en curso (para mostrar «cargando» en su botón). */
  ocupado: string | null;
  ordenar: (comando: ComandoImpresora, valor: string, texto: string) => Promise<void>;
}

const BOQUILLA = { min: 150, max: 300, defecto: 200 };
const CAMA = { min: 0, max: 100, defecto: 60 };

/** Temperaturas de boquilla y cama, y velocidad de los dos ventiladores de la A1. Cada cambio se envía
 *  con su botón (nada se manda al mover un control), con los mismos límites que valida el servidor. */
export function ControlesTermicos({ datos: d, conectada, ocupado, ordenar }: Props) {
  const [boquilla, setBoquilla] = useState<string | null>(null);
  const [cama, setCama] = useState<string | null>(null);
  const [pieza, setPieza] = useState<number | null>(null);
  const [aux, setAux] = useState<number | null>(null);

  const valBoq = boquilla ?? String(d?.boquilla_objetivo ? Math.round(d.boquilla_objetivo) : BOQUILLA.defecto);
  const valCama = cama ?? String(d?.cama_objetivo ? Math.round(d.cama_objetivo) : CAMA.defecto);
  const nBoq = Number(valBoq);
  const nCama = Number(valCama);
  const boqOk = valBoq.trim() !== "" && Number.isInteger(nBoq) && nBoq >= BOQUILLA.min && nBoq <= BOQUILLA.max;
  const camaOk = valCama.trim() !== "" && Number.isInteger(nCama) && nCama >= CAMA.min && nCama <= CAMA.max;
  const vPieza = pieza ?? d?.ventilador_pieza ?? 0;
  const vAux = aux ?? d?.ventilador_aux ?? 0;

  return (
    <>
      <fieldset className="control-grupo">
        <legend className="field__label">Temperaturas</legend>
        <div className="control-fila">
          <label className="field control-fila__campo">
            <span className="field__label">Boquilla (°C)</span>
            <input className="input num" type="number" inputMode="numeric" min={BOQUILLA.min} max={BOQUILLA.max} step={5} value={valBoq} onChange={(e) => setBoquilla(e.target.value)} aria-invalid={!boqOk} />
          </label>
          <Boton variante="secondary" disabled={!conectada || !boqOk} cargando={ocupado === "temp_boquilla"} onClick={() => void ordenar("temp_boquilla", String(nBoq), `Boquilla a ${nBoq} °C.`).then(() => setBoquilla(null))}>Fijar</Boton>
          <Boton variante="ghost" pequeno disabled={!conectada} onClick={() => void ordenar("temp_boquilla", "0", "Boquilla apagada.").then(() => setBoquilla(null))}>Apagar</Boton>
          <span className="control-fila__ahora num">Ahora {grados(d?.boquilla ?? null)}{d?.boquilla_objetivo ? ` → ${grados(d.boquilla_objetivo)}` : ""}</span>
        </div>
        {!boqOk && <p className="field__hint" role="status">La boquilla va de {BOQUILLA.min} a {BOQUILLA.max} °C (usa «Apagar» para enfriarla).</p>}

        <div className="control-fila">
          <label className="field control-fila__campo">
            <span className="field__label">Cama (°C)</span>
            <input className="input num" type="number" inputMode="numeric" min={CAMA.min} max={CAMA.max} step={5} value={valCama} onChange={(e) => setCama(e.target.value)} aria-invalid={!camaOk} />
          </label>
          <Boton variante="secondary" disabled={!conectada || !camaOk} cargando={ocupado === "temp_cama"} onClick={() => void ordenar("temp_cama", String(nCama), `Cama a ${nCama} °C.`).then(() => setCama(null))}>Fijar</Boton>
          <Boton variante="ghost" pequeno disabled={!conectada} onClick={() => void ordenar("temp_cama", "0", "Cama apagada.").then(() => setCama(null))}>Apagar</Boton>
          <span className="control-fila__ahora num">Ahora {grados(d?.cama ?? null)}{d?.cama_objetivo ? ` → ${grados(d.cama_objetivo)}` : ""}</span>
        </div>
        {!camaOk && <p className="field__hint" role="status">La cama va de {CAMA.min} a {CAMA.max} °C.</p>}
        <p className="field__hint">No dejes la boquilla ni la cama calientes sin supervisión. Durante una impresión, el propio trabajo puede volver a cambiar estos valores.</p>
      </fieldset>

      <fieldset className="control-grupo">
        <legend className="field__label">Ventiladores</legend>
        <div className="control-fila">
          <label className="field control-fila__campo control-fila__campo--ancho">
            <span className="field__label">Pieza: <strong className="num">{vPieza} %</strong></span>
            <input type="range" min={0} max={100} step={5} value={vPieza} onChange={(e) => setPieza(Number(e.target.value))} aria-label="Velocidad del ventilador de la pieza (%)" />
          </label>
          <Boton variante="secondary" disabled={!conectada} cargando={ocupado === "ventilador_pieza"} onClick={() => void ordenar("ventilador_pieza", String(vPieza), `Ventilador de la pieza al ${vPieza} %.`).then(() => setPieza(null))}>Aplicar</Boton>
          <span className="control-fila__ahora num">Ahora {d?.ventilador_pieza != null ? `${d.ventilador_pieza} %` : "—"}</span>
        </div>
        <div className="control-fila">
          <label className="field control-fila__campo control-fila__campo--ancho">
            <span className="field__label">Auxiliar: <strong className="num">{vAux} %</strong></span>
            <input type="range" min={0} max={100} step={5} value={vAux} onChange={(e) => setAux(Number(e.target.value))} aria-label="Velocidad del ventilador auxiliar (%)" />
          </label>
          <Boton variante="secondary" disabled={!conectada} cargando={ocupado === "ventilador_aux"} onClick={() => void ordenar("ventilador_aux", String(vAux), `Ventilador auxiliar al ${vAux} %.`).then(() => setAux(null))}>Aplicar</Boton>
          <span className="control-fila__ahora num">Ahora {d?.ventilador_aux != null ? `${d.ventilador_aux} %` : "—"}</span>
        </div>
        <p className="field__hint">El ventilador de la pieza enfría lo recién impreso; el auxiliar mueve el aire dentro de la zona de impresión.</p>
      </fieldset>
    </>
  );
}
