"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { Boton } from "./Boton";
import { Icono } from "./Icono";

interface Props {
  abierta: boolean;
  onCerrar: () => void;
  titulo: string;
  descripcion?: string;
  pie?: ReactNode;
  children: ReactNode;
}

/** Panel deslizante hecho con <dialog>: el navegador atrapa el foco y cierra con Esc. */
export function Hoja({ abierta, onCerrar, titulo, descripcion, pie, children }: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (abierta && !d.open) d.showModal();
    if (!abierta && d.open) d.close();
  }, [abierta]);

  return (
    <dialog
      ref={ref}
      className="hoja"
      aria-labelledby="hoja-titulo"
      onClose={onCerrar}
      onClick={(e) => {
        if (e.target === ref.current) onCerrar();
      }}
    >
      {abierta && (
        <>
          <div className="hoja__cabecera">
            <div>
              <h2 id="hoja-titulo" style={{ fontSize: "var(--text-xl)" }}>
                {titulo}
              </h2>
              {descripcion && <p className="muted">{descripcion}</p>}
            </div>
            <Boton variante="ghost" aria-label="Cerrar" onClick={onCerrar}>
              <Icono nombre="cerrar" />
            </Boton>
          </div>
          <div className="hoja__cuerpo">{children}</div>
          {pie && <div className="hoja__pie">{pie}</div>}
        </>
      )}
    </dialog>
  );
}
