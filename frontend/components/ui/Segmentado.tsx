interface Props<T extends string> {
  valor: T;
  opciones: { valor: T; etiqueta: string }[];
  onCambio: (v: T) => void;
  etiqueta: string;
}

export function Segmentado<T extends string>({ valor, opciones, onCambio, etiqueta }: Props<T>) {
  return (
    <div className="segmentado" role="group" aria-label={etiqueta}>
      {opciones.map((o) => (
        <button key={o.valor} type="button" className="segmentado__op" aria-pressed={o.valor === valor} onClick={() => onCambio(o.valor)}>
          {o.etiqueta}
        </button>
      ))}
    </div>
  );
}
