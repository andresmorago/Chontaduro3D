"use client";

import { useEffect, useState } from "react";

interface Props {
  valor: number;
  onCambio: (n: number) => void;
  min?: number;
  max?: number;
  etiqueta: string;
  chico?: boolean;
  /** El número se puede escribir directamente (además de usar − y +). */
  editable?: boolean;
}

export function Contador({ valor, onCambio, min = 0, max = 10000, etiqueta, chico, editable }: Props) {
  const [texto, setTexto] = useState(String(valor));
  useEffect(() => setTexto(String(valor)), [valor]);
  const acotar = (n: number) => Math.min(max, Math.max(min, n));

  return (
    <div className={`contador${chico ? " contador--chico" : ""}`} role="group" aria-label={etiqueta}>
      <button type="button" className="contador__btn" aria-label={`Quitar una unidad de ${etiqueta}`} disabled={valor <= min} onClick={() => onCambio(Math.max(min, valor - 1))}>
        −
      </button>
      {editable ? (
        <input
          className="contador__valor contador__valor--campo"
          type="number"
          inputMode="numeric"
          min={min}
          max={max}
          step={1}
          value={texto}
          aria-label={`Cantidad de ${etiqueta}`}
          onChange={(e) => {
            setTexto(e.target.value);
            const n = parseInt(e.target.value, 10);
            if (Number.isFinite(n)) onCambio(acotar(n));
          }}
          onBlur={() => setTexto(String(valor))}
          onFocus={(e) => e.currentTarget.select()}
        />
      ) : (
        <span className="contador__valor" aria-live="polite">
          {valor}
        </span>
      )}
      <button type="button" className="contador__btn" aria-label={`Agregar una unidad de ${etiqueta}`} disabled={valor >= max} onClick={() => onCambio(Math.min(max, valor + 1))}>
        +
      </button>
    </div>
  );
}
