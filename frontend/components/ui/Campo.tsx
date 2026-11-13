import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

interface Base {
  etiqueta: string;
  ayuda?: string;
  error?: string | null;
}

function Envoltorio({ etiqueta, ayuda, error, id, children }: Base & { id: string; children: ReactNode }) {
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {etiqueta}
      </label>
      {children}
      <p className={`field__msg ${error ? "field__error" : "field__hint"}`} id={error ? `${id}-error` : ayuda ? `${id}-ayuda` : undefined} role={error ? "alert" : undefined}>
        {error ?? ayuda}
      </p>
    </div>
  );
}

const describe = (id: string, b: Base) => (b.error ? `${id}-error` : b.ayuda ? `${id}-ayuda` : undefined);

export function Entrada({ etiqueta, ayuda, error, className, ...p }: Base & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <Envoltorio etiqueta={etiqueta} ayuda={ayuda} error={error} id={id}>
      <input {...p} id={id} className={["input", className].filter(Boolean).join(" ")} aria-invalid={error ? true : undefined} aria-describedby={describe(id, { etiqueta, ayuda, error })} />
    </Envoltorio>
  );
}

export function AreaTexto({ etiqueta, ayuda, error, ...p }: Base & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId();
  return (
    <Envoltorio etiqueta={etiqueta} ayuda={ayuda} error={error} id={id}>
      <textarea {...p} id={id} className="textarea" aria-invalid={error ? true : undefined} aria-describedby={describe(id, { etiqueta, ayuda, error })} />
    </Envoltorio>
  );
}

export function Seleccion({ etiqueta, ayuda, error, children, ...p }: Base & SelectHTMLAttributes<HTMLSelectElement>) {
  const id = useId();
  return (
    <Envoltorio etiqueta={etiqueta} ayuda={ayuda} error={error} id={id}>
      <select {...p} id={id} className="select" aria-invalid={error ? true : undefined}>
        {children}
      </select>
    </Envoltorio>
  );
}
