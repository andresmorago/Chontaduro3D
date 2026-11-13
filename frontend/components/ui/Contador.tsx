interface Props {
  valor: number;
  onCambio: (n: number) => void;
  min?: number;
  max?: number;
  etiqueta: string;
  chico?: boolean;
}

export function Contador({ valor, onCambio, min = 0, max = 10000, etiqueta, chico }: Props) {
  return (
    <div className={`contador${chico ? " contador--chico" : ""}`} role="group" aria-label={etiqueta}>
      <button type="button" className="contador__btn" aria-label={`Quitar una unidad de ${etiqueta}`} disabled={valor <= min} onClick={() => onCambio(Math.max(min, valor - 1))}>
        −
      </button>
      <span className="contador__valor" aria-live="polite">
        {valor}
      </span>
      <button type="button" className="contador__btn" aria-label={`Agregar una unidad de ${etiqueta}`} disabled={valor >= max} onClick={() => onCambio(Math.min(max, valor + 1))}>
        +
      </button>
    </div>
  );
}
