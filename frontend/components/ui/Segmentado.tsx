interface Props<T extends string> {
  valor: T;
  opciones: { valor: T; etiqueta: string }[];
  onCambio: (v: T) => void;
  etiqueta: string;
  /** En pantallas angostas las opciones pasan a una rejilla de 2 columnas (para 4 o más opciones). */
  rejilla?: boolean;
}

export function Segmentado<T extends string>({ valor, opciones, onCambio, etiqueta, rejilla }: Props<T>) {
  return (
    <div className={rejilla ? "segmentado segmentado--rejilla" : "segmentado"} role="group" aria-label={etiqueta}>
      {opciones.map((o) => (
        <button key={o.valor} type="button" className="segmentado__op" aria-pressed={o.valor === valor} onClick={() => onCambio(o.valor)}>
          {o.etiqueta}
        </button>
      ))}
    </div>
  );
}
