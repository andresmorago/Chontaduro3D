"use client";

import { useState } from "react";
import { Boton } from "@/components/ui/Boton";
import { Entrada } from "@/components/ui/Campo";
import { claveAleatoria } from "@/lib/clave";

interface Props {
  etiqueta: string;
  valor: string;
  onCambio: (v: string) => void;
  /** Muestra el botón «Generar» (útil para claves temporales que se le dictan a otra persona). */
  generar?: boolean;
  autoComplete?: string;
  ayuda?: string;
}

/** Campo de contraseña con ojo para verla y, opcionalmente, generador de claves legibles. */
export function CampoClave({ etiqueta, valor, onCambio, generar, autoComplete = "new-password", ayuda }: Props) {
  const [ver, setVer] = useState(false);
  return (
    <div className="campo-clave" style={{ display: "grid", gap: "var(--space-xs)" }}>
      <Entrada etiqueta={etiqueta} type={ver ? "text" : "password"} value={valor} onChange={(e) => onCambio(e.target.value)} autoComplete={autoComplete} autoCapitalize="none" autoCorrect="off" spellCheck={false} ayuda={ayuda} />
      <div style={{ display: "flex", gap: "var(--space-xs)", flexWrap: "wrap" }}>
        <Boton variante="ghost" pequeno aria-pressed={ver} onClick={() => setVer((v) => !v)}>{ver ? "Ocultar" : "Mostrar"}</Boton>
        {generar && (
          <Boton variante="secondary" pequeno onClick={() => { onCambio(claveAleatoria()); setVer(true); }}>
            Generar contraseña
          </Boton>
        )}
      </div>
    </div>
  );
}
