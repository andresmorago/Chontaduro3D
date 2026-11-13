import type { ButtonHTMLAttributes } from "react";

type Variante = "primary" | "accent" | "secondary" | "ghost" | "danger";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variante?: Variante;
  pequeno?: boolean;
  bloque?: boolean;
  cargando?: boolean;
}

export function Boton({ variante = "primary", pequeno, bloque, cargando, className, children, disabled, type = "button", ...resto }: Props) {
  const clases = ["btn", `btn--${variante}`, pequeno && "btn--small", bloque && "btn--block", className].filter(Boolean).join(" ");
  return (
    <button {...resto} type={type} className={clases} disabled={disabled || cargando} aria-busy={cargando || undefined}>
      {children}
    </button>
  );
}
